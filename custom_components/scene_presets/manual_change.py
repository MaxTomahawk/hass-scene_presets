"""Helpers for detecting external color changes to dynamic scenes."""


def _tuple_or_value(value):
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def color_signature(attributes):
    """Return the effective color represented by Home Assistant attributes."""
    mode = attributes.get("color_mode")

    if mode == "color_temp":
        return mode, attributes.get("color_temp_kelvin")
    if mode == "xy":
        return mode, _tuple_or_value(attributes.get("xy_color"))
    if mode == "hs":
        return mode, _tuple_or_value(attributes.get("hs_color"))
    if mode == "rgb":
        return mode, _tuple_or_value(attributes.get("rgb_color"))
    if mode == "rgbw":
        return mode, _tuple_or_value(
            attributes.get("rgbw_color", attributes.get("rgb_color"))
        )
    if mode == "rgbww":
        return mode, _tuple_or_value(
            attributes.get("rgbww_color", attributes.get("rgb_color"))
        )

    # Modes such as onoff/brightness do not represent a color. Brightness is
    # deliberately excluded so dimming never counts as a manual color change.
    return mode, None


def color_changed(old_attributes, new_attributes):
    """Return True when the effective color or color mode changed."""
    return color_signature(old_attributes) != color_signature(new_attributes)


def is_scene_context(context_id, parent_id, root_context_id, own_context_ids):
    """Return True when a state update belongs to this dynamic scene."""
    return (
        context_id == root_context_id
        or context_id in own_context_ids
        or parent_id == root_context_id
        or parent_id in own_context_ids
    )
