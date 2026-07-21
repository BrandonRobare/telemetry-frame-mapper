from __future__ import annotations

import ipaddress
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from backend.core.application_logging import logging_config
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
    rth_altitude_ft: float = 100
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
        "single_camera": True,
        "dense_rerun": {
            "min_weak_run_frames": 2,
            "high_reprojection_error_px": 2.0,
            "context_frames": 1,
        },
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


def get_remote_worker_config(path: str = "config.yaml") -> dict:
    """Return the explicitly opt-in network reconstruction worker settings.

    The token itself is never kept in YAML: ``auth_token_env`` names the
    environment variable that holds it.  HTTPS is required unless an operator
    deliberately opts into HTTP for an isolated development network.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "enabled": False,
        "url": "",
        "auth_token_env": "REMOTE_WORKER_TOKEN",
        "timeout_seconds": 10,
        "poll_interval_seconds": 2,
        "allow_insecure_http": False,
    }
    configured = data.get("remote_worker", {})
    if not isinstance(configured, dict):
        return defaults
    result = {**defaults, **configured}
    result["enabled"] = bool(result["enabled"])
    result["url"] = str(result["url"]).rstrip("/")
    result["auth_token_env"] = str(result["auth_token_env"])
    result["allow_insecure_http"] = bool(result["allow_insecure_http"])
    for key in ("timeout_seconds", "poll_interval_seconds"):
        try:
            result[key] = max(1, int(result[key]))
        except (TypeError, ValueError):
            result[key] = defaults[key]
    return result


def get_webodm_config(path: str = "config.yaml") -> dict:
    """Return the explicitly opt-in WebODM connection settings.

    ``jwt_env`` names an environment variable; the JWT itself is deliberately
    never read from or written to YAML.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "enabled": False,
        "url": "",
        "jwt_env": "WEBODM_JWT",
        "timeout_seconds": 30,
        "allow_insecure_http": False,
    }
    configured = data.get("webodm", {})
    if not isinstance(configured, dict):
        return defaults
    result = {**defaults, **configured}
    result["enabled"] = bool(result["enabled"])
    result["url"] = str(result["url"]).rstrip("/")
    result["jwt_env"] = str(result["jwt_env"])
    result["allow_insecure_http"] = bool(result["allow_insecure_http"])
    try:
        result["timeout_seconds"] = max(1, int(result["timeout_seconds"]))
    except (TypeError, ValueError):
        result["timeout_seconds"] = defaults["timeout_seconds"]
    return result


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


def get_auto_import_config(path: str = "config.yaml") -> dict:
    """Return the opt-in SD-card/watch-folder import configuration.

    This deliberately lives outside the normal import paths: watched folders are
    an explicit allowlist and are never inferred from a mounted drive.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "enabled": False,
        "roots": [],
        "poll_interval_seconds": 10,
        "stable_seconds": 30,
    }
    configured = data.get("auto_import", {})
    if not isinstance(configured, dict):
        return defaults
    result = {**defaults, **configured}
    result["enabled"] = bool(result["enabled"])
    roots = result["roots"]
    if isinstance(roots, list):
        result["roots"] = [str(root) for root in roots if isinstance(root, str)]
    else:
        result["roots"] = []
    try:
        result["poll_interval_seconds"] = max(1, int(result["poll_interval_seconds"]))
    except (TypeError, ValueError):
        result["poll_interval_seconds"] = defaults["poll_interval_seconds"]
    try:
        result["stable_seconds"] = max(0, int(result["stable_seconds"]))
    except (TypeError, ValueError):
        result["stable_seconds"] = defaults["stable_seconds"]
    return result


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


def get_backup_config(path: str = "config.yaml") -> dict:
    """Return the secret-free destinations allowed for artifact backups."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {"local_destinations": [], "rclone_remote": ""}
    backup = data.get("backup", {})
    return {**defaults, **backup}


def get_backup_schedule_config(path: str = "config.yaml") -> dict:
    """Return the opt-in daily backup schedule without exposing target values."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    backup = data.get("backup", {})
    schedule = backup.get("schedule", {}) if isinstance(backup, dict) else {}
    defaults = {"enabled": False, "target": "", "daily_at": "02:00"}
    return {**defaults, **schedule} if isinstance(schedule, dict) else defaults


def get_logging_config(path: str = "config.yaml") -> dict:
    """Return validated local application logging settings from config.yaml."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    return logging_config(data, path)


