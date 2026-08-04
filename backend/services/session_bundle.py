from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PureWindowsPath

from sqlalchemy import DateTime
from sqlalchemy.orm import Session as DBSession

from backend.core.config import get_config
from backend.db.models import (
    Annotation,
    Defect,
    DefectImage,
    FlightEntry,
    FlightLog,
    FlightLogPoint,
    Footprint,
    Image,
    Measurement,
    Reconstruction,
    ReconstructionFrame,
    Session,
    SessionFrameSelection,
    SessionLogEntry,
)

# Paths bundled as files (not directories — e.g. colmap_dir is skipped, too large).
_IMAGE_PATH_FIELDS = ("filepath", "thumb_path")
_FLIGHT_LOG_PATH_FIELDS = ("filepath",)
_RECONSTRUCTION_PATH_FIELDS = (
    "splat_path",
    "splat_preview_path",
    "splat_medium_path",
    "thumb_path",
    "pointcloud_path",
    "mesh_glb_path",
    "mesh_obj_path",
    "mesh_mtl_path",
    "flythrough_path",
    "ortho_path",
    "semantic_labels_path",
)

# Every path-bearing column on a restorable model, including the ones that are NOT
# bundled as artifacts (colmap_dir, coverage_gaps_path, folder_path). manifest.json is
# attacker-controlled input, so a restored row may only ever carry a path this module
# wrote itself: these are all nulled before construction, and _restore_artifact then
# repopulates only the fields whose files were genuinely in the archive. Without this,
# a crafted manifest could point splat_path at any file the server can read.
_PATH_COLUMNS = {
    Session: ("folder_path",),
    Image: _IMAGE_PATH_FIELDS,
    FlightLog: _FLIGHT_LOG_PATH_FIELDS,
    Reconstruction: _RECONSTRUCTION_PATH_FIELDS + ("colmap_dir", "coverage_gaps_path"),
}


def _sanitize_restored_row(model_cls, data: dict) -> dict:
    """Strip untrusted filesystem paths from a manifest row before it becomes a model."""
    for column in _PATH_COLUMNS.get(model_cls, ()):
        data[column] = None
    if model_cls is Image and data.get("filename"):
        # PureWindowsPath (not PurePath) so "/", "\" and drive letters are stripped on
        # any host OS — the filename is later joined onto the COLMAP workspace directory.
        data["filename"] = PureWindowsPath(str(data["filename"])).name
    return data


def _dump(obj) -> dict:
    """Dump a model row's columns to a JSON-safe dict (datetimes -> isoformat)."""
    out = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[col.name] = val
    return out


def _restore_datetimes(model_cls, data: dict) -> dict:
    """Parse ISO datetime strings back to datetime for the model's DateTime columns."""
    out = dict(data)
    for col in model_cls.__table__.columns:
        if isinstance(col.type, DateTime) and isinstance(out.get(col.name), str):
            out[col.name] = datetime.fromisoformat(out[col.name])
    return out


def _bundle_artifacts(
    zf: zipfile.ZipFile, manifest: dict, category: str, path_fields: tuple
) -> None:
    """Write any existing files referenced by ``path_fields`` into the zip and
    record where, so restore can copy them back and rewrite the DB path."""
    for rec in manifest[category]:
        for field in path_fields:
            raw = rec.get(field)
            if not raw:
                continue
            p = Path(raw)
            if not p.is_file():
                continue
            archive_path = f"artifacts/{category}/{rec['id']}/{field}/{p.name}"
            zf.write(p, archive_path)
            manifest["artifacts"].append(
                {
                    "table": category,
                    "row_id": rec["id"],
                    "field": field,
                    "archive_path": archive_path,
                }
            )


