import uuid
import asyncio
import logging
import time

from homeassistant.core import Context, callback
from homeassistant.helpers.event import async_track_state_change_event

from .presets import apply_preset
from .manual_change import color_changed, is_scene_context
from .const import *

_LOGGER = logging.getLogger(__name__)

CONTEXTLESS_REPORT_GRACE_SECONDS = 2.0


class DynamicScene:
    def __init__(self, hass, self_destruct_callback, parameters, interval, parent_context=None):
        self.id = str(uuid.uuid4())
        self.hass = hass
        self.interval = interval
        self._running = False
        self._stopping = False
        self._task = None
        self.parameters = parameters
        self.self_destruct_callback = self_destruct_callback
        self._own_context_ids = set()
        self._root_context = Context(
            user_id=getattr(parent_context, "user_id", None),
            parent_id=getattr(parent_context, "id", None),
        )
        self._unsub_state_listener = None
        self._last_command_monotonic = None

        if self.parameters.get(ATTR_STOP_ON_MANUAL_CHANGE, False):
            light_entity_ids = self.parameters.get("light_entity_ids", [])
            if light_entity_ids:
                self._unsub_state_listener = async_track_state_change_event(
                    self.hass,
                    light_entity_ids,
                    self._handle_state_change,
                )

    def _new_step_context(self):
        """Create and remember one context for a complete preset iteration."""
        context = Context(
            user_id=self._root_context.user_id,
            parent_id=self._root_context.id,
        )
        self._own_context_ids.add(context.id)
        return context

    def _is_recent_contextless_scene_report(self, context):
        """Handle integrations that lose service context on a device report.

        A very short grace period prevents the scene's own immediate state
        report from being mistaken for a manual override. Explicit HA user
        actions are never covered by this fallback.
        """
        if getattr(context, "user_id", None) is not None:
            return False
        if getattr(context, "parent_id", None) is not None:
            return False
        if self._last_command_monotonic is None:
            return False

        elapsed = time.monotonic() - self._last_command_monotonic
        return 0 <= elapsed <= CONTEXTLESS_REPORT_GRACE_SECONDS

    @callback
    def _handle_state_change(self, event):
        if not self._running or not self.parameters.get(ATTR_STOP_ON_MANUAL_CHANGE, False):
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or new_state is None:
            return

        entity_id = event.data.get("entity_id", getattr(new_state, "entity_id", "unknown"))

        if new_state.state == "off":
            self._stop_for_manual_change("light_turned_off", entity_id)
            return

        if old_state.state != "on" or new_state.state != "on":
            return

        if not color_changed(old_state.attributes, new_state.attributes):
            return

        context = new_state.context
        if is_scene_context(
            context.id,
            context.parent_id,
            self._root_context.id,
            self._own_context_ids,
        ):
            return

        if self._is_recent_contextless_scene_report(context):
            _LOGGER.debug(
                "Ignoring contextless color report for %s immediately after dynamic scene %s command",
                entity_id,
                self.id,
            )
            return

        self._stop_for_manual_change("external_color_change", entity_id)

    def _stop_for_manual_change(self, reason, entity_id):
        if self._stopping or not self._running:
            return

        self._stopping = True
        _LOGGER.info(
            "Stopping dynamic scene %s because of %s on %s",
            self.id,
            reason,
            entity_id,
        )
        self.self_destruct_callback(self.id)

    async def _loop(self):
        run_count = 0

        while self._running:
            light_entity_ids = self.parameters.get("light_entity_ids")
            transition = self.parameters.get(ATTR_TRANSITION)
            smart_shuffle = True

            if run_count == 0:
                transition = 0.5
                smart_shuffle = False
            else:
                entity_states = [
                    (entity_id, self.hass.states.get(entity_id))
                    for entity_id in light_entity_ids
                    if entity_id is not None
                ]
                lights_on = len([
                    state for _, state in entity_states
                    if state is not None and state.state == "on"
                ])

                if lights_on == 0:
                    self._running = False
                    self.self_destruct_callback(self.id)
                    return
                else:
                    # With manual-change stop disabled, preserve the existing behavior:
                    # explicitly turned-off lights are skipped on subsequent iterations.
                    light_entity_ids = [
                        entity_id for entity_id, state in entity_states
                        if state is not None and state.state == "on"
                    ]

            step_context = self._new_step_context()
            self._last_command_monotonic = time.monotonic()
            await apply_preset(
                self.hass,
                self.parameters.get(ATTR_SCENE_PRESET_ID),
                light_entity_ids,
                transition,
                self.parameters.get(ATTR_SHUFFLE),
                smart_shuffle,
                self.parameters.get(ATTR_BRIGHTNESS, None),
                context=step_context,
            )
            run_count += 1

            await asyncio.sleep(self.interval)

    def start_loop(self):
        if self._running:
            return
        self._running = True
        self._task = self.hass.create_task(self._loop())

    def stop_loop(self):
        self._running = False
        self._stopping = True

        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        if self._task and self._task is not asyncio.current_task():
            self._task.cancel()

        self._task = None
        self._own_context_ids.clear()
        self._last_command_monotonic = None

    def to_dict(self):
        return {
            "id": self.id,
            "interval": self.interval,
            "parameters": self.parameters,
            "running": self._running,
        }

    def __del__(self):
        self.stop_loop()


class DynamicSceneManager:
    def __init__(self):
        self.dynamic_scenes = {}

    def create_new(self, hass, parameters, interval, parent_context=None):
        scene = DynamicScene(
            hass,
            lambda scene_id: self.delete_by_id(scene_id),
            parameters,
            interval,
            parent_context,
        )
        self.dynamic_scenes[scene.id] = scene
        scene.start_loop()
        return scene.to_dict()

    def get_by_id(self, id):
        return self.dynamic_scenes.get(id)

    def delete_by_id(self, id):
        active_scene = self.dynamic_scenes.get(id)

        if active_scene:
            active_scene.stop_loop()
            del self.dynamic_scenes[id]

    def stop_all(self):
        scenes_to_delete = []

        for scene in self.dynamic_scenes.values():
            scene.stop_loop()
            scenes_to_delete.append(scene.id)

        for scene_id in scenes_to_delete:
            del self.dynamic_scenes[scene_id]

    def stop_all_for_entity_id(self, entity_id):
        scenes_to_delete = []

        for scene in self.dynamic_scenes.values():
            entity_ids = scene.parameters.get("light_entity_ids", [])
            if entity_id in entity_ids:
                scene.stop_loop()
                scenes_to_delete.append(scene.id)

        for scene_id in scenes_to_delete:
            del self.dynamic_scenes[scene_id]

    def get_all(self):
        return list(self.dynamic_scenes.values())

    def get_all_as_dict(self):
        scenes_dict = {"dynamic_scenes": []}

        for scene in self.dynamic_scenes.values():
            scenes_dict["dynamic_scenes"].append(scene.to_dict())

        return scenes_dict
