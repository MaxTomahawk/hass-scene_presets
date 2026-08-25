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


def import_dynamic():
    for key in list(sys.modules):
        if key == "custom_components.scene_presets" or key.startswith("custom_components.scene_presets."):
            del sys.modules[key]
        if key == "homeassistant" or key.startswith("homeassistant."):
            del sys.modules[key]

    package = types.ModuleType("custom_components.scene_presets")
    package.__path__ = [str(PACKAGE_PATH)]
    sys.modules["custom_components.scene_presets"] = package

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    core = types.ModuleType("homeassistant.core")
    core.Context = FakeContext
    core.callback = lambda fn: fn
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    event_module = types.ModuleType("homeassistant.helpers.event")
    event_module.async_track_state_change_event = lambda *args, **kwargs: (lambda: None)
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    color = types.ModuleType("homeassistant.util.color")
    color.color_RGB_to_xy = lambda r, g, b: (0.0, 0.0)
    color.color_temperature_to_rgb = lambda kelvin: (255, 255, 255)

    sys.modules.update({
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event_module,
        "homeassistant.util": util,
        "homeassistant.util.color": color,
    })
    return importlib.import_module("custom_components.scene_presets.dynamic_scenes")


def make_scene(module):
    scene = object.__new__(module.DynamicScene)
    scene.id = "scene"
    scene.hass = SimpleNamespace()
    scene.interval = 5
    scene.parameters = {"stop_on_manual_change": True}
    scene._running = True
    scene._stopping = False
    scene._task = None
    scene._unsub_state_listener = None
    scene._root_context = FakeContext(id="root")
    scene._own_context_ids = set()
    scene._own_context_order = deque()
    scene._expected_moves = {}
    scene._stop_reason = None
    scene._last_error = None
    scene.stops = []
    scene.self_destruct_callback = lambda scene_id: scene.stops.append(scene_id)
    return scene


def test_overlapping_transitions_keep_multiple_expected_moves(monkeypatch):
    module = import_dynamic()
    scene = make_scene(module)

    first = SimpleNamespace(
        entity_id="light.one",
        color_kind="xy",
        source_color=(0.40, 0.30),
        target_color=(0.60, 0.50),
        transition=45,
    )
    second = SimpleNamespace(
        entity_id="light.one",
        color_kind="xy",
        source_color=(0.45, 0.35),
        target_color=(0.20, 0.25),
        transition=45,
    )

    scene._record_expected_moves([first], 100.0)
    scene._record_expected_moves([second], 105.0)

    expected = scene._expected_moves["light.one"]
    assert len(expected) == 2
    assert len(expected) <= module.MAX_EXPECTED_MOVES_PER_LIGHT

    monkeypatch.setattr(module.time, "monotonic", lambda: 106.0)
    old_state = SimpleNamespace(
        state="on",
        attributes={"color_mode": "xy", "xy_color": [0.40, 0.30]},
    )
    new_state = SimpleNamespace(
        state="on",
        attributes={"color_mode": "xy", "xy_color": [0.48, 0.38]},
        context=FakeContext(id="delayed-report"),
    )
    event = SimpleNamespace(data={
        "entity_id": "light.one",
        "old_state": old_state,
        "new_state": new_state,
    })

    scene._handle_state_change(event)

    assert scene.stops == []