def build_session_archive(zip_path: Path, session: Session, db: DBSession) -> dict:
    """Build a portable .zip of a session: its row, every cascaded child row
    (serialized to JSON), and any artifact files that exist on disk."""
    from backend.services.reconstruction import _safe_export_path

    exports_root = Path(get_config().exports_dir).resolve()
    try:
        zip_path = _safe_export_path(zip_path, exports_root)
    except ValueError as exc:
        raise ValueError("Session archive path is outside exports directory") from exc

    images = db.query(Image).filter(Image.session_id == session.id).all()
    image_ids = [i.id for i in images]
    footprints = (
        db.query(Footprint).filter(Footprint.image_id.in_(image_ids)).all() if image_ids else []
    )
    flight_logs = db.query(FlightLog).filter(FlightLog.session_id == session.id).all()
    flight_log_ids = [f.id for f in flight_logs]
    flight_log_points = (
        db.query(FlightLogPoint).filter(FlightLogPoint.flight_log_id.in_(flight_log_ids)).all()
        if flight_log_ids
        else []
    )
    flight_entries = db.query(FlightEntry).filter(FlightEntry.session_id == session.id).all()
    log_entries = db.query(SessionLogEntry).filter(SessionLogEntry.session_id == session.id).all()
    reconstructions = db.query(Reconstruction).filter(Reconstruction.session_id == session.id).all()
    rec_ids = [r.id for r in reconstructions]
    frames = (
        db.query(ReconstructionFrame).filter(ReconstructionFrame.reconstruction_id.in_(rec_ids)).all()
        if rec_ids
        else []
    )
    annotations = (
        db.query(Annotation).filter(Annotation.reconstruction_id.in_(rec_ids)).all()
        if rec_ids
        else []
    )
    measurements = (
        db.query(Measurement).filter(Measurement.reconstruction_id.in_(rec_ids)).all()
        if rec_ids
        else []
    )
    frame_selections = (
        db.query(SessionFrameSelection).filter(SessionFrameSelection.session_id == session.id).all()
    )
    defects = db.query(Defect).filter(Defect.session_id == session.id).all()
    defect_ids = [d.id for d in defects]
    defect_images = (
        db.query(DefectImage).filter(DefectImage.defect_id.in_(defect_ids)).all()
        if defect_ids
        else []
    )

    manifest = {
        "export_type": "session_archive_bundle",
        "session": _dump(session),
        "images": [_dump(i) for i in images],
        "footprints": [_dump(f) for f in footprints],
        "flight_logs": [_dump(f) for f in flight_logs],
        "flight_log_points": [_dump(p) for p in flight_log_points],
        "flight_entries": [_dump(f) for f in flight_entries],
        "log_entries": [_dump(e) for e in log_entries],
        "reconstructions": [_dump(r) for r in reconstructions],
        "reconstruction_frames": [_dump(f) for f in frames],
        "annotations": [_dump(a) for a in annotations],
        "measurements": [_dump(m) for m in measurements],
        "frame_selections": [_dump(s) for s in frame_selections],
        "defects": [_dump(d) for d in defects],
        "defect_images": [_dump(di) for di in defect_images],
        "artifacts": [],
    }

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _bundle_artifacts(zf, manifest, "images", _IMAGE_PATH_FIELDS)
        _bundle_artifacts(zf, manifest, "flight_logs", _FLIGHT_LOG_PATH_FIELDS)
        _bundle_artifacts(zf, manifest, "reconstructions", _RECONSTRUCTION_PATH_FIELDS)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    manifest["bundle_path"] = str(zip_path)
    return manifest


def _restore_root(new_session_id: int) -> Path:
    return Path(get_config().imports_dir) / "restored_sessions" / str(new_session_id)


