import asyncio
import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "scene_presets"


class FakeStore:
    def __init__(self, hass, version, key):
        self.data = None
        self.saved = []

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data
        self.saved.append(data)


def import_favorites_module():
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
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = FakeStore
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.storage"] = storage

    file_utils = types.ModuleType("custom_components.scene_presets.file_utils")
    file_utils.PRESET_DATA = {
        "presets": [
            {"id": "Rest", "name": "Rest"},
            {"id": "Relax", "name": "Relax"},
        ]
    }
    sys.modules["custom_components.scene_presets.file_utils"] = file_utils

    return importlib.import_module("custom_components.scene_presets.favorites")


def test_store_notifies_sensor_registration_and_user_updates():
    module = import_favorites_module()
    store = module.FavoritesStore(None)
    registrations = []
    updates = []

    store.async_subscribe_sensor_users(registrations.append)
    store.async_subscribe("alice", lambda favorites: updates.append(list(favorites)))

    async def scenario():
        assert await store.async_sensor_user_ids() == []

        await store.async_set("alice", [])
        assert registrations == []
        assert updates == [[]]

        await store.async_add("alice", "Rest")
        assert registrations == ["alice"]
        assert updates[-1] == ["Rest"]
        assert await store.async_sensor_user_ids() == ["alice"]

        await store.async_remove("alice", "Rest")
        assert registrations == ["alice"]
        assert updates[-1] == []
        assert await store.async_sensor_user_ids() == ["alice"]

    asyncio.run(scenario())


def test_subscriptions_can_be_unsubscribed():
    module = import_favorites_module()
    store = module.FavoritesStore(None)
    registrations = []
    updates = []

    unsub_registration = store.async_subscribe_sensor_users(registrations.append)
    unsub_update = store.async_subscribe("alice", lambda favorites: updates.append(list(favorites)))
    unsub_registration()
    unsub_update()

    asyncio.run(store.async_add("alice", "Rest"))

    assert registrations == []
    assert updates == []
