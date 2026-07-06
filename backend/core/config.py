from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from backend.services.camera_calibration import default_camera_profiles, normalize_profiles


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
    basemap_providers: list[dict] = field(
        default_factory=lambda: [
            {
                "id": "esri_satellite",
                "label": "Esri Satellite",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "attribution": "© Esri",
                "offline": False,
            },
            {
                "id": "osm",
                "label": "OpenStreetMap",
                "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "© OpenStreetMap contributors",
                "offline": False,
            },
            {
                "id": "offline_mbtiles",
                "label": "Offline MBTiles/local tiles",
                "url": "/tiles/{z}/{x}/{y}.png",
                "attribution": "Local tiles",
                "offline": True,
            },
        ]
    )
    flight_log_match_tolerance_sec: float = 2.0
    dji_api_key_path: str = ""
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
        self.ground_width_m = (
            2 * self.altitude_m * math.tan(math.radians(self.fov_horizontal_deg / 2))
        )
        self.ground_height_m = (
            2 * self.altitude_m * math.tan(math.radians(self.fov_vertical_deg / 2))
        )
        self.lane_spacing_m = self.ground_width_m * (1 - self.desired_side_overlap)


def load_config(path: str = "config.yaml") -> AppConfig:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    init_fields = {
        f for f in AppConfig.__dataclass_fields__ if AppConfig.__dataclass_fields__[f].init
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


def default_reconstruction_config() -> dict:
    """Return reconstruction defaults without reading config.yaml."""
    return _reconstruction_config_from_data({})


def _reconstruction_config_from_data(data: dict) -> dict:
    defaults: dict = {
        "default_preset": "quick",
        "colmap_threads": 8,
        "sift_max_features": 8192,
        "matcher": "exhaustive",
        "mapper": "incremental",
        "spatial_matcher_min_images": 150,
        "camera_model": "PINHOLE",
        "camera_profiles": default_camera_profiles(),
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
    merged["camera_profiles"] = normalize_profiles(merged.get("camera_profiles"))
    return merged


def get_reconstruction_config(path: str = "config.yaml") -> dict:
    """Return the reconstruction section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    return _reconstruction_config_from_data(data)


def default_ingest_config() -> dict:
    """Return ingest defaults without reading config.yaml."""
    return _ingest_config_from_data({})


def _ingest_config_from_data(data: dict) -> dict:
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


def get_ingest_config(path: str = "config.yaml") -> dict:
    """Return the ingest section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    return _ingest_config_from_data(data)


def default_render_config() -> dict:
    """Return render defaults without reading config.yaml."""
    return _render_config_from_data({})


def _render_config_from_data(data: dict) -> dict:
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


def get_render_config(path: str = "config.yaml") -> dict:
    """Return the render section from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    return _render_config_from_data(data)


def get_upload_limits_config(path: str = "config.yaml") -> dict:
    """Return upload size limits from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "flight_log_max_bytes": 10 * 1024 * 1024,
        "srt_max_bytes": 10 * 1024 * 1024,
    }
    upload_limits = data.get("upload_limits", {})
    return {**defaults, **upload_limits}


def get_dji_api_key(config_path: str = "config.yaml") -> str | None:
    """Return the DJI API key from the configured file path or env var.

    Priority: ``DJI_API_KEY`` env var → file at ``dji_api_key_path``.
    Returns *None* when no key is available.
    """
    env_val = os.environ.get("DJI_API_KEY", "").strip()
    if env_val:
        return env_val

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return None

    key_path = data.get("dji_api_key_path", "")
    if not key_path:
        return None

    try:
        with open(key_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def get_browser_upload_config(path: str = "config.yaml") -> dict:
    """Return browser image upload safeguards from config.yaml with defaults applied."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "chunk_size_bytes": 2 * 1024 * 1024,
        "max_file_bytes": 50 * 1024 * 1024,
        "max_total_bytes": 2 * 1024 * 1024 * 1024,
        "quota_bytes": 10 * 1024 * 1024 * 1024,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg", ".jpeg"],
    }
    browser_uploads = data.get("browser_uploads", {})
    return {**defaults, **browser_uploads}