def _restore_artifact(
    zf: zipfile.ZipFile, manifest: dict, table: str, old_row_id: int, field: str, restore_root: Path
) -> str | None:
    """Copy a bundled artifact back to disk under ``restore_root`` and return its new path."""
    entry = next(
        (
            a
            for a in manifest["artifacts"]
            if a["table"] == table and a["row_id"] == old_row_id and a["field"] == field
        ),
        None,
    )
    if entry is None:
        return None
    from backend.services.reconstruction import _safe_export_path

    archive_path = entry["archive_path"]
    dest = restore_root / Path(archive_path).relative_to("artifacts")
    # A crafted bundle can carry an archive_path like "artifacts/../../etc/foo" that
    # escapes restore_root (zip-slip). Reject anything that resolves outside it.
    try:
        dest = _safe_export_path(dest, restore_root)
    except ValueError as exc:
        raise ValueError(f"Archive entry escapes restore directory: {archive_path}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(archive_path) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return str(dest)


def restore_session_archive(zip_path: Path, db: DBSession) -> dict:
    """Restore a session archive as a brand-new session (fresh IDs). Never
    touches or clobbers any existing session."""
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))

        session_data = _sanitize_restored_row(
            Session, _restore_datetimes(Session, manifest["session"])
        )
        session_data.pop("id", None)
        # project_id points outside the bundle (projects aren't archived) — drop it.
        session_data["project_id"] = None
        new_session = Session(**session_data)
        db.add(new_session)
        db.flush()

        restore_root = _restore_root(new_session.id)
        new_session.folder_path = str(restore_root)

        image_id_map: dict[int, int] = {}
        for row in manifest["images"]:
            old_id = row["id"]
            data = _sanitize_restored_row(Image, _restore_datetimes(Image, row))
            data.pop("id", None)
            data["session_id"] = new_session.id
            for field in _IMAGE_PATH_FIELDS:
                restored = _restore_artifact(zf, manifest, "images", old_id, field, restore_root)
                if restored:
                    data[field] = restored
            if not data.get("filepath"):
                # filepath is NOT NULL, but the source file was absent when the archive
                # was built (_bundle_artifacts skips non-files). Point at where it would
                # have landed rather than keeping the source machine's untrusted path.
                data["filepath"] = str(restore_root / "missing" / (data.get("filename") or ""))
            img = Image(**data)
            db.add(img)
            db.flush()
            image_id_map[old_id] = img.id

        for row in manifest["footprints"]:
            data = dict(row)
            data.pop("id", None)
            old_image_id = data.pop("image_id")
            if old_image_id not in image_id_map:
                continue  # dropped: image outside the bundle
            data["image_id"] = image_id_map[old_image_id]
            db.add(Footprint(**data))

        flight_log_id_map: dict[int, int] = {}
        for row in manifest["flight_logs"]:
            old_id = row["id"]
            data = _sanitize_restored_row(FlightLog, _restore_datetimes(FlightLog, row))
            data.pop("id", None)
            data["session_id"] = new_session.id
            for field in _FLIGHT_LOG_PATH_FIELDS:
                restored = _restore_artifact(
                    zf, manifest, "flight_logs", old_id, field, restore_root
                )
                if restored:
                    data[field] = restored
            fl = FlightLog(**data)
            db.add(fl)
            db.flush()
            flight_log_id_map[old_id] = fl.id

        for row in manifest["flight_log_points"]:
            data = _restore_datetimes(FlightLogPoint, row)
            data.pop("id", None)
            old_flight_log_id = data.pop("flight_log_id")
            if old_flight_log_id not in flight_log_id_map:
                continue
            data["flight_log_id"] = flight_log_id_map[old_flight_log_id]
            db.add(FlightLogPoint(**data))

        for row in manifest["flight_entries"]:
            data = _restore_datetimes(FlightEntry, row)
            data.pop("id", None)
            data["session_id"] = new_session.id
            db.add(FlightEntry(**data))

        for row in manifest["log_entries"]:
            data = _restore_datetimes(SessionLogEntry, row)
            data.pop("id", None)
            data["session_id"] = new_session.id
            db.add(SessionLogEntry(**data))

        rec_id_map: dict[int, int] = {}
        pending_parent: list[tuple[int, int | None]] = []
        for row in manifest["reconstructions"]:
            old_id = row["id"]
            data = _sanitize_restored_row(
                Reconstruction, _restore_datetimes(Reconstruction, row)
            )
            old_parent = data.pop("parent_reconstruction_id", None)
            data.pop("id", None)
            data["session_id"] = new_session.id
            data["parent_reconstruction_id"] = None
            for field in _RECONSTRUCTION_PATH_FIELDS:
                restored = _restore_artifact(
                    zf, manifest, "reconstructions", old_id, field, restore_root
                )
                if restored:
                    data[field] = restored
            rec = Reconstruction(**data)
            db.add(rec)
            db.flush()
            rec_id_map[old_id] = rec.id
            pending_parent.append((rec.id, old_parent))

        # Second pass: remap parent_reconstruction_id now that every new id is
        # known. Any parent outside the bundle is dropped (left as None).
        for new_id, old_parent in pending_parent:
            if old_parent is not None and old_parent in rec_id_map:
                rec = db.query(Reconstruction).filter(Reconstruction.id == new_id).first()
                rec.parent_reconstruction_id = rec_id_map[old_parent]

        for row in manifest["reconstruction_frames"]:
            old_rec_id = row["reconstruction_id"]
            old_image_id = row["image_id"]
            if old_rec_id not in rec_id_map or old_image_id not in image_id_map:
                continue
            db.add(
                ReconstructionFrame(
                    reconstruction_id=rec_id_map[old_rec_id],
                    image_id=image_id_map[old_image_id],
                    colmap_error_px=row.get("colmap_error_px"),
                )
            )

        for row in manifest["annotations"]:
            data = _restore_datetimes(Annotation, row)
            data.pop("id", None)
            old_rec_id = data.pop("reconstruction_id")
            if old_rec_id not in rec_id_map:
                continue
            data["reconstruction_id"] = rec_id_map[old_rec_id]
            db.add(Annotation(**data))

        for row in manifest["measurements"]:
            data = _restore_datetimes(Measurement, row)
            data.pop("id", None)
            old_rec_id = data.pop("reconstruction_id")
            if old_rec_id not in rec_id_map:
                continue
            data["reconstruction_id"] = rec_id_map[old_rec_id]
            db.add(Measurement(**data))

        for row in manifest["frame_selections"]:
            old_image_id = row["image_id"]
            if old_image_id not in image_id_map:
                continue
            db.add(
                SessionFrameSelection(
                    session_id=new_session.id, image_id=image_id_map[old_image_id]
                )
            )

        defect_id_map: dict[int, int] = {}
        for row in manifest["defects"]:
            old_id = row["id"]
            data = _restore_datetimes(Defect, row)
            data.pop("id", None)
            data["session_id"] = new_session.id
            d = Defect(**data)
            db.add(d)
            db.flush()
            defect_id_map[old_id] = d.id

        for row in manifest["defect_images"]:
            old_defect_id = row["defect_id"]
            old_image_id = row["image_id"]
            if old_defect_id not in defect_id_map or old_image_id not in image_id_map:
                continue
            db.add(
                DefectImage(
                    defect_id=defect_id_map[old_defect_id], image_id=image_id_map[old_image_id]
                )
            )

        # Single commit: the restore reads an untrusted archive, so a failure part-way
        # through must leave no rows behind. Previously each table committed as it went,
        # so a malformed manifest stranded a half-restored session on every attempt.
        db.commit()

    return {
        "session_id": new_session.id,
        "image_count": len(image_id_map),
        "flight_log_count": len(flight_log_id_map),
        "reconstruction_count": len(rec_id_map),
        "defect_count": len(defect_id_map),
    }
