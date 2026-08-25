"""Plan and execute per-light Scene Presets moves."""

from dataclasses import dataclass
import asyncio
import random

import voluptuous as vol

from .color_management import (
    get_next_color,
    get_next_smart_random_color,
    get_random_color,
    get_randomized_colors,
)
from .color_temperature import find_closest_ct_match
from .file_utils import PRESET_DATA


@dataclass(frozen=True)
class LightMove:
    """One concrete service action plus its expected color transition."""

    entity_id: str
    service_data: dict
    color_kind: str | None
    source_color: object
    target_color: object
    transition: float


def _tuple_or_none(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def _find_preset(preset_id):
    for preset in PRESET_DATA.get("presets", []):
        if preset.get("id") == preset_id:
            return preset
    raise vol.Invalid(f"Preset '{preset_id}' not found.")


def build_light_moves(
    hass,
    preset_id,
    light_entity_ids,
    transition,
    shuffle,
    smart_shuffle,
    brightness_override=None,
):
    """Build immutable planned moves without mutating caller-owned targets."""
    preset_data = _find_preset(preset_id)
    brightness = (
        brightness_override
        if brightness_override is not None
        else preset_data.get("bri", 255)
    )
    preset_colors = [
        (light["x"], light["y"])
        for light in preset_data["lights"]
    ]

    entity_ids = list(light_entity_ids)
    randomized_colors = None
    if shuffle:
        randomized_colors = get_randomized_colors(preset_colors, len(entity_ids))
        random.shuffle(entity_ids)

    moves = []

    for index, entity_id in enumerate(entity_ids):
        hass_state = hass.states.get(entity_id)
        if not hass_state:
            continue

        if shuffle:
            current_color = hass_state.attributes.get("xy_color")
            if current_color is not None and smart_shuffle:
                next_color = get_next_smart_random_color(
                    current_color,
                    preset_colors,
                )
            elif randomized_colors is not None and index < len(randomized_colors):
                next_color = randomized_colors[index]
            else:
                next_color = get_random_color(preset_colors)
        else:
            next_color = get_next_color(index, preset_colors)

        light_params = {
            "brightness": brightness,
            "transition": transition,
            "entity_id": entity_id,
        }

        supported_color_modes = set(
            hass_state.attributes.get("supported_color_modes", []) or []
        )
        color_support = bool(
            supported_color_modes.intersection(
                {"xy", "hs", "rgb", "rgbw", "rgbww"}
            )
        )
        temp_support = "color_temp" in supported_color_modes
        brightness_support = "brightness" in supported_color_modes

        color_kind = None
        source_color = None
        target_color = None

        if color_support:
            target_color = tuple(next_color)
            source_color = _tuple_or_none(
                hass_state.attributes.get("xy_color")
            )
            color_kind = "xy"
            light_params["xy_color"] = next_color
        elif temp_support:
            target_color = find_closest_ct_match(next_color[0], next_color[1])
            source_color = hass_state.attributes.get("color_temp_kelvin")
            color_kind = "color_temp"
            light_params["color_temp_kelvin"] = target_color
        elif not brightness_support:
            continue

        moves.append(
            LightMove(
                entity_id=entity_id,
                service_data=light_params,
                color_kind=color_kind,
                source_color=source_color,
                target_color=target_color,
                transition=transition,
            )
        )

    return moves


async def apply_light_moves(hass, moves, context=None):
    """Execute planned moves while preserving one supplied Home Assistant context."""
    tasks = [
        hass.services.async_call(
            "light",
            "turn_on",
            dict(move.service_data),
            blocking=False,
            context=context,
        )
        for move in moves
    ]

    if tasks:
        await asyncio.gather(*tasks)
