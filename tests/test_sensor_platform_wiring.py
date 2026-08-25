from pathlib import Path


INIT_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "scene_presets"
    / "__init__.py"
)


def test_config_entry_forwards_and_unloads_sensor_platform():
    source = INIT_PATH.read_text()

    assert 'async_forward_entry_setups(entry, ["sensor"])' in source
    assert 'async_unload_platforms(entry, ["sensor"])' in source