def get_deployment_config(path: str = "config.yaml") -> dict:
    """Return the validated bind and CORS settings for ``python -m backend``."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "host": "127.0.0.1",
        "port": 8000,
        "cors_origins": ["http://localhost:5173", "http://localhost:3000"],
        "allow_unauthenticated_lan": False,
    }
    deployment = data.get("deployment", {})
    if not isinstance(deployment, dict):
        return defaults
    result = {**defaults, **deployment}
    if not isinstance(result["host"], str):
        raise ValueError("deployment.host must be an IP address or hostname")
    host = result["host"].strip()
    host_is_loopback = host == "localhost"
    try:
        host_is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError as exc:
        allowed_hostname_chars = "-.abcdefghijklmnopqrstuvwxyz0123456789"
        labels = host.split(".")
        if (
            not host
            or any(char not in allowed_hostname_chars for char in host.lower())
            or any(not label or label.startswith("-") or label.endswith("-") for label in labels)
        ):
            raise ValueError("deployment.host must be an IP address or hostname") from exc
    result["host"] = host
    if not isinstance(result["allow_unauthenticated_lan"], bool):
        raise ValueError("deployment.allow_unauthenticated_lan must be true or false")
    # Refuse to bind a non-loopback interface with no authentication in front of the
    # otherwise-unauthenticated API, unless the operator explicitly opts in.
    if not host_is_loopback and not result["allow_unauthenticated_lan"]:
        if not (get_pin_lock_config(path)["enabled"] or get_api_key_config(path)["enabled"]):
            raise ValueError(
                f"deployment.host {host!r} is not loopback but no authentication is enabled. "
                "Enable pin_lock (or api_key), bind to 127.0.0.1, or set "
                "deployment.allow_unauthenticated_lan: true to override."
            )
    if isinstance(result["port"], bool):
        raise ValueError("deployment.port must be an integer from 1 to 65535")
    try:
        result["port"] = int(result["port"])
    except (TypeError, ValueError) as exc:
        raise ValueError("deployment.port must be an integer from 1 to 65535") from exc
    if not 1 <= result["port"] <= 65535:
        raise ValueError("deployment.port must be an integer from 1 to 65535")
    origins = result["cors_origins"]
    if not isinstance(origins, list) or not origins:
        raise ValueError("deployment.cors_origins must be a non-empty list of HTTP origins")
    for origin in origins:
        if not isinstance(origin, str):
            raise ValueError("deployment.cors_origins must contain HTTP(S) origins without paths")
        parsed = urlparse(origin)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(
                "deployment.cors_origins must contain HTTP(S) origins without paths"
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or port is not None and not 1 <= port <= 65535
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("deployment.cors_origins must contain HTTP(S) origins without paths")
    result["cors_origins"] = [origin.rstrip("/") for origin in origins]
    return result


def get_cesium_ion_config(path: str = "config.yaml") -> dict:
    """Return the explicitly opt-in Cesium ion upload settings, without its token."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {
        "enabled": False,
        "api_url": "https://api.cesium.com/v1",
        "token_env": "CESIUM_ION_TOKEN",
        "timeout_seconds": 60,
        "allow_insecure_http": False,
    }
    configured = data.get("cesium_ion", {})
    if not isinstance(configured, dict):
        return defaults
    result = {**defaults, **configured}
    result["enabled"] = bool(result["enabled"])
    result["api_url"] = str(result["api_url"]).rstrip("/")
    result["token_env"] = str(result["token_env"])
    result["allow_insecure_http"] = bool(result["allow_insecure_http"])
    try:
        result["timeout_seconds"] = max(1, int(result["timeout_seconds"]))
    except (TypeError, ValueError):
        result["timeout_seconds"] = defaults["timeout_seconds"]
    return result


def get_pin_lock_config(path: str = "config.yaml") -> dict:
    """Return the opt-in, single-user local PIN lock configuration.

    The PIN hash stays in the named environment variable, never in YAML.
    Enabled-but-unusable configuration is rejected at startup rather than
    accidentally exposing the app without a lock.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {"enabled": False, "pin_hash_env": "DRONE_MAPPING_PIN_HASH", "session_ttl": 28800}
    configured = data.get("pin_lock", {})
    if not isinstance(configured, dict):
        raise ValueError("pin_lock must be a mapping")
    result = {**defaults, **configured}
    if not isinstance(result["enabled"], bool):
        raise ValueError("pin_lock.enabled must be true or false")
    if not isinstance(result["pin_hash_env"], str) or not result["pin_hash_env"].strip():
        raise ValueError("pin_lock.pin_hash_env must name an environment variable")
    if isinstance(result["session_ttl"], bool):
        raise ValueError("pin_lock.session_ttl must be an integer of at least 60 seconds")
    try:
        result["session_ttl"] = int(result["session_ttl"])
    except (TypeError, ValueError) as exc:
        raise ValueError("pin_lock.session_ttl must be an integer of at least 60 seconds") from exc
    if result["session_ttl"] < 60:
        raise ValueError("pin_lock.session_ttl must be an integer of at least 60 seconds")
    if result["enabled"]:
        pin_hash = os.environ.get(result["pin_hash_env"])
        try:
            salt, digest = pin_hash.split("$", 1) if pin_hash else ("", "")
            if len(bytes.fromhex(salt)) != 16 or len(bytes.fromhex(digest)) != 64:
                raise ValueError
        except ValueError as exc:
            raise ValueError(
                f"pin_lock requires {result['pin_hash_env']} to contain a valid scrypt hash"
            ) from exc
    return result


def get_api_key_config(path: str = "config.yaml") -> dict:
    """Return the optional automation key configuration for a PIN-locked app."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    defaults = {"enabled": False, "key_hash_env": "DRONE_MAPPING_API_KEY_HASH"}
    configured = data.get("api_key", {})
    if not isinstance(configured, dict):
        raise ValueError("api_key must be a mapping")
    result = {**defaults, **configured}
    if not isinstance(result["enabled"], bool):
        raise ValueError("api_key.enabled must be true or false")
    if not isinstance(result["key_hash_env"], str) or not result["key_hash_env"].strip():
        raise ValueError("api_key.key_hash_env must name an environment variable")
    if result["enabled"]:
        if not get_pin_lock_config(path)["enabled"]:
            raise ValueError("api_key.enabled requires pin_lock.enabled")
        key_hash = os.environ.get(result["key_hash_env"])
        try:
            salt, digest = key_hash.split("$", 1) if key_hash else ("", "")
            if len(bytes.fromhex(salt)) != 16 or len(bytes.fromhex(digest)) != 64:
                raise ValueError
        except ValueError as exc:
            raise ValueError(
                f"api_key requires {result['key_hash_env']} to contain a valid scrypt hash"
            ) from exc
    return result
