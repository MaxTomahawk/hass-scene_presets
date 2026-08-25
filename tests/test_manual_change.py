from pathlib import Path
import runpy


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "scene_presets" / "manual_change.py"


def load_module():
    return runpy.run_path(str(MODULE_PATH))


def test_brightness_only_change_is_not_a_color_change():
    module = load_module()
    old = {"color_mode": "xy", "xy_color": [0.4, 0.3], "brightness": 60}
    new = {"color_mode": "xy", "xy_color": [0.4, 0.3], "brightness": 200}
    assert module["color_changed"](old, new) is False


def test_small_reporting_noise_is_not_a_color_change():
    module = load_module()
    color_changed = module["color_changed"]

    assert color_changed(
        {"color_mode": "xy", "xy_color": [0.4000, 0.3000]},
        {"color_mode": "xy", "xy_color": [0.4010, 0.2990]},
    ) is False
    assert color_changed(
        {"color_mode": "color_temp", "color_temp_kelvin": 3000},
        {"color_mode": "color_temp", "color_temp_kelvin": 3015},
    ) is False
    assert color_changed(
        {"color_mode": "rgb", "rgb_color": [255, 100, 50]},
        {"color_mode": "rgb", "rgb_color": [254, 101, 50]},
    ) is False


def test_xy_and_color_temperature_changes_are_color_changes():
    module = load_module()
    assert module["color_changed"](
        {"color_mode": "xy", "xy_color": [0.4, 0.3]},
        {"color_mode": "xy", "xy_color": [0.5, 0.3]},
    ) is True
    assert module["color_changed"](
        {"color_mode": "color_temp", "color_temp_kelvin": 2700},
        {"color_mode": "color_temp", "color_temp_kelvin": 4000},
    ) is True


def test_color_mode_change_is_a_color_change():
    module = load_module()
    assert module["color_changed"](
        {"color_mode": "color_temp", "color_temp_kelvin": 2700},
        {"color_mode": "xy", "xy_color": [0.4, 0.3]},
    ) is True


def test_scene_context_recognizes_own_root_and_child_parent_ids():
    module = load_module()
    own = {"step-a", "step-b"}
    is_scene_context = module["is_scene_context"]

    assert is_scene_context("step-a", None, "root", own) is True
    assert is_scene_context("derived", "root", "root", own) is True
    assert is_scene_context("derived", "step-b", "root", own) is True
    assert is_scene_context("external", None, "root", own) is False


def test_contextless_xy_report_is_accepted_only_when_it_moves_toward_target():
    module = load_module()
    ExpectedColorMove = module["ExpectedColorMove"]
    expected = ExpectedColorMove(
        color_kind="xy",
        source_color=(0.40, 0.30),
        target_color=(0.60, 0.50),
        started_at=100.0,
        transition=45.0,
    )

    assert module["is_expected_move_progress"](
        expected,
        {"xy_color": [0.40, 0.30]},
        {"xy_color": [0.48, 0.38]},
        now=110.0,
    ) is True
    assert module["is_expected_move_progress"](
        expected,
        {"xy_color": [0.48, 0.38]},
        {"xy_color": [0.60, 0.50]},
        now=130.0,
    ) is True
    assert module["is_expected_move_progress"](
        expected,
        {"xy_color": [0.48, 0.38]},
        {"xy_color": [0.20, 0.65]},
        now=130.0,
    ) is False


def test_contextless_color_temperature_progress_and_stale_reports():
    module = load_module()
    ExpectedColorMove = module["ExpectedColorMove"]
    expected = ExpectedColorMove(
        color_kind="color_temp",
        source_color=2700,
        target_color=4000,
        started_at=100.0,
        transition=20.0,
    )

    assert module["is_expected_move_progress"](
        expected,
        {"color_temp_kelvin": 2700},
        {"color_temp_kelvin": 3300},
        now=110.0,
    ) is True
    assert module["is_expected_move_progress"](
        expected,
        {"color_temp_kelvin": 3300},
        {"color_temp_kelvin": 3800},
        now=125.0,
    ) is False
