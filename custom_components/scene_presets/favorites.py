"""Persistent per-user favorites for Scene Presets."""

import asyncio
import logging

from homeassistant.helpers.storage import Store

from .favorite_logic import FavoritesData
from .file_utils import PRESET_DATA

STORAGE_VERSION = 1
STORAGE_KEY = "scene_presets.favorites"

_LOGGER = logging.getLogger(__name__)


class FavoritesStore:
    """Persist favorite preset IDs by Home Assistant user ID."""

    def __init__(self, hass):
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._data = None
        self._user_listeners = {}
        self._sensor_user_listeners = set()
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

    async def async_sensor_user_ids(self):
        """Return users that should expose persistent favorites sensors."""
        async with self._lock:
            await self._async_ensure_loaded()
            return self._data.sensor_user_ids()

    def async_subscribe(self, user_id, callback):
        """Subscribe to favorite-list changes for one user."""
        callbacks = self._user_listeners.setdefault(user_id, set())
        callbacks.add(callback)

        def unsubscribe():
            current = self._user_listeners.get(user_id)
            if current is None:
                return
            current.discard(callback)
            if not current:
                self._user_listeners.pop(user_id, None)

        return unsubscribe

    def async_subscribe_sensor_users(self, callback):
        """Subscribe to users becoming eligible for a favorites sensor."""
        self._sensor_user_listeners.add(callback)

        def unsubscribe():
            self._sensor_user_listeners.discard(callback)

        return unsubscribe

    async def _async_save(self):
        await self._store.async_save(self._data.to_dict())

    def _notify(self, callbacks, value):
        for callback in tuple(callbacks):
            try:
                callback(value)
            except Exception:  # pragma: no cover - defensive integration boundary
                _LOGGER.exception("Scene Presets favorites listener failed")

    async def _async_mutate(self, user_id, mutation):
        async with self._lock:
            await self._async_ensure_loaded()
            was_sensor_user = self._data.is_sensor_user(user_id)
            result = mutation()
            is_sensor_user = self._data.is_sensor_user(user_id)
            await self._async_save()

        self._notify(self._user_listeners.get(user_id, ()), list(result))
        if is_sensor_user and not was_sensor_user:
            self._notify(self._sensor_user_listeners, user_id)

        return result

    async def async_set(self, user_id, favorites):
        return await self._async_mutate(
            user_id,
            lambda: self._data.set(user_id, favorites),
        )

    async def async_add(self, user_id, preset_id):
        return await self._async_mutate(
            user_id,
            lambda: self._data.add(user_id, preset_id),
        )

    async def async_remove(self, user_id, preset_id):
        return await self._async_mutate(
            user_id,
            lambda: self._data.remove(user_id, preset_id),
        )

    async def async_toggle(self, user_id, preset_id):
        return await self._async_mutate(
            user_id,
            lambda: self._data.toggle(user_id, preset_id),
        )
