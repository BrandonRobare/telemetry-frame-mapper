from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

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

    config_path = Path(path).resolve()
    config_dir = config_path.parent
    for _field in ("imports_dir", "processed_dir", "exports_dir", "data_dir"):
        if _field in filtered:
            p = Path(str(filtered[_field]))
            if not p.is_absolute():
                filtered[_field] = str(config_dir / p)

    return AppConfig(**filtered)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config("config.yaml")


def reload_config() -> AppConfig:
    """Clear the lru_cache and return a fresh AppConfig from config.yaml."""
    get_config.cache_clear()
    return get_config()


def get_reconstruction_config(path: str = "config.yaml") -> dict:
    """Return the reconstruction section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults: dict = {
        "default_preset": "quick",
        "colmap_threads": 8,
        "sift_max_features": 8192,
        "matcher": "exhaustive",
        "camera_model": "PINHOLE",
        "presets": {
            "quick": {
                "iterations": 1000,
                "max_frames": 500,
                "exhaustive_matching": False,
                "max_gaussians": 350000,
                "sh_degree": 1,
                "downscale_factor": 4,
            },
            "full": {
                "iterations": 30000,
                "max_frames": None,
                "exhaustive_matching": True,
                "max_gaussians": 1000000,
                "sh_degree": 2,
                "downscale_factor": 2,
            },
        },
    }
    recon = data.get("reconstruction", {})
    merged = {**defaults, **recon}
    # Deep-merge presets: file overrides per-preset keys, defaults fill the rest.
    if "presets" in recon:
        merged_presets = {}
        for preset_name, preset_defaults in defaults["presets"].items():
            file_preset = recon["presets"].get(preset_name, {})
            merged_presets[preset_name] = {**preset_defaults, **file_preset}
        # Include any extra presets defined only in the file.
        for preset_name, preset_vals in recon["presets"].items():
            if preset_name not in merged_presets:
                merged_presets[preset_name] = preset_vals
        merged["presets"] = merged_presets
    return merged


def get_ingest_config(path: str = "config.yaml") -> dict:
    """Return the ingest section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults: dict = {
        "thumbnail_size_px": 200,
        "thumbnail_jpeg_quality": 75,
        "accepted_extensions": [".jpg", ".jpeg"],
        "blur_threshold": 100.0,
        "dark_threshold": 50.0,
        "bright_threshold": 210.0,
        "filter_zero_gps": True,
    }
    ingest = data.get("ingest", {})
    return {**defaults, **ingest}


def get_render_config(path: str = "config.yaml") -> dict:
    """Return the render section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults: dict = {
        "flythrough_fps": 30,
        "flythrough_width": 1920,
        "flythrough_height": 1080,
        "thumbnail_size_px": 512,
        "thumbnail_quality": 85,
        "lod_preview_ratio": 0.10,
        "lod_medium_ratio": 0.50,
    }
    render = data.get("render", {})
    return {**defaults, **render}
