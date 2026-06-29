from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

_DISTORTION_CAMERA_MODELS = {"SIMPLE_RADIAL", "RADIAL", "OPENCV", "FULL_OPENCV"}
_DISTORTION_LENS_HINTS = ("wide", "fisheye", "equiv", "efl", "zoom")


@dataclass(frozen=True)
class CameraProfile:
    """Per-camera/lens calibration settings used to seed COLMAP intrinsics."""

    name: str
    make: str | None = None
    model: str | None = None
    lens_model: str | None = None
    sensor_width_mm: float | None = None
    sensor_height_mm: float | None = None
    focal_length_mm: float | None = None
    fov_horizontal_deg: float | None = None
    fov_vertical_deg: float | None = None
    colmap_camera_model: str | None = None
    calibration_params: list[float] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraProfile:
        return cls(
            name=str(data.get("name") or _profile_name(data)),
            make=_clean(data.get("make")),
            model=_clean(data.get("model")),
            lens_model=_clean(data.get("lens_model")),
            sensor_width_mm=_positive_float(data.get("sensor_width_mm")),
            sensor_height_mm=_positive_float(data.get("sensor_height_mm")),
            focal_length_mm=_positive_float(data.get("focal_length_mm")),
            fov_horizontal_deg=_angle(data.get("fov_horizontal_deg")),
            fov_vertical_deg=_angle(data.get("fov_vertical_deg")),
            colmap_camera_model=_clean(data.get("colmap_camera_model")),
            calibration_params=[float(v) for v in data.get("calibration_params") or []] or None,
        )


def default_camera_profiles() -> list[dict[str, Any]]:
    """Built-in drone camera profiles that are safe to expose/edit in config."""

    return [
        {
            "name": "DJI Mini 3/4 Pro wide camera",
            "make": "DJI",
            "model": "FC3582",
            "lens_model": "24mm F1.7",
            "sensor_width_mm": 6.4,
            "sensor_height_mm": 4.8,
            "focal_length_mm": 6.72,
            "fov_horizontal_deg": 73.4,
            "fov_vertical_deg": 52.2,
            "colmap_camera_model": "PINHOLE",
        },
        {
            "name": "DJI Air 2S wide camera",
            "make": "DJI",
            "model": "FC3411",
            "sensor_width_mm": 13.2,
            "sensor_height_mm": 8.8,
            "focal_length_mm": 8.4,
            "fov_horizontal_deg": 76.5,
            "fov_vertical_deg": 55.3,
            "colmap_camera_model": "PINHOLE",
        },
        {
            "name": "DJI Mavic 3 wide camera",
            "make": "DJI",
            "model": "L2D-20c",
            "sensor_width_mm": 17.3,
            "sensor_height_mm": 13.0,
            "focal_length_mm": 12.29,
            "fov_horizontal_deg": 70.3,
            "fov_vertical_deg": 55.8,
            "colmap_camera_model": "PINHOLE",
        },
    ]


def normalize_profiles(raw_profiles: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_profiles, list):
        return default_camera_profiles()
    normalized: list[dict[str, Any]] = []
    for item in raw_profiles:
        if not isinstance(item, dict):
            continue
        profile = CameraProfile.from_dict(item)
        data: dict[str, Any] = {"name": profile.name}
        for key in (
            "make",
            "model",
            "lens_model",
            "sensor_width_mm",
            "sensor_height_mm",
            "focal_length_mm",
            "fov_horizontal_deg",
            "fov_vertical_deg",
            "colmap_camera_model",
            "calibration_params",
        ):
            value = getattr(profile, key)
            if value is not None:
                data[key] = value
        normalized.append(data)
    return normalized or default_camera_profiles()


