from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.config import (
    AppConfig,
    default_ingest_config,
    default_reconstruction_config,
    default_render_config,
    get_config,
    get_ingest_config,
    get_reconstruction_config,
    get_render_config,
    load_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])

# Overridable for tests — point at a tmp file via monkeypatch.
CONFIG_PATH: str = "config.yaml"
_SETTINGS_MUTATION_LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# The set of derived (read-only) field names that MUST NOT be settable via API.
# ---------------------------------------------------------------------------
_DERIVED_FIELDS = frozenset(
    name for name, fld in AppConfig.__dataclass_fields__.items() if not fld.init
)

# ---------------------------------------------------------------------------
# Pydantic section models
# ---------------------------------------------------------------------------


class GeneralSettings(BaseModel):
    model_config = {"extra": "forbid"}

    default_basemap: str | None = None
    target_crs: str | None = None
    imports_dir: str | None = None
    processed_dir: str | None = None
    exports_dir: str | None = None
    data_dir: str | None = None
    basemap_providers: list[dict] | None = None

    @field_validator("imports_dir", "processed_dir", "exports_dir", "data_dir")
    @classmethod
    def validate_storage_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        _reject_unsafe_storage_path(v)
        return v


class MissionSettings(BaseModel):
    model_config = {"extra": "forbid"}

    altitude_ft: float | None = None
    fov_horizontal_deg: float | None = None
    fov_vertical_deg: float | None = None
    image_width_px: int | None = None
    image_height_px: int | None = None
    desired_side_overlap: float | None = Field(default=None, ge=0, le=1)
    desired_forward_overlap: float | None = Field(default=None, ge=0, le=1)
    lane_spacing_ft: float | None = None
    default_video_fps: float | None = Field(default=None, ge=1, le=60)
    battery_range_m: float | None = None
    mission_buffer_pct: float | None = Field(default=None, ge=0, le=1)
    flight_log_match_tolerance_sec: float | None = None


class IngestSettings(BaseModel):
    model_config = {"extra": "forbid"}

    thumbnail_size_px: int | None = Field(default=None, gt=0)
    thumbnail_jpeg_quality: int | None = Field(default=None, ge=1, le=100)
    accepted_extensions: list[str] | None = None
    blur_threshold: float | None = None
    dark_threshold: float | None = None
    bright_threshold: float | None = None
    filter_zero_gps: bool | None = None


class PresetSettings(BaseModel):
    model_config = {"extra": "forbid"}

    iterations: int | None = Field(default=None, gt=0)
    max_frames: int | None = Field(default=None, gt=0)
    max_gaussians: int | None = Field(default=None, gt=0)
    sh_degree: int | None = Field(default=None, ge=1, le=3)
    downscale_factor: int | None = Field(default=None, gt=0)
    exhaustive_matching: bool | None = None


class PresetsSettings(BaseModel):
    model_config = {"extra": "forbid"}

    quick: PresetSettings | None = None
    full: PresetSettings | None = None


class ReconstructionSettings(BaseModel):
    model_config = {"extra": "forbid"}

    default_preset: str | None = None
    colmap_threads: int | None = Field(default=None, gt=0)
    sift_max_features: int | None = Field(default=None, gt=0)
    matcher: str | None = None
    camera_model: str | None = None
    single_camera: bool | None = None
    presets: PresetsSettings | None = None

    @field_validator("matcher")
    @classmethod
    def validate_matcher(cls, v: str | None) -> str | None:
        if v is not None and v not in {"exhaustive", "sequential"}:
            raise ValueError("matcher must be 'exhaustive' or 'sequential'")
        return v

    @field_validator("camera_model")
    @classmethod
    def validate_camera_model(cls, v: str | None) -> str | None:
        if v is not None and v not in {"PINHOLE", "SIMPLE_PINHOLE"}:
            raise ValueError("camera_model must be 'PINHOLE' or 'SIMPLE_PINHOLE'")
        return v

    @field_validator("default_preset")
    @classmethod
    def validate_default_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in {"quick", "full"}:
            raise ValueError("default_preset must be 'quick' or 'full'")
        return v


