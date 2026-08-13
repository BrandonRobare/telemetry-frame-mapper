from __future__ import annotations

import sys
import threading
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


def test_patch_reconstruction_can_opt_into_per_camera_estimates(client, tmp_config):
    resp = client.patch("/settings", json={"reconstruction": {"single_camera": False}})

    assert resp.status_code == 200
    assert resp.json()["reconstruction"]["single_camera"] is False


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


def test_concurrent_disjoint_patches_preserve_both_changes(tmp_config, monkeypatch):
    """A settings mutation cannot overwrite another mutation's fresh read."""
    dump = settings_mod.yaml.safe_dump
    rendezvous = threading.Barrier(2, timeout=0.2)

    def pause_both_writers(*args, **kwargs):
        try:
            rendezvous.wait()
        except threading.BrokenBarrierError:
            pass
        return dump(*args, **kwargs)

    monkeypatch.setattr(settings_mod.yaml, "safe_dump", pause_both_writers)
    errors = []
    patches = (
        settings_mod.SettingsPatch(mission=settings_mod.MissionSettings(altitude_ft=301)),
        settings_mod.SettingsPatch(general=settings_mod.GeneralSettings(target_crs="EPSG:4326")),
    )

    def patch(body):
        try:
            settings_mod.patch_settings(body)
        except Exception as exc:  # pragma: no cover - assertion below reports failures
            errors.append(exc)

    threads = [threading.Thread(target=patch, args=(body,)) for body in patches]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    after = yaml.safe_load(tmp_config.read_text())
    assert after["altitude_ft"] == 301
    assert after["target_crs"] == "EPSG:4326"


def test_patch_response_read_does_not_overlap_another_promote(tmp_config, monkeypatch):
    """Windows cannot replace config.yaml while a response is reading it."""
    load_config = settings_mod.load_config
    replace = settings_mod.os.replace
    reader_active = threading.Event()
    release_reader = threading.Event()
    promote_during_read = threading.Event()
    hold_once = threading.Lock()
    errors = []

    def pause_first_response_read(path):
        if hold_once.acquire(blocking=False):
            reader_active.set()
            assert release_reader.wait(timeout=1)
            reader_active.clear()
        return load_config(path)

    def reject_windows_conflicting_promote(source, destination):
        if Path(destination) == tmp_config and reader_active.is_set():
            promote_during_read.set()
            raise PermissionError(13, "Access is denied", str(destination))
        return replace(source, destination)

    monkeypatch.setattr(settings_mod, "load_config", pause_first_response_read)
    monkeypatch.setattr(settings_mod.os, "replace", reject_windows_conflicting_promote)

    def patch(body):
        try:
            settings_mod.patch_settings(body)
        except Exception as exc:  # pragma: no cover - assertion below reports failures
            errors.append(exc)

    first = threading.Thread(
        target=patch,
        args=(settings_mod.SettingsPatch(mission=settings_mod.MissionSettings(altitude_ft=301)),),
    )
    first.start()
    assert reader_active.wait(timeout=1)

    second = threading.Thread(
        target=patch,
        args=(settings_mod.SettingsPatch(general=settings_mod.GeneralSettings(target_crs="EPSG:4326")),),
    )
    second.start()
    promote_during_read.wait(timeout=0.2)
    release_reader.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert not promote_during_read.is_set()
    assert not errors


def test_reset_response_read_does_not_overlap_another_promote(tmp_config, monkeypatch):
    """reset_settings keeps its response read under the mutation lock too."""
    load_config = settings_mod.load_config
    replace = settings_mod.os.replace
    reader_active = threading.Event()
    release_reader = threading.Event()
    promote_during_read = threading.Event()
    errors = []

    def pause_response_read(path):
        reader_active.set()
        assert release_reader.wait(timeout=1)
        reader_active.clear()
        return load_config(path)

    def reject_windows_conflicting_promote(source, destination):
        if Path(destination) == tmp_config and reader_active.is_set():
            promote_during_read.set()
            raise PermissionError(13, "Access is denied", str(destination))
        return replace(source, destination)

    monkeypatch.setattr(settings_mod, "load_config", pause_response_read)
    monkeypatch.setattr(settings_mod.os, "replace", reject_windows_conflicting_promote)

    def reset():
        try:
            settings_mod.reset_settings()
        except Exception as exc:  # pragma: no cover - assertion below reports failures
            errors.append(exc)

    first = threading.Thread(target=reset)
    first.start()
    assert reader_active.wait(timeout=1)

    def patch():
        try:
            settings_mod.patch_settings(
                settings_mod.SettingsPatch(general=settings_mod.GeneralSettings(target_crs="EPSG:4326"))
            )
        except Exception as exc:  # pragma: no cover - assertion below reports failures
            errors.append(exc)

    second = threading.Thread(target=patch)
    second.start()
    promote_during_read.wait(timeout=0.2)
    release_reader.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert not promote_during_read.is_set()
    assert not errors


def test_failed_serialization_preserves_previous_parseable_config(tmp_config, monkeypatch):
    before = tmp_config.read_text()

    def fail_dump(*args, **kwargs):
        raise TypeError("simulated serialization failure")

    monkeypatch.setattr(settings_mod.yaml, "safe_dump", fail_dump)
    with pytest.raises(TypeError, match="simulated serialization failure"):
        settings_mod.patch_settings(
            settings_mod.SettingsPatch(mission=settings_mod.MissionSettings(altitude_ft=301))
        )

    assert tmp_config.read_text() == before
    assert yaml.safe_load(tmp_config.read_text())["altitude_ft"] == 200
    assert not list(tmp_config.parent.glob(f".{tmp_config.name}.*.tmp"))


