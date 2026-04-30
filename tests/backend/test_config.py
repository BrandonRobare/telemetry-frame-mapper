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
