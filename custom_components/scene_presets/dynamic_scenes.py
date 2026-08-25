import uuid
import asyncio
from collections import deque
import logging
import time

from homeassistant.core import Context, callback
from homeassistant.helpers.event import async_track_state_change_event

from .color_moves import apply_light_moves, build_light_moves
from .manual_change import (
    ExpectedColorMove,
    color_changed,
    is_expected_move_progress,
    is_scene_context,
)
from .const import *

_LOGGER = logging.getLogger(__name__)

MAX_OWN_CONTEXT_IDS = 64


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
        self._own_context_order = deque()
        self._expected_moves = {}
        self._stop_reason = None
        self._last_error = None
        self._root_context = Context(
            user_id=getattr(parent_context, "user_id", None),
            parent_id=getattr(parent_context, "id", None),
        )
        self._unsub_state_listener = None

        if self.parameters.get(ATTR_STOP_ON_MANUAL_CHANGE, False):
            light_entity_ids = self.parameters.get("light_entity_ids", [])
            if light_entity_ids:
                self._unsub_state_listener = async_track_state_change_event(
                    self.hass,
                    light_entity_ids,
                    self._handle_state_change,
                )

    def _new_step_context(self):
        """Create and remember one bounded context for a complete iteration."""
        context = Context(
            user_id=self._root_context.user_id,
            parent_id=self._root_context.id,
        )

        if not hasattr(self, "_own_context_order"):
            self._own_context_order = deque()
        self._own_context_ids.add(context.id)
        self._own_context_order.append(context.id)
        while len(self._own_context_order) > MAX_OWN_CONTEXT_IDS:
            expired = self._own_context_order.popleft()
            self._own_context_ids.discard(expired)

        return context

    def _record_expected_moves(self, moves, started_at):
        if not self.parameters.get(ATTR_STOP_ON_MANUAL_CHANGE, False):
            return

        for move in moves:
            if move.color_kind is None or move.target_color is None:
                continue
            self._expected_moves[move.entity_id] = ExpectedColorMove(
                color_kind=move.color_kind,
                source_color=move.source_color,
                target_color=move.target_color,
                started_at=started_at,
                transition=move.transition,
            )

    @callback
    def _handle_state_change(self, event):
        if not self._running or not self.parameters.get(ATTR_STOP_ON_MANUAL_CHANGE, False):
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or new_state is None:
            return

        entity_id = event.data.get(
            "entity_id",
            getattr(new_state, "entity_id", "unknown"),
        )

        if new_state.state == "off":
            self._stop_for_manual_change("light_turned_off", entity_id)
            return

        if old_state.state != "on" or new_state.state != "on":
            return

        if not color_changed(old_state.attributes, new_state.attributes):
            return

        context = new_state.context
        context_id = getattr(context, "id", None)
        parent_id = getattr(context, "parent_id", None)
        if is_scene_context(
            context_id,
            parent_id,
            self._root_context.id,
            self._own_context_ids,
        ):
            return

        # A Home Assistant user explicitly causing an unknown-context color
        # change is always an override, even if that color happens to be on
        # the path toward our current target.
        if getattr(context, "user_id", None) is not None:
            self._stop_for_manual_change("external_color_change", entity_id)
            return

        expected_move = self._expected_moves.get(entity_id)
        if is_expected_move_progress(
            expected_move,
            old_state.attributes,
            new_state.attributes,
            time.monotonic(),
        ):
            _LOGGER.debug(
                "Ignoring expected contextless color progress for %s in dynamic scene %s",
                entity_id,
                self.id,
            )
            return

        self._stop_for_manual_change("external_color_change", entity_id)

    def _stop_for_manual_change(self, reason, entity_id):
        if self._stopping or not self._running:
            return

        self._stop_reason = reason
        self._stopping = True
        _LOGGER.info(
            "Stopping dynamic scene %s because of %s on %s",
            self.id,
            reason,
            entity_id,
        )
        self.self_destruct_callback(self.id)

    def _self_destruct(self, reason, error=None):
        if self._stopping:
            return

        self._stop_reason = reason
        if error is not None:
            self._last_error = f"{type(error).__name__}: {error}"
        self._running = False
        self._stopping = True
        self.self_destruct_callback(self.id)

    async def _loop(self):
        run_count = 0

        try:
            while self._running:
                light_entity_ids = list(
                    self.parameters.get("light_entity_ids", [])
                )
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
                    active_entity_ids = [
                        entity_id
                        for entity_id, state in entity_states
                        if state is not None and state.state == "on"
                    ]

                    if not active_entity_ids:
                        self._self_destruct("all_lights_off")
                        return

                    light_entity_ids = active_entity_ids

                moves = build_light_moves(
                    self.hass,
                    self.parameters.get(ATTR_SCENE_PRESET_ID),
                    light_entity_ids,
                    transition,
                    self.parameters.get(ATTR_SHUFFLE),
                    smart_shuffle,
                    self.parameters.get(ATTR_BRIGHTNESS, None),
                )
                step_context = self._new_step_context()
                started_at = time.monotonic()
                self._record_expected_moves(moves, started_at)
                await apply_light_moves(
                    self.hass,
                    moves,
                    context=step_context,
                )
                run_count += 1

                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # integration boundary: never leave a zombie task
            _LOGGER.exception("Dynamic scene %s failed", self.id)
            self._self_destruct("error", err)

    def start_loop(self):
        if self._running:
            return
        self._running = True
        self._task = self.hass.create_task(self._loop())

    def stop_loop(self, reason=None):
        self._running = False
        self._stopping = True
        if reason is not None and self._stop_reason is None:
            self._stop_reason = reason
        elif self._stop_reason is None:
            self._stop_reason = "stopped"

        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        if self._task and self._task is not asyncio.current_task():
            self._task.cancel()

        self._task = None
        self._own_context_ids.clear()
        self._own_context_order.clear()
        self._expected_moves.clear()

    def to_dict(self):
        return {
            "id": self.id,
            "interval": self.interval,
            "parameters": self.parameters,
            "running": self._running,
            "stop_reason": self._stop_reason,
            "last_error": self._last_error,
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

    def delete_by_id(self, id, reason=None):
        active_scene = self.dynamic_scenes.get(id)

        if active_scene:
            active_scene.stop_loop(reason=reason)
            del self.dynamic_scenes[id]

    def stop_all(self):
        scenes_to_delete = []

        for scene in self.dynamic_scenes.values():
            scene.stop_loop(reason="service_stop")
            scenes_to_delete.append(scene.id)

        for scene_id in scenes_to_delete:
            del self.dynamic_scenes[scene_id]

    def stop_all_for_entity_id(self, entity_id):
        scenes_to_delete = []

        for scene in self.dynamic_scenes.values():
            entity_ids = scene.parameters.get("light_entity_ids", [])
            if entity_id in entity_ids:
                scene.stop_loop(reason="superseded")
                scenes_to_delete.append(scene.id)

        for scene_id in scenes_to_delete:
            del self.dynamic_scenes[scene_id]

    def get_all(self):
        return list(self.dynamic_scenes.values())

    def get_all_as_dict(self):
        return {
            "dynamic_scenes": [
                scene.to_dict()
                for scene in self.dynamic_scenes.values()
            ]
        }
