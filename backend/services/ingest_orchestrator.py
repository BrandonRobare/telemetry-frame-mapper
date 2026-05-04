from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from ..db.models import Footprint, Image, SessionLogEntry
from ..db.models import Session as SessionModel
from .geometry import compute_footprint
from .ingest import extract_exif, generate_thumbnail
from .quality import flag_image, score_brightness, score_sharpness

_progress: dict[int, dict] = {}
_progress_lock = threading.Lock()


def get_progress(session_id: int) -> dict:
    with _progress_lock:
        return dict(_progress.get(session_id, {"processed": 0, "total": 0, "status": "unknown"}))


def _run(session_id: int, folder: Path, db_factory) -> None:
    from ..core.config import load_config  # lazy import to avoid circular

    jpgs = (
        sorted(folder.glob("*.jpg"))
        + sorted(folder.glob("*.jpeg"))
        + sorted(folder.glob("*.JPG"))
        + sorted(folder.glob("*.JPEG"))
    )
    total = len(jpgs)
    with _progress_lock:
        _progress[session_id] = {"processed": 0, "total": total, "status": "running"}

    db: DBSession = db_factory()
    try:
        usable = 0
        cfg = load_config()

        for i, jpg in enumerate(jpgs):
            exif = extract_exif(str(jpg))

            # generate thumbnail into processed_dir/<session_id>/thumbs/
            thumb_path = None
            try:
                thumb_dir = Path(cfg.processed_dir) / str(session_id) / "thumbs"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                dest = thumb_dir / jpg.name
                generate_thumbnail(str(jpg), str(dest), size=cfg.thumbnail_size_px)
                thumb_path = str(dest)
            except Exception:
                thumb_path = None

            img = Image(
                session_id=session_id,
                filename=jpg.name,
                filepath=str(jpg),
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
                flag="good",
                usable=True,
            )
            db.add(img)
            db.flush()

            try:
                sharpness = score_sharpness(str(jpg))
                brightness = score_brightness(str(jpg))
                has_gps = exif.get("latitude") is not None and exif.get("longitude") is not None
                flag = flag_image(sharpness, brightness, has_gps)
                img.sharpness_score = sharpness
                img.brightness_score = brightness
                img.flag = flag
                img.usable = flag == "good"
            except Exception:
                pass  # quality scoring is best-effort

            if img.usable:
                usable += 1

            if img.latitude and img.longitude and img.altitude_m:
                try:
                    fp = compute_footprint(
                        lat=img.latitude,
                        lon=img.longitude,
                        altitude_m=img.altitude_m,
                        fov_horizontal_deg=cfg.fov_horizontal_deg,
                        fov_vertical_deg=cfg.fov_vertical_deg,
                        yaw_deg=img.yaw,
                        target_crs=cfg.target_crs,
                    )
                    if fp:
                        db.add(Footprint(
                            image_id=img.id,
                            geom_wkt=fp.get("geom_wkt"),
                            geom_geojson=fp.get("geom_geojson"),
                            ground_width_m=fp.get("ground_width_m"),
                            ground_height_m=fp.get("ground_height_m"),
                            heading_estimated=fp.get("heading_estimated", True),
                        ))
                except Exception:
                    pass  # footprint is best-effort

            with _progress_lock:
                _progress[session_id]["processed"] = i + 1
            db.commit()

        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session:
            session.photo_count = total
            session.usable_count = usable
            db.add(SessionLogEntry(
                session_id=session_id,
                event_type="import_complete",
                photo_count=total,
                message=f"Imported {total} images, {usable} usable",
            ))
            db.commit()
        with _progress_lock:
            _progress[session_id]["status"] = "done"
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
