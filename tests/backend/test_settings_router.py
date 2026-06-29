from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import backend.routers.settings as settings_mod
from backend.core.config import get_config


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """Point the settings router at a fresh temporary config.yaml."""
    cfg_file = tmp_path / "config.yaml"
    # Write the same defaults as config.yaml so tests start from a known state.
    defaults = {
        "altitude_ft": 200,
        "fov_horizontal_deg": 83,
        "fov_vertical_deg": 53,
        "image_width_px": 4000,
        "image_height_px": 3000,
        "desired_side_overlap": 0.70,
        "desired_forward_overlap": 0.80,
        "lane_spacing_ft": 105,
        "default_video_fps": 2.0,
        "target_crs": "EPSG:32617",
        "default_basemap": "esri_satellite",
        "basemap_providers": [
            {
                "id": "osm",
                "label": "OpenStreetMap",
                "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "© OSM",
                "offline": False,
            }
        ],
        "flight_log_match_tolerance_sec": 2.0,
        "battery_range_m": 3000,
        "mission_buffer_pct": 0.10,
        "thumbnail_size_px": 200,
        "imports_dir": "./imports",
        "processed_dir": "./processed",
        "exports_dir": "./exports",
        "data_dir": "./data",
    }
    cfg_file.write_text(yaml.safe_dump(defaults, sort_keys=False))
    # Point the router at the tmp file — all reads go through CONFIG_PATH.
    monkeypatch.setattr(settings_mod, "CONFIG_PATH", str(cfg_file))
    # Clear the lru_cache so it doesn't serve stale data from other tests.
    get_config.cache_clear()
    yield cfg_file
    get_config.cache_clear()


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------


def test_get_settings_has_all_five_sections(client, tmp_config):
    resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"general", "mission", "ingest", "reconstruction", "render"}


def test_get_settings_general_keys(client, tmp_config):
    data = client.get("/settings").json()
    general = data["general"]
    assert "default_basemap" in general
    assert "basemap_providers" in general
    assert "target_crs" in general
    assert "imports_dir" in general
    assert "processed_dir" in general
    assert "exports_dir" in general
    assert "data_dir" in general


def test_get_settings_mission_keys(client, tmp_config):
    data = client.get("/settings").json()
    mission = data["mission"]
    expected_keys = {
        "altitude_ft",
        "fov_horizontal_deg",
        "fov_vertical_deg",
        "image_width_px",
        "image_height_px",
        "desired_side_overlap",
        "desired_forward_overlap",
        "lane_spacing_ft",
        "default_video_fps",
        "battery_range_m",
        "mission_buffer_pct",
        "flight_log_match_tolerance_sec",
    }
    assert expected_keys == set(mission.keys())


def test_get_settings_no_derived_fields(client, tmp_config):
    """Derived fields (altitude_m, ground_width_m, etc.) must NOT appear in response."""
    data = client.get("/settings").json()
    # Flatten all values from all sections.
    all_keys = set()
    for section in data.values():
        if isinstance(section, dict):
            all_keys.update(section.keys())
    derived = {"altitude_m", "ground_width_m", "ground_height_m", "lane_spacing_m"}
    assert not (derived & all_keys), f"Derived fields present: {derived & all_keys}"


def test_get_settings_ingest_defaults(client, tmp_config):
    data = client.get("/settings").json()
    ingest = data["ingest"]
    assert ingest["thumbnail_size_px"] == 200
    assert ingest["thumbnail_jpeg_quality"] == 75
    assert ".jpg" in ingest["accepted_extensions"]
    assert ingest["blur_threshold"] == pytest.approx(100.0)
    assert ingest["dark_threshold"] == pytest.approx(50.0)
    assert ingest["bright_threshold"] == pytest.approx(210.0)
    assert ingest["filter_zero_gps"] is True


def test_get_settings_reconstruction_defaults(client, tmp_config):
    data = client.get("/settings").json()
    recon = data["reconstruction"]
    assert recon["colmap_threads"] == 8
    assert recon["sift_max_features"] == 8192
    assert "quick" in recon["presets"]
    assert "full" in recon["presets"]
    assert recon["presets"]["quick"]["iterations"] == 1000
    assert recon["presets"]["full"]["iterations"] == 30000


def test_get_settings_render_defaults(client, tmp_config):
    data = client.get("/settings").json()
    render = data["render"]
    assert render["flythrough_fps"] == 30
    assert render["flythrough_width"] == 1920
    assert render["flythrough_height"] == 1080
    assert render["thumbnail_size_px"] == 512
    assert render["thumbnail_quality"] == 85
    assert render["lod_preview_ratio"] == pytest.approx(0.10)
    assert render["lod_medium_ratio"] == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# PATCH /settings
# ---------------------------------------------------------------------------


