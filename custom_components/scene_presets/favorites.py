"""Persistent per-user favorites for Scene Presets."""

import asyncio

from homeassistant.helpers.storage import Store

from .favorite_logic import FavoritesData
from .file_utils import PRESET_DATA

STORAGE_VERSION = 1
STORAGE_KEY = "scene_presets.favorites"


class FavoritesStore:
    """Persist favorite preset IDs by Home Assistant user ID."""

    def __init__(self, hass):
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._data = None
        self._valid_preset_ids = {
            preset.get("id")
            for preset in PRESET_DATA.get("presets", [])
            if preset.get("id")
        }

    async def _async_ensure_loaded(self):
        if self._data is None:
            stored = await self._store.async_load()
            self._data = FavoritesData(self._valid_preset_ids, stored)

    async def async_get(self, user_id):
        async with self._lock:
            await self._async_ensure_loaded()
            return self._data.get(user_id), self._data.is_initialized(user_id)

    async def _async_save(self):
        await self._store.async_save(self._data.to_dict())

    async def async_set(self, user_id, favorites):
        async with self._lock:
            await self._async_ensure_loaded()
            result = self._data.set(user_id, favorites)
            await self._async_save()
            return result

    async def async_add(self, user_id, preset_id):
        async with self._lock:
            await self._async_ensure_loaded()
            result = self._data.add(user_id, preset_id)
            await self._async_save()
            return result

    async def async_remove(self, user_id, preset_id):
        async with self._lock:
            await self._async_ensure_loaded()
            result = self._data.remove(user_id, preset_id)
            await self._async_save()
            return result

    async def async_toggle(self, user_id, preset_id):
        async with self._lock:
            await self._async_ensure_loaded()
            result = self._data.toggle(user_id, preset_id)
            await self._async_save()
            return result
