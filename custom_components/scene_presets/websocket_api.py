import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components import websocket_api


def async_setup_websocket_api(_hass, dynamic_scene_manager, favorites_store) -> None:
    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_presets/get_dynamic_scenes",
        }
    )
    def ws_get_dynamic_scenes(hass, connection, msg) -> None:
        connection.send_result(msg["id"], dynamic_scene_manager.get_all_as_dict())

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_presets/get_favorites",
        }
    )
    @websocket_api.async_response
    async def ws_get_favorites(hass, connection, msg) -> None:
        user = connection.user
        if user is None:
            connection.send_error(msg["id"], websocket_api.ERR_UNAUTHORIZED, "User required")
            return

        favorites, initialized = await favorites_store.async_get(user.id)
        connection.send_result(
            msg["id"],
            {"favorites": favorites, "initialized": initialized},
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_presets/set_favorites",
            vol.Required("favorites"): [cv.string],
        }
    )
    @websocket_api.async_response
    async def ws_set_favorites(hass, connection, msg) -> None:
        user = connection.user
        if user is None:
            connection.send_error(msg["id"], websocket_api.ERR_UNAUTHORIZED, "User required")
            return

        try:
            favorites = await favorites_store.async_set(user.id, msg["favorites"])
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_preset", str(err))
            return

        connection.send_result(
            msg["id"],
            {"favorites": favorites, "initialized": True},
        )

    websocket_api.async_register_command(_hass, ws_get_dynamic_scenes)
    websocket_api.async_register_command(_hass, ws_get_favorites)
    websocket_api.async_register_command(_hass, ws_set_favorites)
