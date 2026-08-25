import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "scene_presets"


class FakeContext:
    counter = 0

    def __init__(self, user_id=None, parent_id=None, id=None):
        if id is None:
            FakeContext.counter += 1
            id = f"ctx-{FakeContext.counter}"
        self.id = id
        self.parent_id = parent_id
        self.user_id = user_id


def import_scene_module(name):
    for key in list(sys.modules):
        if key == "custom_components.scene_presets" or key.startswith("custom_components.scene_presets."):
            del sys.modules[key]

    package = types.ModuleType("custom_components.scene_presets")
    package.__path__ = [str(PACKAGE_PATH)]
    sys.modules["custom_components.scene_presets"] = package

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    core = types.ModuleType("homeassistant.core")
    core.Context = FakeContext
    core.callback = lambda fn: fn
    sys.modules["homeassistant.core"] = core

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_state_change_event = lambda hass, entity_ids, callback: (lambda: None)
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.event"] = event

    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    color = types.ModuleType("homeassistant.util.color")
    color.color_RGB_to_xy = lambda r, g, b: (0.0, 0.0)
    color.color_temperature_to_rgb = lambda kelvin: (255, 255, 255)
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.color"] = color

    return importlib.import_module(f"custom_components.scene_presets.{name}")


class FakeState:
    def __init__(self, state="on", attributes=None, context=None):
        self.state = state
        self.attributes = attributes or {}
        self.context = context or FakeContext()


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False, context=None):
        self.calls.append((domain, service, data, blocking, context))


class FakeHass:
    def __init__(self):
        self.services = FakeServices()
        self.states = SimpleNamespace(get=lambda entity_id: FakeState(
            attributes={"supported_color_modes": ["xy"], "xy_color": [0.4, 0.3]}
        ))


def test_apply_preset_forwards_same_context_to_every_light_call():
    presets = import_scene_module("presets")
    preset_id = presets.PRESET_DATA["presets"][0]["id"]
    hass = FakeHass()
    context = FakeContext(id="shared")

    asyncio.run(presets.apply_preset(
        hass,
        preset_id,
        ["light.one", "light.two"],
        1,
        False,
        False,
        context=context,
    ))

    assert len(hass.services.calls) == 2
    assert all(call[4] is context for call in hass.services.calls)


def make_dynamic_scene(module):
    scene = object.__new__(module.DynamicScene)
    scene.id = "scene-id"
    scene.hass = SimpleNamespace()
    scene.parameters = {"light_entity_ids": ["light.one"], "stop_on_manual_change": True}
    scene._running = True
    scene._stopping = False
    scene._task = None
    scene._unsub_state_listener = None
    scene._root_context = FakeContext(id="root", user_id="user")
    scene._own_context_ids = set()
    scene._last_command_monotonic = None
    scene.stops = []
    scene.self_destruct_callback = lambda scene_id: scene.stops.append(scene_id)
    return scene


def test_dynamic_step_contexts_are_unique_and_share_root_parent():
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)

    first = scene._new_step_context()
    second = scene._new_step_context()

    assert first.id != second.id
    assert first.parent_id == "root"
    assert second.parent_id == "root"
    assert first.id in scene._own_context_ids
    assert second.id in scene._own_context_ids


def event(old_state, new_state):
    return SimpleNamespace(data={"old_state": old_state, "new_state": new_state, "entity_id": "light.one"})


def test_external_color_change_stops_but_brightness_and_own_color_do_not():
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)
    own = scene._new_step_context()

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3], "brightness": 60}),
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3], "brightness": 200}, context=FakeContext(id="external-brightness")),
    ))
    assert scene.stops == []

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.5, 0.3]}, context=own),
    ))
    assert scene.stops == []

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.5, 0.3]}),
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.3, 0.5]}, context=FakeContext(id="external")),
    ))
    assert scene.stops == ["scene-id"]


def test_turning_any_target_off_stops_scene():
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)

    scene._handle_state_change(event(
        FakeState(state="on", attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(state="off", attributes={}, context=FakeContext(id="external-off")),
    ))

    assert scene.stops == ["scene-id"]


def test_contextless_color_report_immediately_after_scene_command_is_ignored(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)
    scene._last_command_monotonic = 100.0
    monkeypatch.setattr(module.time, "monotonic", lambda: 101.0)

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(
            attributes={"color_mode": "xy", "xy_color": [0.5, 0.3]},
            context=FakeContext(id="device-report"),
        ),
    ))

    assert scene.stops == []


def test_contextless_color_report_after_grace_period_stops_scene(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)
    scene._last_command_monotonic = 100.0
    monkeypatch.setattr(module.time, "monotonic", lambda: 103.5)

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(
            attributes={"color_mode": "xy", "xy_color": [0.5, 0.3]},
            context=FakeContext(id="external-device"),
        ),
    ))

    assert scene.stops == ["scene-id"]


def test_explicit_user_color_change_stops_even_during_grace_period(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)
    scene._last_command_monotonic = 100.0
    monkeypatch.setattr(module.time, "monotonic", lambda: 101.0)

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(
            attributes={"color_mode": "xy", "xy_color": [0.5, 0.3]},
            context=FakeContext(id="user-change", user_id="other-user"),
        ),
    ))

    assert scene.stops == ["scene-id"]
