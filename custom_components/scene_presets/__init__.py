import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import logging
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ServiceValidationError
from .const import *

from .dynamic_scenes import DynamicSceneManager
from .favorite_actions import async_get_favorites_response, async_is_favorite_response
from .favorites import FavoritesStore
from .presets import apply_preset
from .view import async_setup_view, async_remove_view
from .util import ensure_list, resolve_targets
from .websocket_api import async_setup_websocket_api

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

APPLY_PRESET_SCHEMA = vol.Schema({
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
    vol.Required(ATTR_TARGETS): vol.Any(dict),
    vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
    vol.Optional(ATTR_TRANSITION, default=1): vol.Coerce(int),
    vol.Optional(ATTR_SHUFFLE, default=False): cv.boolean,
    vol.Optional(ATTR_SMART_SHUFFLE, default=False): cv.boolean
})

START_DYNAMIC_SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
    vol.Required(ATTR_TARGETS): vol.Any(dict),
    vol.Optional(ATTR_INTERVAL, default=60): vol.Coerce(int),
    vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
    vol.Optional(ATTR_TRANSITION, default=1): vol.Coerce(int),
    vol.Optional(ATTR_STOP_ON_MANUAL_CHANGE, default=False): cv.boolean,
})

STOP_DYNAMIC_SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DYNAMIC_SCENE_ID): cv.string,
})

STOP_DYNAMIC_SCENES_FOR_TARGETS_SCHEMA = vol.Schema({
    vol.Required(ATTR_TARGETS): vol.Any(dict),
})

FAVORITE_SCHEMA = vol.Schema({
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
})


_LOGGER = logging.getLogger(__name__)

dynamic_scene_manager = DynamicSceneManager()


def _get_favorites_store(hass):
    domain_data = hass.data.setdefault(DOMAIN, {})
    if DATA_FAVORITES_STORE not in domain_data:
        domain_data[DATA_FAVORITES_STORE] = FavoritesStore(hass)
    return domain_data[DATA_FAVORITES_STORE]


def _get_call_user_id(call):
    user_id = call.context.user_id
    if not user_id:
        raise ServiceValidationError(
            "Favorite actions require a Home Assistant user context. "
            "Call this action from an authenticated dashboard/user action."
        )
    return user_id


async def async_setup(hass, config):
    favorites_store = _get_favorites_store(hass)

    async def apply_preset_service(call):
        preset_id = call.data.get(ATTR_SCENE_PRESET_ID)
        targets = call.data.get(ATTR_TARGETS)
        brightness_override = call.data.get(ATTR_BRIGHTNESS)
        transition = call.data.get(ATTR_TRANSITION, 1)
        shuffle = call.data.get(ATTR_SHUFFLE, False)
        smart_shuffle = call.data.get(ATTR_SMART_SHUFFLE, False)

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))

        light_entity_ids = resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids)

        await apply_preset(
            hass,
            preset_id,
            light_entity_ids,
            transition,
            shuffle,
            smart_shuffle,
            brightness_override,
            context=call.context,
        )

    async def start_dynamic_scene(call):
        # always stop any existing actions first
        await stop_dynamic_scenes_for_targets(call)

        preset_id = call.data.get(ATTR_SCENE_PRESET_ID)
        targets = call.data.get(ATTR_TARGETS)
        interval = call.data.get(ATTR_INTERVAL)

        brightness_override = call.data.get(ATTR_BRIGHTNESS)
        transition = call.data.get(ATTR_TRANSITION, 1)
        stop_on_manual_change = call.data.get(ATTR_STOP_ON_MANUAL_CHANGE, False)
        shuffle = True

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))

        light_entity_ids = resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids)

        return dynamic_scene_manager.create_new(
            hass,
            {
                "preset_id": preset_id,
                "light_entity_ids": light_entity_ids,
                "brightness": brightness_override,
                "transition": transition,
                "shuffle": shuffle,
                "stop_on_manual_change": stop_on_manual_change,
            },
            interval,
            parent_context=call.context,
        )

    async def stop_dynamic_scene(call):
        scene_id = call.data.get(ATTR_DYNAMIC_SCENE_ID)
        dynamic_scene_manager.delete_by_id(scene_id)

    async def stop_dynamic_scenes_for_targets(call):
        targets = call.data.get(ATTR_TARGETS)

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))

        light_entity_ids = resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids)

        for light_entity_id in light_entity_ids:
            dynamic_scene_manager.stop_all_for_entity_id(light_entity_id)

        return True

    async def stop_all_dynamic_scenes(call):
        dynamic_scene_manager.stop_all()

    async def get_dynamic_scenes(call):
        return dynamic_scene_manager.get_all_as_dict()

    async def get_favorites(call):
        user_id = _get_call_user_id(call)
        return await async_get_favorites_response(favorites_store, user_id)

    async def is_favorite(call):
        user_id = _get_call_user_id(call)
        return await async_is_favorite_response(
            favorites_store,
            user_id,
            call.data.get(ATTR_SCENE_PRESET_ID),
        )

    async def add_favorite(call):
        user_id = _get_call_user_id(call)
        try:
            await favorites_store.async_add(user_id, call.data.get(ATTR_SCENE_PRESET_ID))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def remove_favorite(call):
        user_id = _get_call_user_id(call)
        try:
            await favorites_store.async_remove(user_id, call.data.get(ATTR_SCENE_PRESET_ID))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def toggle_favorite(call):
        user_id = _get_call_user_id(call)
        try:
            await favorites_store.async_toggle(user_id, call.data.get(ATTR_SCENE_PRESET_ID))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_PRESET,
        apply_preset_service,
        schema=APPLY_PRESET_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DYNAMIC_SCENES,
        get_dynamic_scenes,
        supports_response=SupportsResponse.ONLY
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_DYNAMIC_SCENE,
        start_dynamic_scene,
        schema=START_DYNAMIC_SCENE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_DYNAMIC_SCENE,
        stop_dynamic_scene,
        schema=STOP_DYNAMIC_SCENE_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS,
        stop_dynamic_scenes_for_targets,
        schema=STOP_DYNAMIC_SCENES_FOR_TARGETS_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL_DYNAMIC_SCENES,
        stop_all_dynamic_scenes,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FAVORITES,
        get_favorites,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IS_FAVORITE,
        is_favorite,
        schema=FAVORITE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FAVORITE,
        add_favorite,
        schema=FAVORITE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_FAVORITE,
        remove_favorite,
        schema=FAVORITE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TOGGLE_FAVORITE,
        toggle_favorite,
        schema=FAVORITE_SCHEMA,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    hass.data.setdefault(DOMAIN, {})

    await async_setup_view(hass)

    async_setup_websocket_api(
        hass,
        dynamic_scene_manager,
        _get_favorites_store(hass),
    )

    return True


async def async_remove_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    await async_remove_view(hass)