# ---------------------------------------------------------------------------
# PATCH validation errors → 422
# ---------------------------------------------------------------------------


def test_patch_rejects_posix_root_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"imports_dir": "/"}})
    assert resp.status_code == 422


def test_patch_rejects_posix_system_storage_path(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"exports_dir": "/etc"}})
    assert resp.status_code == 422


def test_patch_rejects_posix_system_storage_descendant(client, tmp_config):
    resp = client.patch("/settings", json={"general": {"exports_dir": "/etc/telemetry"}})
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
    assert Path(resp.json()["general"]["imports_dir"]).parts[-2:] == ("safe", "imports")


@pytest.mark.parametrize("path", ["/", "\\"])
def test_patch_rejects_slash_root_storage_path(client, tmp_config, path):
    resp = client.patch("/settings", json={"general": {"imports_dir": path}})
    assert resp.status_code == 422


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


def test_reset_uses_explicit_defaults_without_creating_sentinel_file(client, tmp_config):
    sentinel = tmp_config.with_name(".settings-reset-empty.yaml")

    resp = client.post("/settings/reset")

    assert resp.status_code == 200
    assert not sentinel.exists()
    assert resp.json()["reconstruction"]["default_preset"] == "quick"


def test_reset_returns_full_response_shape(client, tmp_config):
    resp = client.post("/settings/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"general", "mission", "ingest", "reconstruction", "render"}


# ---------------------------------------------------------------------------
# Security regressions
# ---------------------------------------------------------------------------


def test_reset_preserves_security_and_deployment_sections(client, tmp_config):
    """POST /settings/reset must not disable the PIN lock.

    reset_settings rewrites config.yaml from defaults. It used to build that dict
    without reading the existing file, so every section this router does not manage
    — pin_lock, api_key, deployment, logging, backup, ... — was silently dropped and
    the lock was gone on the next restart.
    """
    raw = yaml.safe_load(tmp_config.read_text()) or {}
    raw["pin_lock"] = {"enabled": True, "hash_env": "DRONE_MAPPING_PIN_HASH"}
    raw["api_key"] = {"enabled": True, "hash_env": "DRONE_MAPPING_API_KEY_HASH"}
    raw["deployment"] = {"host": "192.168.1.50", "port": 8000, "cors_origins": ["http://x:5173"]}
    raw["logging"] = {"enabled": True, "level": "DEBUG"}
    raw["backup"] = {"local_destinations": ["E:/telemetry-backups"]}
    tmp_config.write_text(yaml.safe_dump(raw))

    resp = client.post("/settings/reset")
    assert resp.status_code == 200

    after = yaml.safe_load(tmp_config.read_text())
    assert after["pin_lock"]["enabled"] is True
    assert after["api_key"]["enabled"] is True
    assert after["deployment"]["host"] == "192.168.1.50"
    assert after["logging"]["level"] == "DEBUG"
    assert after["backup"]["local_destinations"] == ["E:/telemetry-backups"]


# These use *relative* paths on purpose. An absolute POSIX path is already rejected
# wholesale on Linux, because blocked_posix contains "/" and "/" is a parent of every
# absolute path — so an absolute-path test would pass on CI without exercising the
# credential-directory check at all, and would fail on Windows-shaped input.
# Relative paths resolve against cwd identically on both platforms.
@pytest.mark.parametrize(
    "field,value",
    [
        ("exports_dir", "./storage/.ssh"),
        ("data_dir", "./storage/.ssh/keys"),
        ("imports_dir", "./storage/.aws"),
        ("processed_dir", "./storage/.gnupg"),
        ("exports_dir", "./storage/AppData/Roaming/Microsoft/Windows/"
                        "Start Menu/Programs/Startup"),
    ],
)
def test_patch_rejects_credential_directories(client, tmp_config, field, value):
    """Storage roots widen every containment check, so they must not land on key stores.

    The Windows blocklist matches the users directory exactly but deliberately not as a
    prefix, because %LOCALAPPDATA% (where the installer keeps its data) lives inside
    a user profile. That left ~/.ssh reachable as an exports root.
    """
    resp = client.patch("/settings", json={"general": {field: value}})
    assert resp.status_code == 422


def test_patch_still_allows_app_data_style_layout(client, tmp_config):
    # The installer's own %LOCALAPPDATA%\Telemetry Frame Mapper layout must keep working:
    # the fix must not reject a path merely for sitting under a user profile.
    target = "./storage/AppData/Local/Telemetry Frame Mapper/imports"
    resp = client.patch("/settings", json={"general": {"imports_dir": target}})
    assert resp.status_code == 200


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-shaped absolute paths")
@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\pilot\.ssh",
        r"C:\Users\pilot\.aws\credentials",
        r"C:\Users\pilot\AppData\Roaming\Microsoft\Windows"
        r"\Start Menu\Programs\Startup",
    ],
)
def test_patch_rejects_windows_credential_directories(client, tmp_config, value):
    resp = client.patch("/settings", json={"general": {"exports_dir": value}})
    assert resp.status_code == 422


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-shaped absolute paths")
def test_patch_allows_windows_local_app_data(client, tmp_config):
    value = r"C:\Users\pilot\AppData\Local\Telemetry Frame Mapper\imports"
    resp = client.patch("/settings", json={"general": {"imports_dir": value}})
    assert resp.status_code == 200