def test_patch_mission_field_and_fresh_get_reflects_change(client, tmp_config):
    """PATCH a mission field → the response and a subsequent GET both show the new value."""
    resp = client.patch("/settings", json={"mission": {"altitude_ft": 300}})
    assert resp.status_code == 200
    assert resp.json()["mission"]["altitude_ft"] == 300.0

    # Verify the file was actually written.
    raw = yaml.safe_load(tmp_config.read_text())
    assert raw["altitude_ft"] == 300.0


def test_patch_ingest_section(client, tmp_config):
    resp = client.patch("/settings", json={"ingest": {"blur_threshold": 150.0}})
    assert resp.status_code == 200
    assert resp.json()["ingest"]["blur_threshold"] == pytest.approx(150.0)


def test_patch_render_section(client, tmp_config):
    resp = client.patch("/settings", json={"render": {"flythrough_fps": 60}})
    assert resp.status_code == 200
    assert resp.json()["render"]["flythrough_fps"] == 60


def test_patch_reconstruction_matcher(client, tmp_config):
    resp = client.patch("/settings", json={"reconstruction": {"matcher": "sequential"}})
    assert resp.status_code == 200
    assert resp.json()["reconstruction"]["matcher"] == "sequential"


def test_patch_reconstruction_preset_key(client, tmp_config):
    resp = client.patch(
        "/settings",
        json={"reconstruction": {"presets": {"quick": {"iterations": 500}}}},
    )
    assert resp.status_code == 200
    assert resp.json()["reconstruction"]["presets"]["quick"]["iterations"] == 500


def test_patch_general_field(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"target_crs": "EPSG:4326"}})
    assert resp.status_code == 200
    assert resp.json()["general"]["target_crs"] == "EPSG:4326"


# ---------------------------------------------------------------------------
# PATCH validation errors → 422
# ---------------------------------------------------------------------------


def test_patch_rejects_posix_root_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"imports_dir": "/"}})
    assert resp.status_code == 422


def test_patch_rejects_posix_system_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"exports_dir": "/etc"}})
    assert resp.status_code == 422


def test_patch_rejects_home_root_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"data_dir": str(Path.home())}})
    assert resp.status_code == 422


def test_patch_rejects_windows_system_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"processed_dir": "C:\\Windows"}})
    assert resp.status_code == 422


def test_patch_allows_safe_relative_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"imports_dir": "./safe/imports"}})
    assert resp.status_code == 200
    assert resp.json()["general"]["imports_dir"].endswith("safe/imports")


def test_patch_overlap_above_one_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"mission": {"desired_side_overlap": 1.5}})
    assert resp.status_code == 422


def test_patch_unknown_key_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"mission": {"nonexistent_field": 99}})
    assert resp.status_code == 422


def test_patch_unknown_top_level_key_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"totally_made_up": {"foo": "bar"}})
    assert resp.status_code == 422


def test_patch_derived_field_returns_422(client, tmp_config):
    """Attempting to set a derived/read-only field must return 422."""
    resp = client.patch("/settings", json={"general": {"altitude_m": 100}})
    assert resp.status_code == 422


def test_patch_derived_field_in_mission_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"mission": {"ground_width_m": 50}})
    assert resp.status_code == 422


def test_patch_invalid_matcher_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"reconstruction": {"matcher": "brute_force"}})
    assert resp.status_code == 422


def test_patch_mission_buffer_above_one_returns_422(client, tmp_config):
    resp = client.patch("/settings", json={"mission": {"mission_buffer_pct": 2.0}})
    assert resp.status_code == 422


def test_patch_invalid_camera_model_returns_422(client, tmp_config):
    """An unsupported camera model (e.g. OPENCV) must return 422."""
    resp = client.patch("/settings", json={"reconstruction": {"camera_model": "OPENCV"}})
    assert resp.status_code == 422


def test_patch_valid_camera_model_simple_pinhole_returns_200(client, tmp_config):
    """SIMPLE_PINHOLE is a valid camera model and must be accepted."""
    resp = client.patch("/settings", json={"reconstruction": {"camera_model": "SIMPLE_PINHOLE"}})
    assert resp.status_code == 200
    assert resp.json()["reconstruction"]["camera_model"] == "SIMPLE_PINHOLE"


# ---------------------------------------------------------------------------
# POST /settings/reset
# ---------------------------------------------------------------------------


def test_reset_restores_defaults(client, tmp_config):
    # Dirty the config first.
    client.patch("/settings", json={"mission": {"altitude_ft": 999}})
    raw_dirty = yaml.safe_load(tmp_config.read_text())
    assert raw_dirty["altitude_ft"] == 999.0

    resp = client.post("/settings/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mission"]["altitude_ft"] == 200.0


def test_reset_returns_full_response_shape(client, tmp_config):
    resp = client.post("/settings/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"general", "mission", "ingest", "reconstruction", "render"}
