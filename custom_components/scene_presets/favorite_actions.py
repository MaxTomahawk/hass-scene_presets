"""Service response helpers for user-specific favorites."""


async def async_get_favorites_response(favorites_store, user_id):
    """Return a dashboard-friendly favorites response for one user."""
    favorites, initialized = await favorites_store.async_get(user_id)
    return {
        "favorites": favorites,
        "count": len(favorites),
        "initialized": initialized,
    }


async def async_is_favorite_response(favorites_store, user_id, preset_id):
    """Return whether a preset is in one user's favorites."""
    favorites, initialized = await favorites_store.async_get(user_id)
    return {
        "preset_id": preset_id,
        "is_favorite": preset_id in favorites,
        "initialized": initialized,
    }
