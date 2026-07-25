from __future__ import annotations

import pytest

from backend.core.config import load_config


def test_load_config_defaults():
    cfg = load_config("config.yaml")
    assert cfg.altitude_ft == 200
    assert cfg.altitude_m == pytest.approx(60.96, abs=0.1)
    assert cfg.fov_horizontal_deg == 83
    assert cfg.target_crs == "EPSG:32617"


def test_lane_spacing_m():
    cfg = load_config("config.yaml")
    assert cfg.lane_spacing_m == pytest.approx(32.25, abs=1.0)


def test_ground_dimensions():
    cfg = load_config("config.yaml")
    assert cfg.ground_width_m == pytest.approx(107.5, abs=2.0)
    assert cfg.ground_height_m == pytest.approx(60.8, abs=2.0)


def test_get_reconstruction_config_defaults():
    from backend.core.config import get_reconstruction_config
    cfg = get_reconstruction_config()
    assert "presets" in cfg
    assert "quick" in cfg["presets"]
    assert "full" in cfg["presets"]
    assert cfg["presets"]["quick"]["iterations"] == 1000
    assert cfg["presets"]["full"]["iterations"] == 30000
    assert cfg["colmap_threads"] == 8
    assert cfg["sift_max_features"] == 8192
    assert cfg["single_camera"] is True
    assert cfg["dense_rerun"] == {
        "min_weak_run_frames": 2,
        "high_reprojection_error_px": 2.0,
        "context_frames": 1,
    }


def test_get_reconstruction_config_preset_values():
    from backend.core.config import get_reconstruction_config
    cfg = get_reconstruction_config()
    quick = cfg["presets"]["quick"]
    assert quick["max_frames"] == 500
    assert quick["exhaustive_matching"] is False
    full = cfg["presets"]["full"]
    assert full["max_frames"] is None
    assert full["exhaustive_matching"] is True


def test_get_backup_config_reads_only_configured_destinations(tmp_path):
    from backend.core.config import get_backup_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "backup:\n  local_destinations:\n    - E:/telemetry-backups\n"
        "  rclone_remote: archive:telemetry\n"
    )

    assert get_backup_config(str(path)) == {
        "local_destinations": ["E:/telemetry-backups"],
        "rclone_remote": "archive:telemetry",
    }


def test_deployment_config_defaults_to_loopback_and_local_frontends(tmp_path):
    from backend.core.config import get_deployment_config

    assert get_deployment_config(str(tmp_path / "missing.yaml")) == {
        "host": "127.0.0.1",
        "port": 8000,
        "cors_origins": ["http://localhost:5173", "http://localhost:3000"],
        "allow_unauthenticated_lan": False,
        "allowed_hosts": [],
    }


def test_deployment_config_accepts_explicit_lan_bind_and_origins(tmp_path):
    from backend.core.config import get_deployment_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "deployment:\n"
        "  host: 192.168.1.50\n"
        "  port: '8080'\n"
        "  allow_unauthenticated_lan: true\n"
        "  cors_origins:\n"
        "    - http://192.168.1.50:5173/\n"
    )

    assert get_deployment_config(str(path)) == {
        "host": "192.168.1.50",
        "port": 8080,
        "cors_origins": ["http://192.168.1.50:5173"],
        "allow_unauthenticated_lan": True,
        "allowed_hosts": [],
    }


def test_deployment_config_refuses_lan_bind_without_auth(tmp_path):
    from backend.core.config import get_deployment_config

    path = tmp_path / "config.yaml"
    path.write_text("deployment:\n  host: 0.0.0.0\n")

    with pytest.raises(ValueError, match="not loopback but no authentication"):
        get_deployment_config(str(path))


def test_deployment_config_lan_bind_allowed_with_pin_lock(tmp_path, monkeypatch):
    from backend.core.config import get_deployment_config
    from backend.services.share_links import hash_password

    path = tmp_path / "config.yaml"
    path.write_text(
        "deployment:\n  host: 192.168.1.50\n"
        "pin_lock:\n  enabled: true\n  pin_hash_env: TEST_PIN_HASH\n"
    )
    monkeypatch.setenv("TEST_PIN_HASH", hash_password("1234"))

    assert get_deployment_config(str(path))["host"] == "192.168.1.50"


@pytest.mark.parametrize(
    "deployment",
    [
        "host: http://bad.example",
        "host: true",
        "port: 0",
        "cors_origins: ['*']",
        "cors_origins: ['http://example.test/path']",
        "cors_origins: ['http://user@example.test']",
        "cors_origins: ['http://example.test:99999']",
    ],
)
def test_deployment_config_rejects_invalid_values(tmp_path, deployment):
    from backend.core.config import get_deployment_config

    path = tmp_path / "config.yaml"
    path.write_text(f"deployment:\n  {deployment}\n")

    with pytest.raises(ValueError, match="deployment"):
        get_deployment_config(str(path))
