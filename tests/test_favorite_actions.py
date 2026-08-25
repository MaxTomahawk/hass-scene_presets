import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


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


class FakeAuth:
    def __init__(self, users):
        self.users = {user.id: user for user in users}

    async def async_get_user(self, user_id):
        return self.users.get(user_id)


def make_hass(*users):
    return SimpleNamespace(auth=FakeAuth(users))


def make_user(user_id, is_admin=False):
    return SimpleNamespace(id=user_id, is_admin=is_admin)


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


def test_favorite_user_defaults_to_authenticated_actor():
    module = import_scene_module("favorite_actions")
    hass = make_hass(make_user("alice"))

    result = asyncio.run(
        module.async_resolve_favorite_user_id(hass, "alice", None)
    )

    assert result == "alice"


def test_admin_may_target_another_user():
    module = import_scene_module("favorite_actions")
    hass = make_hass(
        make_user("admin", is_admin=True),
        make_user("bob"),
    )

    result = asyncio.run(
        module.async_resolve_favorite_user_id(hass, "admin", "bob")
    )

    assert result == "bob"


def test_non_admin_may_not_target_another_user():
    module = import_scene_module("favorite_actions")
    hass = make_hass(
        make_user("alice"),
        make_user("bob"),
    )

    with pytest.raises(PermissionError, match="another Home Assistant user"):
        asyncio.run(
            module.async_resolve_favorite_user_id(hass, "alice", "bob")
        )


def test_contextless_automation_may_target_explicit_valid_user():
    module = import_scene_module("favorite_actions")
    hass = make_hass(make_user("bob"))

    result = asyncio.run(
        module.async_resolve_favorite_user_id(hass, None, "bob")
    )

    assert result == "bob"


def test_missing_or_unknown_target_user_is_rejected():
    module = import_scene_module("favorite_actions")
    hass = make_hass(make_user("alice"))

    with pytest.raises(ValueError, match="user_id"):
        asyncio.run(
            module.async_resolve_favorite_user_id(hass, None, None)
        )

    with pytest.raises(ValueError, match="Unknown Home Assistant user"):
        asyncio.run(
            module.async_resolve_favorite_user_id(hass, "alice", "missing")
        )
