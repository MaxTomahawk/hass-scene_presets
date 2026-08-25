from pathlib import Path
import runpy


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "custom_components" / "scene_presets"


def test_favorite_constants_include_set_and_explicit_user_fields():
    constants = runpy.run_path(str(PACKAGE / "const.py"))

    assert constants["SERVICE_SET_FAVORITES"] == "set_favorites"
    assert constants["ATTR_USER_ID"] == "user_id"
    assert constants["ATTR_FAVORITES"] == "favorites"


def test_services_yaml_exposes_set_and_user_id_on_all_favorite_actions():
    services = (PACKAGE / "services.yaml").read_text()

    assert "\nset_favorites:\n" in services
    favorite_section = services.split("\nget_favorites:\n", 1)[1]
    assert favorite_section.count("\n    user_id:\n") == 6


def test_service_registration_wires_set_favorites_and_explicit_user_resolution():
    source = (PACKAGE / "__init__.py").read_text()

    assert "SET_FAVORITES_SCHEMA" in source
    assert "SERVICE_SET_FAVORITES" in source
    assert "async_resolve_favorite_user_id" in source
    assert "call.data.get(ATTR_USER_ID)" in source
