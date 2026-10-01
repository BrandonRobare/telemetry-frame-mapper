from __future__ import annotations

import os

import cv2
import numpy as np

BLUR_THRESHOLD = 100.0
DARK_THRESHOLD = 50.0
BRIGHT_THRESHOLD = 210.0


def _ingest_thresholds() -> tuple[float, float, float]:
    """Return (blur, dark, bright) thresholds from config, falling back to module constants."""
    try:
        from backend.core.config import get_ingest_config

        cfg = get_ingest_config()
        return (
            float(cfg.get("blur_threshold", BLUR_THRESHOLD)),
            float(cfg.get("dark_threshold", DARK_THRESHOLD)),
            float(cfg.get("bright_threshold", BRIGHT_THRESHOLD)),
        )
    except Exception:  # pragma: no cover
        return BLUR_THRESHOLD, DARK_THRESHOLD, BRIGHT_THRESHOLD


def _read_grayscale(filepath: str) -> np.ndarray:
    img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
    if img is None:
        # A stand-in score would be flagged as if it were measured (#943).
        raise ValueError(f"OpenCV could not decode {os.path.basename(filepath)}")
    return img


def score_sharpness(filepath: str) -> float:
    """Laplacian variance — higher means sharper. Raises ValueError on read failure."""
    img = _read_grayscale(filepath)
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def score_brightness(filepath: str) -> float:
    """Mean grayscale pixel value 0–255. Raises ValueError on read failure."""
    img = _read_grayscale(filepath)
    return float(np.mean(img))


def flag_image(sharpness: float, brightness: float, has_gps: bool) -> str:
    """Return quality flag. Priority: no_gps > blurry > dark > bright > good."""
    blur_threshold, dark_threshold, bright_threshold = _ingest_thresholds()
    if not has_gps:
        return "no_gps"
    if sharpness < blur_threshold:
        return "blurry"
    if brightness < dark_threshold:
        return "dark"
    if brightness > bright_threshold:
        return "bright"
    return "good"
