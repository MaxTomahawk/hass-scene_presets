"""Helpers for detecting external color changes to dynamic scenes."""

from dataclasses import dataclass
import math

XY_TOLERANCE = 0.002
HS_TOLERANCE = 0.5
COLOR_TEMP_KELVIN_TOLERANCE = 20
RGB_TOLERANCE = 1
EXPECTED_MOVE_MARGIN_SECONDS = 1.0


@dataclass(frozen=True)
class ExpectedColorMove:
    """One color transition that a dynamic scene expects a light to report."""

    color_kind: str
    source_color: object
    target_color: object
    started_at: float
    transition: float
    acknowledge_until: float | None = None

    def is_active(self, now):
        """Return whether arbitrary transition progress can still be our own."""
        return now <= (
            self.started_at
            + max(float(self.transition or 0), 0.0)
            + EXPECTED_MOVE_MARGIN_SECONDS
        )

    def is_acknowledgement_active(self, now):
        """Return whether an exact target report can still acknowledge this move."""
        return (
            self.acknowledge_until is not None
            and now <= self.acknowledge_until
        )

    def is_relevant(self, now):
        """Return whether this move can still explain a device state report."""
        return self.is_active(now) or self.is_acknowledgement_active(now)


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


def _distance(value, target):
    if value is None or target is None:
        return None

    if isinstance(value, (list, tuple)) and isinstance(target, (list, tuple)):
        if len(value) != len(target):
            return None
        return math.sqrt(
            sum((float(a) - float(b)) ** 2 for a, b in zip(value, target))
        )

    try:
        return abs(float(value) - float(target))
    except (TypeError, ValueError):
        return 0.0 if value == target else None


def _state_value_for_expected_move(expected, attributes):
    if expected.color_kind == "xy":
        return _tuple_or_value(attributes.get("xy_color"))
    if expected.color_kind == "color_temp":
        return attributes.get("color_temp_kelvin")
    if expected.color_kind == "hs":
        return _tuple_or_value(attributes.get("hs_color"))
    if expected.color_kind == "rgb":
        return _tuple_or_value(attributes.get("rgb_color"))
    if expected.color_kind == "rgbw":
        return _tuple_or_value(
            attributes.get("rgbw_color", attributes.get("rgb_color"))
        )
    if expected.color_kind == "rgbww":
        return _tuple_or_value(
            attributes.get("rgbww_color", attributes.get("rgb_color"))
        )
    return None


def _progress_tolerance(expected):
    if expected.color_kind == "xy":
        return XY_TOLERANCE
    if expected.color_kind == "color_temp":
        return COLOR_TEMP_KELVIN_TOLERANCE
    if expected.color_kind == "hs":
        return HS_TOLERANCE
    return RGB_TOLERANCE


def is_expected_move_progress(expected, old_attributes, new_attributes, now):
    """Return True if a contextless state report is compatible with our move."""
    if expected is None:
        return False

    new_value = _state_value_for_expected_move(expected, new_attributes)
    if new_value is None:
        return False

    target_distance = _distance(new_value, expected.target_color)
    if target_distance is None:
        return False

    tolerance = _progress_tolerance(expected)

    # Device integrations can acknowledge the exact requested target well
    # after a short HA transition has completed. Keep that exact target valid
    # through the scene's acknowledgement window without treating arbitrary
    # intermediate colors as scene progress for the same duration.
    if target_distance <= tolerance:
        return (
            expected.is_active(now)
            or expected.is_acknowledgement_active(now)
        )

    if not expected.is_active(now):
        return False

    old_value = _state_value_for_expected_move(expected, old_attributes)
    reference = old_value if old_value is not None else expected.source_color
    reference_distance = _distance(reference, expected.target_color)
    if reference_distance is None:
        return False

    # Genuine scene progress must not move farther away from the target. A
    # small tolerance absorbs device-side conversion/rounding noise.
    return target_distance <= reference_distance + tolerance


def is_scene_context(context_id, parent_id, root_context_id, own_context_ids):
    """Return True when a state update belongs to this dynamic scene."""
    return (
        context_id == root_context_id
        or context_id in own_context_ids
        or parent_id == root_context_id
        or parent_id in own_context_ids
    )
