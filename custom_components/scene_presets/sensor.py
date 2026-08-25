"""Sensor platform for per-user Scene Presets favorites."""

from homeassistant.components.sensor import SensorEntity

from .const import DATA_FAVORITES_STORE, DOMAIN
from .file_utils import PRESET_DATA

_PRESET_NAMES = {
    preset.get("id"): preset.get("name", preset.get("id"))
    for preset in PRESET_DATA.get("presets", [])
    if preset.get("id")
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up per-user favorites sensors from the Scene Presets config entry."""
    store = hass.data[DOMAIN][DATA_FAVORITES_STORE]
    known_user_ids = set()

    async def async_add_user(user_id):
        if user_id in known_user_ids:
            return

        known_user_ids.add(user_id)
        user = await hass.auth.async_get_user(user_id)
        user_name = getattr(user, "name", None) or user_id
        async_add_entities([
            ScenePresetsFavoritesSensor(store, user_id, user_name)
        ])

    for user_id in await store.async_sensor_user_ids():
        await async_add_user(user_id)

    def handle_new_sensor_user(user_id):
        hass.async_create_task(async_add_user(user_id))

    entry.async_on_unload(
        store.async_subscribe_sensor_users(handle_new_sensor_user)
    )


class ScenePresetsFavoritesSensor(SensorEntity):
    """Expose one Home Assistant user's Scene Presets favorites."""

    _attr_should_poll = False
    _attr_icon = "mdi:star"

    def __init__(self, store, user_id, user_name):
        super().__init__()
        self._store = store
        self._user_id = user_id
        self._user_name = user_name
        self._favorites = []
        self._attr_unique_id = f"scene_presets_favorites_{user_id}"
        self._attr_name = f"Scene Presets Favorites {user_name}"

    @property
    def user_id(self):
        return self._user_id

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return self._attr_name

    @property
    def native_value(self):
        return len(self._favorites)

    @property
    def extra_state_attributes(self):
        return {
            "user_id": self._user_id,
            "user_name": self._user_name,
            "favorite_ids": list(self._favorites),
            "favorite_names": [
                _PRESET_NAMES.get(preset_id, preset_id)
                for preset_id in self._favorites
            ],
        }

    async def async_added_to_hass(self):
        """Load initial favorites and subscribe to changes."""
        favorites, _ = await self._store.async_get(self._user_id)
        self._favorites = list(favorites)
        self.async_on_remove(
            self._store.async_subscribe(
                self._user_id,
                self._handle_favorites_update,
            )
        )

    def _handle_favorites_update(self, favorites):
        self._favorites = list(favorites)
        self.async_write_ha_state()
