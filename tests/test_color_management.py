import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "scene_presets"
    / "color_management.py"
)

spec = importlib.util.spec_from_file_location("scene_presets_color_management", MODULE_PATH)
color_management = importlib.util.module_from_spec(spec)
spec.loader.exec_module(color_management)


def test_smart_shuffle_handles_current_color_at_white_point():
    options = [(0.5, 0.4), (0.2, 0.3)]

    result = color_management.get_next_smart_random_color(
        color_management.white_point,
        options,
    )

    assert result in options


def test_smart_shuffle_handles_target_color_at_white_point():
    options = [color_management.white_point, (0.5, 0.4)]

    result = color_management.get_next_smart_random_color((0.4, 0.3), options)

    assert result in options