def match_camera_profile(image: Any, profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    image_make = _norm(getattr(image, "camera_make", None))
    image_model = _norm(getattr(image, "camera_model", None))
    image_lens = _norm(getattr(image, "lens_model", None))
    best: tuple[int, dict[str, Any]] | None = None
    for raw_profile in profiles:
        profile = CameraProfile.from_dict(raw_profile)
        score = 0
        if profile.make and _matches(profile.make, image_make):
            score += 2
        elif profile.make:
            continue
        if profile.model and _matches(profile.model, image_model):
            score += 4
        elif profile.model:
            continue
        if profile.lens_model and _matches(profile.lens_model, image_lens):
            score += 3
        elif profile.lens_model:
            continue
        if score and (best is None or score > best[0]):
            best = (score, raw_profile)
    return best[1] if best else None


def suggest_colmap_camera_model(image: Any, profile: dict[str, Any] | None = None) -> str:
    configured = _clean((profile or {}).get("colmap_camera_model"))
    if configured:
        return configured.upper()
    lens = " ".join(
        str(v or "")
        for v in (
            getattr(image, "lens_model", None),
            getattr(image, "camera_model", None),
        )
    ).lower()
    if any(hint in lens for hint in _DISTORTION_LENS_HINTS):
        return "SIMPLE_RADIAL"
    if getattr(image, "focal_length_mm", None):
        return "PINHOLE"
    return "SIMPLE_PINHOLE"


def focal_pixels_from_metadata(
    image: Any,
    profile: dict[str, Any] | None,
    fallback_fov_deg: float,
) -> float | None:
    width = _positive_float(getattr(image, "width", None))
    if width is None:
        return None
    profile_obj = CameraProfile.from_dict(profile or {}) if profile else None
    focal_mm = _positive_float(getattr(image, "focal_length_mm", None))
    if focal_mm is None and profile_obj:
        focal_mm = profile_obj.focal_length_mm
    sensor_width = profile_obj.sensor_width_mm if profile_obj else None
    if focal_mm and sensor_width:
        return width * focal_mm / sensor_width
    fov = fallback_fov_deg
    if profile_obj and profile_obj.fov_horizontal_deg:
        fov = profile_obj.fov_horizontal_deg
    return (width / 2.0) / math.tan(math.radians(fov / 2.0)) if fov else None


def calibration_profile_for_images(
    images: list[Any],
    profiles: list[dict[str, Any]],
    configured_width: int,
    configured_height: int,
    configured_fov_horizontal_deg: float,
    configured_fov_vertical_deg: float,
    configured_camera_model: str,
) -> dict[str, Any]:
    """Summarize metadata/profile match and warnings for a reconstruction image set."""

    first = next(
        (
            img
            for img in images
            if _positive_float(getattr(img, "width", None))
            and _positive_float(getattr(img, "height", None))
        ),
        None,
    )
    image_for_profile = first or (images[0] if images else None)
    profile = match_camera_profile(image_for_profile, profiles) if image_for_profile else None
    width = configured_width
    height = configured_height
    if first:
        width = int(_positive_float(getattr(first, "width", None)) or configured_width)
        height = int(_positive_float(getattr(first, "height", None)) or configured_height)
    focal_px = None
    suggested_model = configured_camera_model
    if image_for_profile:
        focal_px = focal_pixels_from_metadata(
            image_for_profile,
            profile,
            configured_fov_horizontal_deg,
        )
        suggested_model = suggest_colmap_camera_model(image_for_profile, profile)
    warnings = dimension_fov_warnings(
        images,
        configured_width,
        configured_height,
        configured_fov_horizontal_deg,
        configured_fov_vertical_deg,
        profile,
    )
    return {
        "profile": profile,
        "suggested_colmap_camera_model": suggested_model,
        "configured_colmap_camera_model": configured_camera_model,
        "width": width,
        "height": height,
        "focal_px": focal_px,
        "warnings": warnings,
    }


def dimension_fov_warnings(
    images: list[Any],
    configured_width: int,
    configured_height: int,
    configured_fov_horizontal_deg: float,
    configured_fov_vertical_deg: float,
    profile: dict[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []
    dimensions = {
        (int(getattr(img, "width", 0) or 0), int(getattr(img, "height", 0) or 0))
        for img in images
        if _positive_float(getattr(img, "width", None))
        and _positive_float(getattr(img, "height", None))
    }
    if dimensions:
        if len(dimensions) > 1:
            warnings.append(f"Imported images have mixed dimensions: {sorted(dimensions)}")
        width, height = sorted(dimensions)[0]
        width_mismatch = abs(width - configured_width) > max(16, configured_width * 0.01)
        height_mismatch = abs(height - configured_height) > max(16, configured_height * 0.01)
        if width_mismatch or height_mismatch:
            warnings.append(
                f"Configured image size {configured_width}x{configured_height} "
                f"does not match imported images {width}x{height}"
            )
    if profile:
        h_fov = _angle(profile.get("fov_horizontal_deg"))
        v_fov = _angle(profile.get("fov_vertical_deg"))
        if h_fov and abs(h_fov - configured_fov_horizontal_deg) > 5:
            warnings.append(
                f"Configured horizontal FOV {configured_fov_horizontal_deg:.1f}° "
                f"differs from profile {h_fov:.1f}°"
            )
        if v_fov and abs(v_fov - configured_fov_vertical_deg) > 5:
            warnings.append(
                f"Configured vertical FOV {configured_fov_vertical_deg:.1f}° "
                f"differs from profile {v_fov:.1f}°"
            )
    return warnings


def _profile_name(data: dict[str, Any]) -> str:
    parts = (str(data.get(k) or "").strip() for k in ("make", "model", "lens_model"))
    return " ".join(parts).strip() or "Camera profile"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_float(value: Any) -> float | None:
    if value is None or not isinstance(value, int | float | str):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _angle(value: Any) -> float | None:
    parsed = _positive_float(value)
    return parsed if parsed is not None and parsed < 180 else None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _matches(needle: str, haystack: str) -> bool:
    n = _norm(needle)
    return bool(n and haystack and (n == haystack or n in haystack or haystack in n))
