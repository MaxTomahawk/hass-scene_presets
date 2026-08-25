import asyncio
import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "scene_presets"


def import_scene_module(name):
    for key in list(sys.modules):
        if key == "custom_components.scene_presets" or key.startswith("custom_components.scene_presets."):
            del sys.modules[key]

    package = types.ModuleType("custom_components.scene_presets")
    package.__path__ = [str(PACKAGE_PATH)]
    sys.modules["custom_components.scene_presets"] = package

    return importlib.import_module(f"custom_components.scene_presets.{name}")


class FakeFavoritesStore:
    def __init__(self, favorites, initialized=True):
        self.favorites = list(favorites)
        self.initialized = initialized

    async def async_get(self, user_id):
        assert user_id == "user-1"
        return list(self.favorites), self.initialized


def test_get_favorites_response_is_dashboard_friendly():
    module = import_scene_module("favorite_actions")
    store = FakeFavoritesStore(["Rest", "Relax"])

    result = asyncio.run(module.async_get_favorites_response(store, "user-1"))

    assert result == {
        "favorites": ["Rest", "Relax"],
        "count": 2,
        "initialized": True,
    }


def test_is_favorite_response_reports_membership():
    module = import_scene_module("favorite_actions")
    store = FakeFavoritesStore(["Rest", "Relax"])

    result = asyncio.run(
        module.async_is_favorite_response(store, "user-1", "Rest")
    )

    assert result == {
        "preset_id": "Rest",
        "is_favorite": True,
        "initialized": True,
    }


def test_is_favorite_response_reports_false_for_non_favorite():
    module = import_scene_module("favorite_actions")
    store = FakeFavoritesStore(["Rest"])

    result = asyncio.run(
        module.async_is_favorite_response(store, "user-1", "Relax")
    )

    assert result["is_favorite"] is False
