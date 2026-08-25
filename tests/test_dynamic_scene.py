import asyncio
from collections import deque
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
    event_module = types.ModuleType("homeassistant.helpers.event")
    event_module.async_track_state_change_event = lambda hass, entity_ids, callback: (lambda: None)
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.event"] = event_module

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


def make_dynamic_scene(module, stop_on_manual_change=True):
    scene = object.__new__(module.DynamicScene)
    scene.id = "scene-id"
    scene.hass = FakeHass()
    scene.interval = 5
    scene.parameters = {
        "preset_id": "preset",
        "light_entity_ids": ["light.one"],
        "transition": 45,
        "shuffle": True,
        "brightness": None,
        "stop_on_manual_change": stop_on_manual_change,
    }
    scene._running = True
    scene._stopping = False
    scene._task = None
    scene._unsub_state_listener = None
    scene._root_context = FakeContext(id="root", user_id="user")
    scene._own_context_ids = set()
    scene._own_context_order = deque()
    scene._expected_moves = {}
    scene._stop_reason = None
    scene._last_error = None
    scene.stops = []
    scene.self_destruct_callback = lambda scene_id: scene.stops.append(scene_id)
    return scene


def test_dynamic_step_contexts_are_unique_share_root_and_stay_bounded():
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module)

    first = scene._new_step_context()
    second = scene._new_step_context()

    assert first.id != second.id
    assert first.parent_id == "root"
    assert second.parent_id == "root"

    for _ in range(200):
        scene._new_step_context()

    assert len(scene._own_context_ids) <= module.MAX_OWN_CONTEXT_IDS


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
    assert scene._stop_reason == "light_turned_off"


def test_contextless_report_toward_expected_target_is_ignored_but_divergence_stops(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    manual = import_scene_module("manual_change")
    scene = make_dynamic_scene(module)
    scene._expected_moves["light.one"] = manual.ExpectedColorMove(
        color_kind="xy",
        source_color=(0.4, 0.3),
        target_color=(0.6, 0.5),
        started_at=100.0,
        transition=45,
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: 110.0)

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.48, 0.38]}, context=FakeContext(id="device-report")),
    ))
    assert scene.stops == []

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.48, 0.38]}),
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.2, 0.65]}, context=FakeContext(id="physical-change")),
    ))
    assert scene.stops == ["scene-id"]


def test_explicit_user_color_change_stops_even_if_it_moves_toward_target(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    manual = import_scene_module("manual_change")
    scene = make_dynamic_scene(module)
    scene._expected_moves["light.one"] = manual.ExpectedColorMove(
        color_kind="xy",
        source_color=(0.4, 0.3),
        target_color=(0.6, 0.5),
        started_at=100.0,
        transition=45,
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: 110.0)

    scene._handle_state_change(event(
        FakeState(attributes={"color_mode": "xy", "xy_color": [0.4, 0.3]}),
        FakeState(
            attributes={"color_mode": "xy", "xy_color": [0.48, 0.38]},
            context=FakeContext(id="user-change", user_id="other-user"),
        ),
    ))

    assert scene.stops == ["scene-id"]


def test_dynamic_loop_executes_five_iterations_without_self_stopping(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module, stop_on_manual_change=False)
    applied = []
    sleeps = 0
    move = SimpleNamespace(
        entity_id="light.one",
        color_kind="xy",
        source_color=(0.4, 0.3),
        target_color=(0.5, 0.4),
        transition=5,
        service_data={"entity_id": "light.one", "xy_color": (0.5, 0.4)},
    )

    def build_moves(*args, **kwargs):
        return [move]

    async def apply_moves(hass, moves, context=None):
        applied.append((list(moves), context))

    async def fake_sleep(interval):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 5:
            scene._running = False

    monkeypatch.setattr(module, "build_light_moves", build_moves, raising=False)
    monkeypatch.setattr(module, "apply_light_moves", apply_moves, raising=False)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    asyncio.run(scene._loop())

    assert len(applied) == 5
    assert scene.stops == []
    assert scene._last_error is None


def test_iteration_exception_cleans_up_instead_of_leaving_zombie(monkeypatch):
    module = import_scene_module("dynamic_scenes")
    scene = make_dynamic_scene(module, stop_on_manual_change=False)
    move = SimpleNamespace(
        entity_id="light.one",
        color_kind="xy",
        source_color=(0.4, 0.3),
        target_color=(0.5, 0.4),
        transition=5,
        service_data={"entity_id": "light.one"},
    )

    monkeypatch.setattr(module, "build_light_moves", lambda *a, **k: [move], raising=False)

    async def fail_apply(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "apply_light_moves", fail_apply, raising=False)
    monkeypatch.setattr(module, "apply_preset", fail_apply, raising=False)

    asyncio.run(scene._loop())

    assert scene._running is False
    assert scene._stop_reason == "error"
    assert "RuntimeError: boom" in scene._last_error
    assert scene.stops == ["scene-id"]
