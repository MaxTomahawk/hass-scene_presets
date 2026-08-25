import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "scene_presets"


def import_color_moves():
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
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    color = types.ModuleType("homeassistant.util.color")
    color.color_RGB_to_xy = lambda r, g, b: (r / 255, g / 255)
    color.color_temperature_to_rgb = lambda kelvin: (255, 255, 255)
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.color"] = color

    return importlib.import_module("custom_components.scene_presets.color_moves")


class FakeState:
    def __init__(self, attributes):
        self.attributes = attributes


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False, context=None):
        self.calls.append((domain, service, data, blocking, context))


class FakeHass:
    def __init__(self, states):
        self._states = states
        self.states = SimpleNamespace(get=lambda entity_id: self._states.get(entity_id))
        self.services = FakeServices()


def first_preset_id(module):
    return module.PRESET_DATA["presets"][0]["id"]


def test_build_xy_moves_does_not_mutate_callers_target_list():
    module = import_color_moves()
    targets = ["light.one", "light.two"]
    original = list(targets)
    hass = FakeHass({
        "light.one": FakeState({
            "supported_color_modes": ["xy"],
            "xy_color": [0.40, 0.30],
        }),
        "light.two": FakeState({
            "supported_color_modes": ["xy"],
            "xy_color": [0.30, 0.40],
        }),
    })

    moves = module.build_light_moves(
        hass,
        first_preset_id(module),
        targets,
        transition=45,
        shuffle=True,
        smart_shuffle=False,
    )

    assert targets == original
    assert {move.entity_id for move in moves} == set(original)
    assert all(move.color_kind == "xy" for move in moves)
    assert all(move.transition == 45 for move in moves)
    assert all("xy_color" in move.service_data for move in moves)
    assert all(move.target_color is not None for move in moves)


def test_build_color_temperature_move_records_source_and_target(monkeypatch):
    module = import_color_moves()
    monkeypatch.setattr(module, "find_closest_ct_match", lambda x, y: 3200)
    hass = FakeHass({
        "light.temp": FakeState({
            "supported_color_modes": ["color_temp"],
            "color_temp_kelvin": 2700,
        }),
    })

    moves = module.build_light_moves(
        hass,
        first_preset_id(module),
        ["light.temp"],
        transition=10,
        shuffle=False,
        smart_shuffle=False,
    )

    assert len(moves) == 1
    move = moves[0]
    assert move.color_kind == "color_temp"
    assert move.source_color == 2700
    assert move.target_color == 3200
    assert move.service_data["color_temp_kelvin"] == 3200


def test_apply_light_moves_uses_one_supplied_context_for_all_calls():
    module = import_color_moves()
    hass = FakeHass({
        "light.one": FakeState({
            "supported_color_modes": ["xy"],
            "xy_color": [0.40, 0.30],
        }),
        "light.two": FakeState({
            "supported_color_modes": ["xy"],
            "xy_color": [0.30, 0.40],
        }),
    })
    moves = module.build_light_moves(
        hass,
        first_preset_id(module),
        ["light.one", "light.two"],
        transition=5,
        shuffle=False,
        smart_shuffle=False,
    )
    context = object()

    asyncio.run(module.apply_light_moves(hass, moves, context=context))

    assert len(hass.services.calls) == 2
    assert all(call[4] is context for call in hass.services.calls)
