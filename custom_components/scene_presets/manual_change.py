"""Helpers for detecting external color changes to dynamic scenes."""

XY_TOLERANCE = 0.002
HS_TOLERANCE = 0.5
COLOR_TEMP_KELVIN_TOLERANCE = 20
RGB_TOLERANCE = 1


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

    # Modes such as onoff/brightness/white do not expose an independent color
    # value here. Brightness is deliberately excluded so dimming never counts
    # as a manual color change.
    return mode, None


def _number_changed(old_value, new_value, tolerance):
    if old_value is None or new_value is None:
        return old_value != new_value

    try:
        return abs(float(old_value) - float(new_value)) > tolerance
    except (TypeError, ValueError):
        return old_value != new_value


def _sequence_changed(old_value, new_value, tolerance):
    if old_value is None or new_value is None:
        return old_value != new_value

    if len(old_value) != len(new_value):
        return True

    return any(
        _number_changed(old_component, new_component, tolerance)
        for old_component, new_component in zip(old_value, new_value)
    )


def color_changed(old_attributes, new_attributes):
    """Return True when the effective color changed beyond reporting noise."""
    old_mode = old_attributes.get("color_mode")
    new_mode = new_attributes.get("color_mode")

    if old_mode != new_mode:
        return True

    if new_mode == "color_temp":
        return _number_changed(
            old_attributes.get("color_temp_kelvin"),
            new_attributes.get("color_temp_kelvin"),
            COLOR_TEMP_KELVIN_TOLERANCE,
        )

    if new_mode == "xy":
        return _sequence_changed(
            old_attributes.get("xy_color"),
            new_attributes.get("xy_color"),
            XY_TOLERANCE,
        )

    if new_mode == "hs":
        return _sequence_changed(
            old_attributes.get("hs_color"),
            new_attributes.get("hs_color"),
            HS_TOLERANCE,
        )

    if new_mode == "rgb":
        return _sequence_changed(
            old_attributes.get("rgb_color"),
            new_attributes.get("rgb_color"),
            RGB_TOLERANCE,
        )

    if new_mode == "rgbw":
        return _sequence_changed(
            old_attributes.get("rgbw_color", old_attributes.get("rgb_color")),
            new_attributes.get("rgbw_color", new_attributes.get("rgb_color")),
            RGB_TOLERANCE,
        )

    if new_mode == "rgbww":
        return _sequence_changed(
            old_attributes.get("rgbww_color", old_attributes.get("rgb_color")),
            new_attributes.get("rgbww_color", new_attributes.get("rgb_color")),
            RGB_TOLERANCE,
        )

    return False


def is_scene_context(context_id, parent_id, root_context_id, own_context_ids):
    """Return True when a state update belongs to this dynamic scene."""
    return (
        context_id == root_context_id
        or context_id in own_context_ids
        or parent_id == root_context_id
        or parent_id in own_context_ids
    )
