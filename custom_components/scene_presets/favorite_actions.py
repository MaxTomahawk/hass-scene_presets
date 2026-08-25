"""Service response and authorization helpers for user-specific favorites."""


async def async_resolve_favorite_user_id(
    hass,
    context_user_id,
    requested_user_id=None,
):
    """Resolve and authorize the Home Assistant user targeted by an action.

    An authenticated caller defaults to itself. Admin users may explicitly
    target another user. Contextless automations may target an explicit valid
    user ID. Non-admin authenticated users cannot target somebody else.
    """
    target_user_id = requested_user_id or context_user_id
    if not target_user_id:
        raise ValueError(
            "Favorite actions require a user_id when no Home Assistant user "
            "is present in the action context."
        )

    target_user = await hass.auth.async_get_user(target_user_id)
    if target_user is None:
        raise ValueError(f"Unknown Home Assistant user '{target_user_id}'")

    if context_user_id and target_user_id != context_user_id:
        context_user = await hass.auth.async_get_user(context_user_id)
        if context_user is None:
            raise ValueError(
                f"Unknown Home Assistant context user '{context_user_id}'"
            )
        if not context_user.is_admin:
            raise PermissionError(
                "A non-admin user cannot manage favorites for another "
                "Home Assistant user."
            )

    return target_user_id


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
