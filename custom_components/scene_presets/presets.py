"""Apply Scene Presets to Home Assistant lights."""

from .color_moves import apply_light_moves, build_light_moves
from .file_utils import PRESET_DATA


async def apply_preset(
    hass,
    preset_id,
    light_entity_ids,
    transition,
    shuffle,
    smart_shuffle,
    brightness_override=None,
    context=None,
):
    """Build and execute a preset while keeping the public API compatible."""
    moves = build_light_moves(
        hass,
        preset_id,
        light_entity_ids,
        transition,
        shuffle,
        smart_shuffle,
        brightness_override,
    )
    await apply_light_moves(hass, moves, context=context)
    return moves
