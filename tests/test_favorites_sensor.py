import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "scene_presets"
SENSOR_PATH = PACKAGE_PATH / "sensor.py"


class FakeSensorEntity:
    def __init__(self):
        self.hass = None
        self.write_count = 0
        self._remove_callbacks = []

    def async_write_ha_state(self):
        self.write_count += 1

    def async_on_remove(self, callback):
        self._remove_callbacks.append(callback)


class FakeFavoritesStore:
    def __init__(self):
        self.favorites = {
            "alice": ["Rest", "Relax"],
            "bob": ["Relax"],
        }
        self.sensor_users = ["alice"]
        self.user_callbacks = {}
        self.sensor_user_callbacks = []

    async def async_sensor_user_ids(self):
        return list(self.sensor_users)

    async def async_get(self, user_id):
        return list(self.favorites.get(user_id, [])), True

    def async_subscribe(self, user_id, callback):
        self.user_callbacks.setdefault(user_id, []).append(callback)

        def unsub():
            self.user_callbacks[user_id].remove(callback)

        return unsub

    def async_subscribe_sensor_users(self, callback):
        self.sensor_user_callbacks.append(callback)

        def unsub():
            self.sensor_user_callbacks.remove(callback)

        return unsub

    def update(self, user_id, favorites):
        self.favorites[user_id] = list(favorites)
        for callback in list(self.user_callbacks.get(user_id, [])):
            callback(list(favorites))

    def register_sensor_user(self, user_id):
        if user_id not in self.sensor_users:
            self.sensor_users.append(user_id)
        for callback in list(self.sensor_user_callbacks):
            callback(user_id)


class FakeAuth:
    def __init__(self):
        self.users = {
            "alice": SimpleNamespace(id="alice", name="Alice"),
            "bob": SimpleNamespace(id="bob", name="Bob"),
        }

    async def async_get_user(self, user_id):
        return self.users.get(user_id)


class FakeHass:
    def __init__(self, store):
        self.data = {"scene_presets": {"favorites_store": store}}
        self.auth = FakeAuth()
        self.tasks = []

    def async_create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class FakeEntry:
    def __init__(self):
        self.unloads = []

    def async_on_unload(self, callback):
        self.unloads.append(callback)


def import_sensor_module():
    assert SENSOR_PATH.exists(), "sensor platform has not been implemented yet"

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
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    sensor = types.ModuleType("homeassistant.components.sensor")
    sensor.SensorEntity = FakeSensorEntity
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.sensor"] = sensor

    file_utils = types.ModuleType("custom_components.scene_presets.file_utils")
    file_utils.PRESET_DATA = {
        "presets": [
            {"id": "Rest", "name": "Rest mode"},
            {"id": "Relax", "name": "Relax mode"},
        ]
    }
    sys.modules["custom_components.scene_presets.file_utils"] = file_utils

    return importlib.import_module("custom_components.scene_presets.sensor")


def test_favorites_sensor_exposes_count_user_and_favorite_names_and_updates_live():
    module = import_sensor_module()
    store = FakeFavoritesStore()
    hass = FakeHass(store)
    entity = module.ScenePresetsFavoritesSensor(store, "alice", "Alice")
    entity.hass = hass

    asyncio.run(entity.async_added_to_hass())

    assert entity.unique_id == "scene_presets_favorites_alice"
    assert entity.name == "Scene Presets Favorites Alice"
    assert entity.native_value == 2
    assert entity.extra_state_attributes == {
        "user_id": "alice",
        "user_name": "Alice",
        "favorite_ids": ["Rest", "Relax"],
        "favorite_names": ["Rest mode", "Relax mode"],
    }

    store.update("alice", [])

    assert entity.native_value == 0
    assert entity.extra_state_attributes["favorite_ids"] == []
    assert entity.write_count == 1


def test_sensor_platform_adds_existing_and_new_sensor_users():
    module = import_sensor_module()
    store = FakeFavoritesStore()
    hass = FakeHass(store)
    entry = FakeEntry()
    added = []

    def async_add_entities(entities):
        for entity in entities:
            entity.hass = hass
        added.extend(entities)

    async def scenario():
        await module.async_setup_entry(hass, entry, async_add_entities)
        assert [entity.user_id for entity in added] == ["alice"]

        store.register_sensor_user("bob")
        await asyncio.sleep(0)
        if hass.tasks:
            await asyncio.gather(*hass.tasks)

        assert [entity.user_id for entity in added] == ["alice", "bob"]
        assert len(entry.unloads) == 1

    asyncio.run(scenario())
