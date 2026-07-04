from __future__ import annotations

import os
import threading
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from ..db.models import Footprint, Image, SessionLogEntry
from ..db.models import Session as SessionModel
from .geometry import compute_footprint
from .ingest import extract_exif, generate_thumbnail
from .quality import flag_image, score_brightness, score_sharpness
from .storage_summary_cache import invalidate_storage_summary_cache

_progress: dict[int, dict] = {}
_progress_lock = threading.Lock()


def get_progress(session_id: int) -> dict:
    with _progress_lock:
        return dict(_progress.get(session_id, {"processed": 0, "total": 0, "status": "unknown"}))


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

    seen: set[str] = set()
    accepted_files: list[Path] = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in _ACCEPTED_SUFFIXES:
            key = os.path.normcase(str(p.resolve()))
            if key not in seen:
                seen.add(key)
                accepted_files.append(p)
    total = len(accepted_files)
    with _progress_lock:
        _progress[session_id] = {"processed": 0, "total": total, "status": "running"}

    db: DBSession = db_factory()
    try:
        usable = 0
        imported = 0
        cfg = load_config()
        ingest_thumbnail_size: int = int(ingest_cfg.get("thumbnail_size_px", cfg.thumbnail_size_px))

        for i, accepted_file in enumerate(accepted_files):
            exif = extract_exif(str(accepted_file))

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
            try:
                thumb_dir = Path(cfg.processed_dir) / str(session_id) / "thumbs"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                dest = thumb_dir / accepted_file.name
                generate_thumbnail(str(accepted_file), str(dest), size=ingest_thumbnail_size)
                thumb_path = str(dest)
            except Exception:
                thumb_path = None

            img = Image(
                session_id=session_id,
                filename=accepted_file.name,
                filepath=str(accepted_file),
                thumb_path=thumb_path,
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
                flag="good",
                usable=True,
            )
            db.add(img)
            db.flush()

            try:
                sharpness = score_sharpness(str(accepted_file))
                brightness = score_brightness(str(accepted_file))
                has_gps = exif.get("latitude") is not None and exif.get("longitude") is not None
                flag = flag_image(sharpness, brightness, has_gps)
                img.sharpness_score = sharpness
                img.brightness_score = brightness
                img.flag = flag
                img.usable = flag == "good"
            except Exception:
                pass  # quality scoring is best-effort

            imported += 1
            if img.usable:
                usable += 1

            if (
                img.latitude is not None
                and img.longitude is not None
                and img.altitude_m is not None
            ):
                try:
                    fp = compute_footprint(
                        lat=img.latitude,
                        lon=img.longitude,
                        altitude_m=img.altitude_m,
                        fov_horizontal_deg=cfg.fov_horizontal_deg,
                        fov_vertical_deg=cfg.fov_vertical_deg,
                        yaw_deg=img.yaw,
                        target_crs=cfg.target_crs,
                        gimbal_pitch=exif.get("gimbal_pitch"),
                    )
                    if fp:
                        db.add(Footprint(
                            image_id=img.id,
                            geom_wkt=fp.get("geom_wkt"),
                            geom_geojson=fp.get("geom_geojson"),
                            ground_width_m=fp.get("ground_width_m"),
                            ground_height_m=fp.get("ground_height_m"),
                            heading_estimated=fp.get("heading_estimated", True),
                            pitch_oblique=fp.get("pitch_oblique", False),
                        ))
                except Exception:
                    pass  # footprint is best-effort

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
                message=f"Imported {imported} images, {usable} usable",
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
