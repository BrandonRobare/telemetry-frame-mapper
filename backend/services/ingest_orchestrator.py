from __future__ import annotations

import logging
import os
import threading
from collections import Counter
from hashlib import sha256
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from ..core.paths import confine_path
from ..db.models import Footprint, Image, SessionLogEntry
from ..db.models import Session as SessionModel
from .geometry import compute_footprint
from .ingest import UnreadableImageError, extract_exif, generate_thumbnail
from .quality import flag_image, score_brightness, score_sharpness
from .storage_summary_cache import invalidate_storage_summary_cache

logger = logging.getLogger(__name__)

# Flag of a frame whose quality scoring did not complete. Such a frame is kept
# for review but is never usable: no measured score backs a 'good' verdict.
UNSCORED_FLAG = "unscored"

_progress: dict[int, dict] = {}
_progress_lock = threading.Lock()


def get_progress(session_id: int) -> dict:
    with _progress_lock:
        return dict(
            _progress.get(
                session_id, {"processed": 0, "total": 0, "skipped": 0, "status": "unknown"}
            )
        )


def build_footprint(img: Image, cfg) -> Footprint | None:
    """Footprint row for ``img``'s current position, or None without a full position.

    Ingest and flight-log GPS sync both derive footprints here, so a synced
    image gets exactly the footprint ingest would have given it at that
    position. ``cfg`` is the loaded app config (camera FOV, target CRS).
    Errors from ``compute_footprint`` propagate; callers decide how to log them.
    """
    if img.latitude is None or img.longitude is None or img.altitude_m is None:
        return None
    fp = compute_footprint(
        lat=img.latitude,
        lon=img.longitude,
        altitude_m=img.altitude_m,
        fov_horizontal_deg=cfg.fov_horizontal_deg,
        fov_vertical_deg=cfg.fov_vertical_deg,
        yaw_deg=img.yaw,
        target_crs=cfg.target_crs,
        gimbal_pitch=img.gimbal_pitch,
    )
    if not fp:
        return None
    return Footprint(
        image_id=img.id,
        geom_wkt=fp.get("geom_wkt"),
        geom_geojson=fp.get("geom_geojson"),
        ground_width_m=fp.get("ground_width_m"),
        ground_height_m=fp.get("ground_height_m"),
        heading_estimated=fp.get("heading_estimated", True),
        pitch_oblique=fp.get("pitch_oblique", False),
    )


def _unique_filename(path: Path, root: Path, duplicate_basenames: set[str]) -> str:
    """Return a collision-free display/storage name for an imported image."""
    if os.path.normcase(path.name) not in duplicate_basenames:
        return path.name
    relative = path.relative_to(root).as_posix()
    suffix = path.suffix
    digest = sha256(relative.encode()).hexdigest()[:12]
    return f"{path.stem}__{digest}{suffix}"


def _skip_image(
    db: DBSession, session_id: int, index: int, skipped: int, path: Path, exc: Exception
) -> None:
    """Record an image that cannot be imported and move the progress past it."""
    # An unreadable file is an expected input problem; anything else is a bug
    # worth a traceback in the application log.
    logger.warning(
        "Skipped %s during import: %s",
        path.name,
        exc,
        exc_info=not isinstance(exc, UnreadableImageError),
    )
    db.add(SessionLogEntry(
        session_id=session_id,
        event_type="image_skipped",
        message=f"Skipped {path.name}: {exc}",
    ))
    with _progress_lock:
        _progress[session_id]["processed"] = index + 1
        _progress[session_id]["skipped"] = skipped
    db.commit()


