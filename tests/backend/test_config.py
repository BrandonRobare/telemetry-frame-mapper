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