class RenderSettings(BaseModel):
    model_config = {"extra": "forbid"}

    flythrough_fps: int | None = Field(default=None, ge=1, le=60)
    flythrough_width: int | None = Field(default=None, gt=0)
    flythrough_height: int | None = Field(default=None, gt=0)
    thumbnail_size_px: int | None = Field(default=None, gt=0)
    thumbnail_quality: int | None = Field(default=None, ge=1, le=100)
    lod_preview_ratio: float | None = Field(default=None, ge=0, le=1)
    lod_medium_ratio: float | None = Field(default=None, ge=0, le=1)


class SettingsPatch(BaseModel):
    """PATCH /settings body — all sections optional; unknown top-level keys → 422."""

    model_config = {"extra": "forbid"}

    general: GeneralSettings | None = None
    mission: MissionSettings | None = None
    ingest: IngestSettings | None = None
    reconstruction: ReconstructionSettings | None = None
    render: RenderSettings | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_derived_fields(cls, data: Any) -> Any:
        """Reject any attempt to set derived/read-only fields."""
        if isinstance(data, dict):
            for section_key in ("general", "mission"):
                section = data.get(section_key)
                if isinstance(section, dict):
                    bad = _DERIVED_FIELDS & section.keys()
                    if bad:
                        raise ValueError(
                            f"The following fields are derived and read-only: {sorted(bad)}"
                        )
        return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject_unsafe_storage_path(value: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise ValueError("storage paths cannot be empty")

    if stripped in {"/", "\\"}:
        raise ValueError("storage paths cannot point at root, home, or system directories")

    if stripped in {"~", "~/", "~\\"}:
        raise ValueError("storage paths cannot point at the home directory root")

    posix_path = PurePosixPath(stripped)
    blocked_posix = tuple(
        PurePosixPath(candidate)
        for candidate in ("/", "/etc", "/usr", "/bin", "/sbin", "/var", "/System", "/Windows")
    )
    if any(posix_path == blocked or blocked in posix_path.parents for blocked in blocked_posix):
        raise ValueError("storage paths cannot point at root, home, or system directories")

    path = Path(stripped).expanduser()
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise ValueError("storage path cannot be resolved") from exc

    home = Path.home().resolve()
    blocked = {
        home,
    }
    if resolved in blocked:
        raise ValueError("storage paths cannot point at root, home, or system directories")

    win_path = PureWindowsPath(stripped)
    win_text = stripped.replace("/", "\\").rstrip("\\").lower()
    if win_path.is_absolute():
        if win_path.parent == win_path or win_text.endswith(":"):
            raise ValueError("storage paths cannot point at a Windows drive root")
        blocked_windows = (
            "c:\\windows",
            "c:\\program files",
            "c:\\program files (x86)",
            "c:\\users",
        )
        # c:\users is matched exactly but NOT as a prefix: the Windows installer keeps
        # its data under %LOCALAPPDATA%, which lives inside a user profile. Sensitive
        # profile subdirectories are named individually below instead.
        if win_text in blocked_windows or any(
            win_text.startswith(prefix + "\\") for prefix in blocked_windows[:3]
        ):
            raise ValueError("storage paths cannot point at Windows system directories")

    _reject_sensitive_user_dir(resolved)


# Credential stores and auto-run locations. Pointing a storage root at one of these lets
# the app's own artifact writes land on keys or startup entries. Matched at any depth so
# "~/.ssh/keys" is rejected along with "~/.ssh".
_SENSITIVE_DIR_NAMES = frozenset(
    {".ssh", ".aws", ".gnupg", ".gcloud", ".azure", ".kube", ".docker", ".config"}
)
_SENSITIVE_DIR_SEGMENTS = (
    ("appdata", "roaming", "microsoft", "windows", "start menu", "programs", "startup"),
    ("library", "keychains"),
)


def _reject_sensitive_user_dir(resolved: Path) -> None:
    parts = [part.lower() for part in resolved.parts]
    if _SENSITIVE_DIR_NAMES.intersection(parts):
        raise ValueError("storage paths cannot point at credential or key directories")
    for segments in _SENSITIVE_DIR_SEGMENTS:
        window = len(segments)
        if any(
            tuple(parts[i : i + window]) == segments for i in range(len(parts) - window + 1)
        ):
            raise ValueError("storage paths cannot point at startup or keychain directories")


def _load_raw(path: str) -> dict:
    """Load raw config.yaml dict (empty dict if missing)."""
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _write_raw(path: str, data: dict) -> None:
    """Atomically replace config.yaml after its complete YAML reaches disk."""
    target = Path(path)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            yaml.safe_dump(
                data, temp, default_flow_style=False, sort_keys=False, allow_unicode=True
            )
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def _mutate_raw(path: str, mutation: Callable[[dict], dict]) -> dict:
    """Serialize a managed read/merge/write and invalidate cached app settings."""
    with _SETTINGS_MUTATION_LOCK:
        updated = mutation(_load_raw(path))
        _write_raw(path, updated)
        get_config.cache_clear()
        return updated


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_full_response() -> dict:
    """Build the full GET /settings response from live config."""
    cfg = load_config(CONFIG_PATH)
    recon_cfg = get_reconstruction_config(CONFIG_PATH)
    ingest_cfg = get_ingest_config(CONFIG_PATH)
    render_cfg = get_render_config(CONFIG_PATH)

    # General + mission keys come from AppConfig init fields (exclude derived).
    general_keys = {
        "default_basemap",
        "target_crs",
        "imports_dir",
        "processed_dir",
        "exports_dir",
        "data_dir",
        "basemap_providers",
    }
    mission_keys = {
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

    general = {k: getattr(cfg, k) for k in general_keys}
    mission = {k: getattr(cfg, k) for k in mission_keys}

    return {
        "general": general,
        "mission": mission,
        "ingest": ingest_cfg,
        "reconstruction": recon_cfg,
        "render": render_cfg,
    }


def _section_to_dict(section_model: BaseModel) -> dict:
    """Convert a Pydantic section model to a dict with only non-None values."""
    return {k: v for k, v in section_model.model_dump().items() if v is not None}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
def get_settings() -> dict:
    """Return the current configuration."""
    return _build_full_response()


@router.patch("")
def patch_settings(body: SettingsPatch) -> dict:
    """Deep-merge the partial body into config.yaml and return the full config."""

    # Build override dict from the validated body sections.
    override: dict = {}

    if body.general is not None:
        override.update(_section_to_dict(body.general))

    if body.mission is not None:
        override.update(_section_to_dict(body.mission))

    if body.ingest is not None:
        ingest_patch = _section_to_dict(body.ingest)
        if ingest_patch:
            override["ingest"] = ingest_patch

    if body.reconstruction is not None:
        recon_patch = {}
        for key in (
            "default_preset",
            "colmap_threads",
            "sift_max_features",
            "matcher",
            "camera_model",
            "single_camera",
        ):
            val = getattr(body.reconstruction, key)
            if val is not None:
                recon_patch[key] = val
        if body.reconstruction.presets is not None:
            presets_patch: dict = {}
            for preset_name in ("quick", "full"):
                preset_section = getattr(body.reconstruction.presets, preset_name)
                if preset_section is not None:
                    preset_vals = _section_to_dict(preset_section)
                    if preset_vals:
                        presets_patch[preset_name] = preset_vals
            if presets_patch:
                recon_patch["presets"] = presets_patch
        if recon_patch:
            override["reconstruction"] = recon_patch

    if body.render is not None:
        render_patch = _section_to_dict(body.render)
        if render_patch:
            override["render"] = render_patch

    _mutate_raw(CONFIG_PATH, lambda raw: _deep_merge(raw, override))

    return _build_full_response()


@router.post("/reset")
def reset_settings() -> dict:
    """Restore the settings this API manages to their defaults, and return the full config.

    Only the sections exposed by this router are reset. Security- and deployment-critical
    sections it never surfaces — ``deployment``, ``pin_lock``, ``api_key``, ``logging``,
    ``webodm``, ``remote_worker``, ``auto_import``, ``backup`` — are preserved verbatim.
    Resetting them here would silently disable the PIN lock on the next restart.
    """
    cfg = AppConfig()
    init_fields = {name for name, fld in AppConfig.__dataclass_fields__.items() if fld.init}
    app_defaults = {name: getattr(cfg, name) for name in init_fields}

    recon_defaults = default_reconstruction_config()
    ingest_defaults = default_ingest_config()
    render_defaults = default_render_config()

    def reset(raw: dict) -> dict:
        return {
            **raw,
            **app_defaults,
            "reconstruction": recon_defaults,
            "ingest": ingest_defaults,
            "render": render_defaults,
        }

    _mutate_raw(CONFIG_PATH, reset)

    return _build_full_response()
