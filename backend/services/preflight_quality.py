from __future__ import annotations

from collections import Counter
from datetime import datetime

from shapely import wkt
from shapely.ops import unary_union
from sqlalchemy.orm import Session as DBSession

from backend.db.models import Footprint, Image, Session
from backend.services.quality import BRIGHT_THRESHOLD, DARK_THRESHOLD, _ingest_thresholds

_DUPLICATE_TIMESTAMP_EPSILON_S = 0.001
_COVERAGE_MIN_FOOTPRINTS = 3
_COVERAGE_MIN_OVERLAP_RATIO = 0.15
_COVERAGE_HIGH_OVERLAP_RATIO = 0.85
_TIMESTAMP_GAP_MULTIPLIER = 3.0
_TIMESTAMP_GAP_MIN_SECONDS = 2.0


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100.0, 1)


def _histogram(values: list[float], bins: list[float]) -> list[dict]:
    if not bins or len(bins) < 2:
        return []
    counts = [0 for _ in range(len(bins) - 1)]
    for value in values:
        for index in range(len(bins) - 1):
            lower = bins[index]
            upper = bins[index + 1]
            if lower <= value < upper or (index == len(bins) - 2 and value == upper):
                counts[index] += 1
                break
    return [
        {"min": bins[index], "max": bins[index + 1], "count": counts[index]}
        for index in range(len(counts))
    ]


def _timestamp_seconds(ts: datetime) -> float:
    if ts.tzinfo is None:
        return ts.timestamp()
    return ts.timestamp()


def _timestamp_quality(images: list[Image]) -> dict:
    timestamps = [img.timestamp for img in images if img.timestamp is not None]
    seconds = sorted(_timestamp_seconds(ts) for ts in timestamps)
    duplicate_groups = 0
    duplicate_frames = 0
    if seconds:
        current_count = 1
        previous = seconds[0]
        for value in seconds[1:]:
            if abs(value - previous) <= _DUPLICATE_TIMESTAMP_EPSILON_S:
                current_count += 1
            else:
                if current_count > 1:
                    duplicate_groups += 1
                    duplicate_frames += current_count
                current_count = 1
            previous = value
        if current_count > 1:
            duplicate_groups += 1
            duplicate_frames += current_count

    intervals = [round(seconds[i] - seconds[i - 1], 3) for i in range(1, len(seconds))]
    positive_intervals = [gap for gap in intervals if gap > _DUPLICATE_TIMESTAMP_EPSILON_S]
    typical_gap = min(positive_intervals) if positive_intervals else None
    gap_threshold = None
    gaps = []
    if typical_gap is not None:
        gap_threshold = max(_TIMESTAMP_GAP_MIN_SECONDS, typical_gap * _TIMESTAMP_GAP_MULTIPLIER)
        gaps = [gap for gap in positive_intervals if gap > gap_threshold]

    return {
        "missing": len(images) - len(timestamps),
        "completeness_pct": _pct(len(timestamps), len(images)),
        "duplicate_groups": duplicate_groups,
        "duplicate_frames": duplicate_frames,
        "gap_count": len(gaps),
        "max_gap_s": round(max(gaps), 3) if gaps else 0.0,
        "typical_gap_s": round(typical_gap, 3) if typical_gap is not None else None,
        "gap_threshold_s": round(gap_threshold, 3) if gap_threshold is not None else None,
    }


def _gps_quality(images: list[Image]) -> dict:
    complete = [
        img for img in images
        if img.latitude is not None and img.longitude is not None
    ]
    return {
        "missing": len(images) - len(complete),
        "completeness_pct": _pct(len(complete), len(images)),
    }


def _image_quality(images: list[Image]) -> dict:
    blur_threshold, dark_threshold, bright_threshold = _ingest_thresholds()
    sharpness_values = [
        float(img.sharpness_score) for img in images if img.sharpness_score is not None
    ]
    brightness_values = [
        float(img.brightness_score) for img in images if img.brightness_score is not None
    ]
    flag_counts = Counter(img.flag or "unknown" for img in images)
    blurry = sum(1 for value in sharpness_values if value < blur_threshold)
    dark = sum(1 for value in brightness_values if value < dark_threshold)
    bright = sum(1 for value in brightness_values if value > bright_threshold)
    return {
        "blur_threshold": blur_threshold,
        "dark_threshold": dark_threshold,
        "bright_threshold": bright_threshold,
        "blur_count": blurry,
        "dark_count": dark,
        "bright_count": bright,
        "blur_pct": _pct(blurry, len(images)),
        "dark_pct": _pct(dark, len(images)),
        "bright_pct": _pct(bright, len(images)),
        "flag_counts": dict(flag_counts),
        "sharpness_histogram": _histogram(
            sharpness_values, [0, 25, 50, 100, 200, 500, 1000, 5000]
        ),
        "brightness_histogram": _histogram(
            brightness_values, [0, DARK_THRESHOLD, 85, 128, 170, BRIGHT_THRESHOLD, 255]
        ),
    }


