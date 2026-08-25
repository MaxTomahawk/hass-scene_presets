from pathlib import Path
import runpy

import pytest


MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "scene_presets" / "favorite_logic.py"


def load_module():
    return runpy.run_path(str(MODULE_PATH))


def test_favorites_are_isolated_per_user_and_empty_set_initializes():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest", "Read", "Relax"})

    assert data.is_initialized("alice") is False
    data.set("alice", [])
    data.add("bob", "Rest")

    assert data.is_initialized("alice") is True
    assert data.get("alice") == []
    assert data.get("bob") == ["Rest"]


def test_favorites_are_deduplicated_in_stable_order():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest", "Read"})

    assert data.set("alice", ["Read", "Rest", "Read"]) == ["Read", "Rest"]


def test_add_remove_and_toggle_are_idempotent_and_predictable():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest", "Read"})

    assert data.add("alice", "Rest") == ["Rest"]
    assert data.add("alice", "Rest") == ["Rest"]
    assert data.remove("alice", "Read") == ["Rest"]
    assert data.toggle("alice", "Read") == ["Rest", "Read"]
    assert data.toggle("alice", "Read") == ["Rest"]
    assert data.remove("alice", "Rest") == []


def test_unknown_preset_is_rejected():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest"})

    with pytest.raises(ValueError, match="Unknown preset"):
        data.add("alice", "Missing")

    with pytest.raises(ValueError, match="Unknown preset"):
        data.set("alice", ["Rest", "Missing"])


def test_empty_initialization_does_not_create_sensor_user():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest"})

    data.set("alice", [])

    assert data.is_initialized("alice") is True
    assert data.sensor_user_ids() == []


def test_first_real_favorite_registers_sensor_user_permanently():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData({"Rest", "Relax"})

    data.add("alice", "Rest")
    assert data.sensor_user_ids() == ["alice"]

    data.remove("alice", "Rest")
    assert data.get("alice") == []
    assert data.sensor_user_ids() == ["alice"]


def test_existing_nonempty_favorites_upgrade_to_sensor_users():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData(
        {"Rest", "Relax"},
        {
            "users": {
                "alice": ["Rest"],
                "bob": [],
            }
        },
    )

    assert data.sensor_user_ids() == ["alice"]
    assert data.to_dict()["sensor_users"] == ["alice"]


def test_persisted_sensor_user_survives_empty_favorites():
    FavoritesData = load_module()["FavoritesData"]
    data = FavoritesData(
        {"Rest"},
        {
            "users": {"alice": []},
            "sensor_users": ["alice"],
        },
    )

    assert data.sensor_user_ids() == ["alice"]
