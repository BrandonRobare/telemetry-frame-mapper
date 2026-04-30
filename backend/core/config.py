from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

import yaml


@dataclass
class AppConfig:
    altitude_ft: float = 200
    fov_horizontal_deg: float = 83
    fov_vertical_deg: float = 53
    image_width_px: int = 4000
    image_height_px: int = 3000
    desired_side_overlap: float = 0.70
    desired_forward_overlap: float = 0.80
    lane_spacing_ft: float = 105
    default_video_fps: float = 2.0
    target_crs: str = "EPSG:32617"
    default_basemap: str = "esri_satellite"
    flight_log_match_tolerance_sec: float = 2.0
    battery_range_m: float = 3000
    mission_buffer_pct: float = 0.10
    thumbnail_size_px: int = 200
    imports_dir: str = "./imports"
    processed_dir: str = "./processed"
    exports_dir: str = "./exports"
    data_dir: str = "./data"

    altitude_m: float = field(init=False)
    ground_width_m: float = field(init=False)
    ground_height_m: float = field(init=False)
    lane_spacing_m: float = field(init=False)

    def __post_init__(self):
        self.altitude_m = self.altitude_ft * 0.3048
        self.ground_width_m = 2 * self.altitude_m * math.tan(
            math.radians(self.fov_horizontal_deg / 2)
        )
        self.ground_height_m = 2 * self.altitude_m * math.tan(
            math.radians(self.fov_vertical_deg / 2)
        )
        self.lane_spacing_m = self.ground_width_m * (1 - self.desired_side_overlap)


def load_config(path: str = "config.yaml") -> AppConfig:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    init_fields = {
        f for f in AppConfig.__dataclass_fields__
        if AppConfig.__dataclass_fields__[f].init
    }
    filtered = {k: v for k, v in data.items() if k in init_fields}
    return AppConfig(**filtered)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config("config.yaml")