def _coverage_quality(db: DBSession, images: list[Image]) -> dict:
    image_ids = [img.id for img in images]
    footprints = []
    if image_ids:
        footprints = db.query(Footprint).filter(Footprint.image_id.in_(image_ids)).all()

    geometries = []
    for footprint in footprints:
        if not footprint.geom_wkt:
            continue
        try:
            geom = wkt.loads(footprint.geom_wkt)
        except Exception:
            continue
        if not geom.is_empty and geom.area > 0:
            geometries.append(geom)

    footprint_count = len(geometries)
    area_sum = sum(geom.area for geom in geometries)
    union_area = unary_union(geometries).area if geometries else 0.0
    overlap_area = max(0.0, area_sum - union_area)
    overlap_ratio = (overlap_area / area_sum) if area_sum > 0 else None
    warnings = []
    if footprint_count < min(_COVERAGE_MIN_FOOTPRINTS, len(images)):
        warnings.append("Not enough footprints to estimate overlap or coverage")
    elif overlap_ratio is not None and overlap_ratio < _COVERAGE_MIN_OVERLAP_RATIO:
        warnings.append(
            "Low estimated overlap; add more overlapping flight lines or reduce frame spacing"
        )
    elif overlap_ratio is not None and overlap_ratio > _COVERAGE_HIGH_OVERLAP_RATIO:
        warnings.append(
            "Very high overlap; consider using fewer frames for a faster reconstruction"
        )

    footprint_pct = _pct(footprint_count, len(images))
    if images and footprint_pct < 80:
        warnings.append("Coverage estimate is incomplete because many frames lack footprints")

    return {
        "footprint_count": footprint_count,
        "footprint_coverage_pct": footprint_pct,
        "estimated_overlap_pct": (
            round(overlap_ratio * 100.0, 1) if overlap_ratio is not None else None
        ),
        "union_area": round(union_area, 3),
        "summed_footprint_area": round(area_sum, 3),
        "warnings": warnings,
    }


def build_preflight_quality_report(session_id: int, db: DBSession) -> dict:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise ValueError("Session not found")

    images = db.query(Image).filter(Image.session_id == session_id).order_by(Image.id).all()
    total = len(images)
    usable_images = [img for img in images if img.usable]
    gps = _gps_quality(usable_images)
    timestamps = _timestamp_quality(usable_images)
    quality = _image_quality(usable_images)
    coverage = _coverage_quality(db, usable_images)

    warnings: list[str] = []
    score = 100

    if len(usable_images) < 3:
        warnings.append("At least 3 usable frames are recommended before reconstruction")
        score -= 45
    if gps["completeness_pct"] < 90:
        warnings.append(
            "GPS completeness is low; sync a flight log or remove frames without coordinates"
        )
        score -= 25
    elif gps["missing"]:
        warnings.append("Some usable frames are missing GPS coordinates")
        score -= 10
    if timestamps["completeness_pct"] < 90:
        warnings.append("Timestamp completeness is low; inspect EXIF or flight log alignment")
        score -= 20
    elif timestamps["missing"]:
        warnings.append("Some usable frames are missing timestamps")
        score -= 8
    if timestamps["duplicate_frames"]:
        warnings.append("Duplicate timestamps found; check for duplicate frames")
        score -= min(15, 3 * int(timestamps["duplicate_groups"]))
    if timestamps["gap_count"]:
        warnings.append("Timestamp gaps found; verify continuous coverage across the flight")
        score -= min(20, 4 * int(timestamps["gap_count"]))
    if quality["blur_pct"] >= 20:
        warnings.append("Many frames are below the blur threshold")
        score -= 15
    if quality["dark_pct"] + quality["bright_pct"] >= 20:
        warnings.append("Exposure issues detected in a significant share of frames")
        score -= 12
    if coverage["warnings"]:
        warnings.extend(coverage["warnings"])
        score -= 12

    score = max(0, min(100, score))
    if score >= 80:
        safe = "yes"
        action = "Start reconstruction"
    elif score >= 60:
        safe = "caution"
        action = "Review warnings, then use Quick reconstruction if the dataset looks acceptable"
    else:
        safe = "no"
        action = (
            "Fix GPS/timestamps, remove poor frames, or capture more overlap before reconstructing"
        )

    return {
        "session_id": session_id,
        "total_frames": total,
        "usable_frames": len(usable_images),
        "gps": gps,
        "timestamps": timestamps,
        "quality": quality,
        "coverage": coverage,
        "warnings": warnings,
        "safe_to_reconstruct": safe,
        "score": score,
        "recommended_action": action,
    }
