from custom_components.scene_presets.color_management import (
    get_next_smart_random_color,
    white_point,
)


def test_smart_shuffle_handles_current_color_at_white_point():
    options = [(0.5, 0.4), (0.2, 0.3)]

    result = get_next_smart_random_color(white_point, options)

    assert result in options


def test_smart_shuffle_handles_target_color_at_white_point():
    options = [white_point, (0.5, 0.4)]

    result = get_next_smart_random_color((0.4, 0.3), options)

    assert result in options