def _run(session_id: int, folder: Path, db_factory) -> None:
    from ..core.config import get_ingest_config, load_config  # lazy import to avoid circular

    ingest_cfg = get_ingest_config()

    # Build accepted-suffix set from config (normalise to lowercase with leading dot).
    _raw_extensions = ingest_cfg.get("accepted_extensions", [".jpg", ".jpeg"])
    _ACCEPTED_SUFFIXES: set[str] = {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in _raw_extensions
    } or {".jpg", ".jpeg"}

    filter_zero_gps: bool = bool(ingest_cfg.get("filter_zero_gps", True))

    root = folder.resolve()
    seen: set[str] = set()
    accepted_files: list[Path] = []
    try:
        candidates = sorted(folder.rglob("*"))
    except OSError:
        candidates = []
    for p in candidates:
        try:
            resolved = confine_path(p, root)
            if p.is_file() and p.suffix.lower() in _ACCEPTED_SUFFIXES:
                key = os.path.normcase(str(resolved))
                if key not in seen:
                    seen.add(key)
                    accepted_files.append(p)
        except (OSError, ValueError):
            continue
    total = len(accepted_files)
    with _progress_lock:
        _progress[session_id] = {
            "processed": 0,
            "total": total,
            "skipped": 0,
            "status": "running",
        }
    if not accepted_files:
        with _progress_lock:
            _progress[session_id].update(
                status="error", error="No importable files found in the selected folder"
            )
        return

    duplicate_basenames = {
        name
        for name, count in Counter(os.path.normcase(path.name) for path in accepted_files).items()
        if count > 1
    }

    db: DBSession = db_factory()
    try:
        usable = 0
        imported = 0
        skipped = 0
        cfg = load_config()
        ingest_thumbnail_size: int = int(ingest_cfg.get("thumbnail_size_px", cfg.thumbnail_size_px))

        for i, accepted_file in enumerate(accepted_files):
            filename = _unique_filename(accepted_file, root, duplicate_basenames)
            try:
                exif = extract_exif(str(accepted_file))
            except Exception as exc:
                # One unreadable image must not fail the whole batch: skip it.
                # extract_exif raises UnreadableImageError for a file that is
                # not an image at all (#943).
                skipped += 1
                _skip_image(db, session_id, i, skipped, accepted_file, exc)
                continue

            # filter_zero_gps: skip images where both lat and lon are exactly 0.0.
            lat = exif.get("latitude")
            lon = exif.get("longitude")
            if (
                filter_zero_gps
                and lat is not None
                and lon is not None
                and lat == 0.0
                and lon == 0.0
            ):
                with _progress_lock:
                    _progress[session_id]["processed"] = i + 1
                continue

            # generate thumbnail into processed_dir/<session_id>/thumbs/
            thumb_path = None

            img = Image(
                session_id=session_id,
                filename=filename,
                filepath=str(accepted_file),
                thumb_path=None,
                timestamp=exif.get("timestamp"),
                latitude=exif.get("latitude"),
                longitude=exif.get("longitude"),
                altitude_m=exif.get("altitude_m"),
                gps_source=exif.get("gps_source", "none"),
                yaw=exif.get("yaw"),
                gimbal_pitch=exif.get("gimbal_pitch"),
                width=exif.get("width"),
                height=exif.get("height"),
                focal_length_mm=exif.get("focal_length_mm"),
                camera_make=exif.get("camera_make"),
                camera_model=exif.get("camera_model"),
                lens_model=exif.get("lens_model"),
                focal_length_35mm=exif.get("focal_length_35mm"),
                digital_zoom_ratio=exif.get("digital_zoom_ratio"),
                # Only a completed quality score may mark the frame good/usable.
                flag=UNSCORED_FLAG,
                usable=False,
            )
            db.add(img)
            db.flush()

            # Generate the thumbnail after the row exists so the file name can
            # carry the image id: case-variant sibling basenames (IMG.JPG vs
            # img.jpg) collapse to the same path on case-insensitive macOS
            # APFS and silently overwrite each other's thumbnails (#831).
            thumb_path = None
            try:
                thumb_dir = Path(cfg.processed_dir) / str(session_id) / "thumbs"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                dest = thumb_dir / f"{img.id}_{filename}"
                generate_thumbnail(str(accepted_file), str(dest), size=ingest_thumbnail_size)
                thumb_path = str(dest)
            except UnreadableImageError as exc:
                # The header parsed but the pixel data does not decode (e.g. a
                # copy cut short): drop the uncommitted row and skip the file.
                db.rollback()
                skipped += 1
                _skip_image(db, session_id, i, skipped, accepted_file, exc)
                continue
            except Exception as exc:
                # The frame itself is fine; only its preview is missing.
                logger.warning("Thumbnail generation failed for %s", filename, exc_info=True)
                db.add(SessionLogEntry(
                    session_id=session_id,
                    event_type="thumbnail_failed",
                    message=f"Thumbnail generation failed for {filename}: {exc}",
                ))
            img.thumb_path = thumb_path

            try:
                sharpness = score_sharpness(str(accepted_file))
                brightness = score_brightness(str(accepted_file))
                has_gps = exif.get("latitude") is not None and exif.get("longitude") is not None
                flag = flag_image(sharpness, brightness, has_gps)
                img.sharpness_score = sharpness
                img.brightness_score = brightness
                img.flag = flag
                img.usable = flag == "good"
            except Exception as exc:
                # The frame keeps flag=UNSCORED_FLAG and usable=False.
                logger.warning("Quality scoring failed for %s", filename, exc_info=True)
                db.add(SessionLogEntry(
                    session_id=session_id,
                    event_type="quality_failed",
                    message=f"Quality scoring failed for {filename}: {exc}",
                ))

            imported += 1
            if img.usable:
                usable += 1

            try:
                footprint = build_footprint(img, cfg)
                if footprint is not None:
                    db.add(footprint)
            except Exception:
                # Footprint stays best-effort, but a silent failure reads as
                # "no coverage data" in the UI — say so in the log (#640).
                logger.warning(
                    "Footprint computation failed for %s", filename, exc_info=True
                )

            with _progress_lock:
                _progress[session_id]["processed"] = i + 1
            db.commit()

        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session:
            session.photo_count = imported
            session.usable_count = usable
            db.add(SessionLogEntry(
                session_id=session_id,
                event_type="import_complete",
                photo_count=imported,
                message=f"Imported {imported} images, {usable} usable, {skipped} skipped",
            ))
            db.commit()
        with _progress_lock:
            _progress[session_id]["status"] = "done"
        invalidate_storage_summary_cache()
    except Exception as exc:
        with _progress_lock:
            _progress[session_id]["status"] = "error"
            _progress[session_id]["error"] = str(exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def start_import(session_id: int, folder: Path, db_factory) -> None:
    """Launch import pipeline in a background thread."""
    with _progress_lock:
        _progress[session_id] = {"processed": 0, "total": 0, "status": "pending"}
    t = threading.Thread(target=_run, args=(session_id, folder, db_factory), daemon=True)
    t.start()
