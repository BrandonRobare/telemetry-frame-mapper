from __future__ import annotations

from collections import Counter
from datetime import datetime

from shapely import wkt
from shapely.ops import unary_union
from sqlalchemy.orm import Session as DBSession

from backend.db.models import Footprint, Image, Session
from backend.services.quality import BRIGHT_THRESHOLD, DARK_THRESHOLD, _ingest_thresholds
from src.drone_video_geotagger.gps_quality import GpsSample, assess_gps_lock

_DUPLICATE_TIMESTAMP_EPSILON_S = 0.001
_COVERAGE_MIN_FOOTPRINTS = 3
_COVERAGE_MIN_OVERLAP_RATIO = 0.15
_COVERAGE_HIGH_OVERLAP_RATIO = 0.85
_TIMESTAMP_GAP_MULTIPLIER = 3.0
_TIMESTAMP_GAP_MIN_SECONDS = 2.0
_LIGHTING_MIN_SAMPLES = 5
_LIGHTING_P10_P90_SPREAD_THRESHOLD = 60.0

# Match-density diagnostics
_MATCH_SAMPLE_STRIDE = 10  # only sample every Nth usable image pair
_MATCH_MIN_INLIERS = 12
_MATCH_LOW_DENSITY_THRESHOLD = 24  # matches below this flag a weak-texture stretch
_MATCH_MAX_PAIRS = 30
_MATCH_WEAK_RATIO_THRESHOLD = 0.3  # fraction of sampled pairs that are low-density


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


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """Return the nearest-rank percentile for a non-empty sorted list."""
    index = round((len(sorted_values) - 1) * percentile)
    return sorted_values[index]


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


def _gps_lock_quality(images: list[Image]) -> dict:
    """Run GPS-lock heuristics over the per-image coordinates (in id order)."""
    samples = []
    for img in images:
        if img.latitude is None or img.longitude is None:
            continue
        t_s = _timestamp_seconds(img.timestamp) if img.timestamp is not None else None
        samples.append(GpsSample(lat=float(img.latitude), lon=float(img.longitude), t_s=t_s))

    report = assess_gps_lock(samples)
    return {
        "sample_count": report.sample_count,
        "near_zero_count": report.near_zero_count,
        "longest_frozen_run": report.longest_frozen_run,
        "jump_count": report.jump_count,
        "max_speed_ms": (
            round(report.max_speed_ms, 1) if report.max_speed_ms is not None else None
        ),
        "warnings": list(report.warnings),
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
    sorted_brightness = sorted(brightness_values)
    lighting = {
        "sample_count": len(sorted_brightness),
        "p10_p90_spread": None,
        "threshold": _LIGHTING_P10_P90_SPREAD_THRESHOLD,
        "inconsistent": False,
    }
    if len(sorted_brightness) >= _LIGHTING_MIN_SAMPLES:
        p10 = _percentile(sorted_brightness, 0.10)
        p90 = _percentile(sorted_brightness, 0.90)
        spread = round(p90 - p10, 1)
        lighting.update({
            "p10_p90_spread": spread,
            "inconsistent": spread >= _LIGHTING_P10_P90_SPREAD_THRESHOLD,
        })
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
        "lighting": lighting,
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


def _match_density_diagnostics(images: list[Image]) -> dict | None:
    """Sample sequential frame pairs for SIFT/ORB match density.

    Returns None when the diagnostic could not run (e.g. missing OpenCV
    or zero usable images).  Best-effort: individual pair failures
    (missing file, feature extraction error) are skipped without
    crashing the whole report.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None

    usable = [img for img in images if img.usable]
    if len(usable) < 2:
        return None

    orb = cv2.ORB_create(nfeatures=800)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    pairs_sampled = 0
    pairs_failed = 0
    pairs_low = 0
    densities: list[float] = []

    # Stride through usable images, spreading sample across the timeline.
    end = min(len(usable) - 1, _MATCH_SAMPLE_STRIDE * _MATCH_MAX_PAIRS)
    for i in range(0, end, _MATCH_SAMPLE_STRIDE):
        img_a = usable[i]
        img_b = usable[i + 1]
        try:
            if not img_a.filepath or not img_b.filepath:
                pairs_failed += 1
                continue
            gray_a = cv2.imread(img_a.filepath, cv2.IMREAD_GRAYSCALE)
            gray_b = cv2.imread(img_b.filepath, cv2.IMREAD_GRAYSCALE)
            if gray_a is None or gray_b is None:
                pairs_failed += 1
                continue
            kp_a, des_a = orb.detectAndCompute(gray_a, None)
            kp_b, des_b = orb.detectAndCompute(gray_b, None)
            if (
                des_a is None
                or des_b is None
                or len(des_a) < _MATCH_MIN_INLIERS
                or len(des_b) < _MATCH_MIN_INLIERS
            ):
                pairs_failed += 1
                continue
            matches = bf.match(des_a, des_b)
            pairs_sampled += 1
            densities.append(float(len(matches)))
            if len(matches) < _MATCH_LOW_DENSITY_THRESHOLD:
                pairs_low += 1
        except Exception:
            pairs_failed += 1
            continue

    if pairs_sampled == 0:
        return None

    weak_ratio = pairs_low / pairs_sampled if pairs_sampled > 0 else 0.0
    avg_density = sum(densities) / len(densities) if densities else 0.0

    return {
        "samples": pairs_sampled,
        "failed_pairs": pairs_failed,
        "low_count": pairs_low,
        "weak_ratio": round(weak_ratio, 2),
        "low_threshold": _MATCH_LOW_DENSITY_THRESHOLD,
        "avg_matches": round(avg_density, 1),
    }


def build_preflight_quality_report(session_id: int, db: DBSession) -> dict:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise ValueError("Session not found")

    images = db.query(Image).filter(Image.session_id == session_id).order_by(Image.id).all()
    total = len(images)
    usable_images = [img for img in images if img.usable]
    gps = _gps_quality(usable_images)
    gps_lock = _gps_lock_quality(usable_images)
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
    if gps_lock["warnings"]:
        warnings.extend(gps_lock["warnings"])
        score -= 20
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
    if quality["lighting"]["inconsistent"]:
        warnings.append(
            "Lighting varies substantially across the flight; shadows or changing exposure may "
            "hurt reconstruction consistency"
        )
        score -= 10
    if coverage["warnings"]:
        warnings.extend(coverage["warnings"])
        score -= 12

    # Optional match-density diagnostics (best-effort)
    match_density = _match_density_diagnostics(images)
    if match_density is not None and match_density["weak_ratio"] >= _MATCH_WEAK_RATIO_THRESHOLD:
        warnings.append(
            "Weak-texture stretches detected: many frame pairs have low feature-match "
            "density: may cause COLMAP registration failures on uniform surfaces "
            "(water, pavement, snow)"
        )
        score -= 15

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
        "gps_lock": gps_lock,
        "timestamps": timestamps,
        "quality": quality,
        "coverage": coverage,
        "warnings": warnings,
        "safe_to_reconstruct": safe,
        "score": score,
        "recommended_action": action,
        "match_density": match_density,
    }


def build_quick_report(session_id: int, db: DBSession) -> dict:
    """Compact post-landing QA summary (pass/caution/fail) from preflight checks.

    Returns the full preflight report augmented with match-density diagnostics
    and a simplified status field suitable for a rapid UI card.
    """
    return build_preflight_quality_report(session_id, db)
