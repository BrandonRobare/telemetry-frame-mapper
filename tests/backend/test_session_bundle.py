from __future__ import annotations

import zipfile
from unittest.mock import patch

import pytest

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
    SessionFrameSelection,
    SessionLogEntry,
)
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _cfg(tmp_path):
    return type(
        "Cfg",
        (),
        {
            "exports_dir": str(tmp_path / "exports"),
            "imports_dir": str(tmp_path / "imports"),
            "processed_dir": str(tmp_path / "processed"),
            "data_dir": str(tmp_path / "data"),
        },
    )()


def _archive(client, cfg, session_id):
    with (
        patch("backend.routers.sessions.get_config", return_value=cfg),
        patch("backend.services.session_bundle.get_config", return_value=cfg),
    ):
        return client.post(f"/sessions/{session_id}/archive")


def _restore(client, cfg, zip_path):
    with (
        patch("backend.routers.sessions.get_config", return_value=cfg),
        patch("backend.services.session_bundle.get_config", return_value=cfg),
    ):
        return client.post("/sessions/restore", json={"zip_path": zip_path})


def test_archive_session_not_found(client, tmp_path):
    resp = _archive(client, _cfg(tmp_path), 999999)
    assert resp.status_code == 404


def test_restore_missing_zip_not_found(client, tmp_path):
    # missing file, but under an allowed root (exports_dir) → 404, not the 400 confinement error
    resp = _restore(client, _cfg(tmp_path), str(tmp_path / "exports" / "missing.zip"))
    assert resp.status_code == 404


def test_restore_rejects_zip_path_outside_allowed_dirs(client, tmp_path):
    # a path outside imports/exports/data must not be readable via restore (path injection)
    resp = _restore(client, _cfg(tmp_path), str(tmp_path / "evil.zip"))
    assert resp.status_code == 400


def test_restore_rejects_sibling_of_allowed_directory(client, tmp_path):
    resp = _restore(client, _cfg(tmp_path), str(tmp_path / "exports2" / "bundle.zip"))
    assert resp.status_code == 400


def test_restore_finds_nested_archive_from_allowed_root(client, tmp_path):
    cfg = _cfg(tmp_path)
    archive = tmp_path / "imports" / "incoming" / "bundle.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zip")

    with patch(
        "backend.services.session_bundle.restore_session_archive",
        return_value={"session_id": 7},
    ) as restore:
        resp = _restore(client, cfg, str(archive))

    assert resp.status_code == 200
    assert restore.call_args.args[0] == archive


def test_session_archive_rejects_sibling_of_exports(tmp_path):
    from backend.services.session_bundle import build_session_archive

    with (
        patch("backend.services.session_bundle.get_config", return_value=_cfg(tmp_path)),
        pytest.raises(ValueError, match="outside exports directory"),
    ):
        build_session_archive(tmp_path / "exports2" / "bundle.zip", None, None)


def test_restore_artifact_rejects_zip_slip(tmp_path):
    # a crafted archive_path that escapes restore_root must be rejected (zip-slip)
    from backend.services.session_bundle import _restore_artifact

    zip_file = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("manifest.json", "{}")
    restore_root = tmp_path / "restored" / "1"
    manifest = {
        "artifacts": [
            {
                "table": "images",
                "row_id": 1,
                "field": "filepath",
                "archive_path": "artifacts/../../../escape.bin",
            }
        ]
    }
    with zipfile.ZipFile(zip_file) as zf:
        try:
            _restore_artifact(zf, manifest, "images", 1, "filepath", restore_root)
            raised = False
        except ValueError:
            raised = True
    assert raised, "zip-slip archive_path was not rejected"
    assert not (tmp_path / "escape.bin").exists()


def test_archive_creates_zip_with_manifest_and_bundled_artifact(client, tmp_path):
    cfg = _cfg(tmp_path)
    db = _db(client)
    session = SessionModel(name="Field Session", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)

    thumb = tmp_path / "frame1_thumb.jpg"
    thumb.write_bytes(b"thumb")
    db.add(
        Image(
            session_id=session.id,
            filename="frame1.jpg",
            filepath=str(tmp_path / "frame1.jpg"),
            thumb_path=str(thumb),
        )
    )
    db.commit()

    resp = _archive(client, cfg, session.id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["name"] == "Field Session"
    assert len(body["images"]) == 1

    with zipfile.ZipFile(body["bundle_path"]) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert any(n.startswith("artifacts/images/") and n.endswith("frame1_thumb.jpg") for n in names)


def test_round_trip_remaps_reconstruction_lineage_and_measurements(client, tmp_path):
    cfg = _cfg(tmp_path)
    db = _db(client)

    session = SessionModel(
        name="Roof Survey", folder_path=str(tmp_path), photo_count=2, usable_count=2
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    original_session_id = session.id

    img1 = Image(session_id=session.id, filename="a.jpg", filepath=str(tmp_path / "a.jpg"))
    img2 = Image(session_id=session.id, filename="b.jpg", filepath=str(tmp_path / "b.jpg"))
    db.add_all([img1, img2])
    db.commit()

    # A reconstruction belonging to a *different* session — used below as a
    # parent reference that lives outside the archived bundle.
    other_session = SessionModel(name="Other", folder_path=str(tmp_path))
    db.add(other_session)
    db.commit()
    db.refresh(other_session)
    outside_rec = Reconstruction(session_id=other_session.id, status="complete")
    db.add(outside_rec)
    db.commit()
    db.refresh(outside_rec)

    splat = tmp_path / "splat.ply"
    splat.write_bytes(b"splat")
    parent_rec = Reconstruction(
        session_id=session.id, status="complete", frames_used=2, splat_path=str(splat)
    )
    db.add(parent_rec)
    db.commit()
    db.refresh(parent_rec)

    child_rec = Reconstruction(
        session_id=session.id,
        status="complete",
        parent_reconstruction_id=parent_rec.id,
        frames_used=2,
    )
    db.add(child_rec)
    db.commit()
    db.refresh(child_rec)

    # Lineage pointing at a reconstruction outside the bundle — must be
    # dropped (not remapped) on restore.
    dangling_rec = Reconstruction(
        session_id=session.id, status="complete", parent_reconstruction_id=outside_rec.id
    )
    db.add(dangling_rec)
    db.commit()
    db.refresh(dangling_rec)

    db.add(
        Measurement(
            reconstruction_id=parent_rec.id,
            kind="distance",
            points_json="[]",
            value=1.5,
            unit="m",
        )
    )
    db.add(
        Annotation(reconstruction_id=parent_rec.id, label="crack", lat=1.0, lon=2.0, alt_m=3.0)
    )
    db.commit()

    archive_resp = _archive(client, cfg, session.id)
    assert archive_resp.status_code == 200
    zip_path = archive_resp.json()["bundle_path"]

    restore_resp = _restore(client, cfg, zip_path)
    assert restore_resp.status_code == 200
    result = restore_resp.json()

    new_session_id = result["session_id"]
    assert new_session_id != original_session_id
    # original session untouched (restore must never clobber it)
    assert db.query(SessionModel).filter(SessionModel.id == original_session_id).first() is not None

    new_images = db.query(Image).filter(Image.session_id == new_session_id).all()
    assert len(new_images) == 2
    assert {i.id for i in new_images}.isdisjoint({img1.id, img2.id})

    new_recs = (
        db.query(Reconstruction)
        .filter(Reconstruction.session_id == new_session_id)
        .order_by(Reconstruction.id)
        .all()
    )
    assert len(new_recs) == 3  # parent, child, dangling — outside_rec's session excluded
    new_ids = {r.id for r in new_recs}
    assert new_ids.isdisjoint({parent_rec.id, child_rec.id, dangling_rec.id, outside_rec.id})

    new_parent = next(r for r in new_recs if r.parent_reconstruction_id is None and r.splat_path)
    new_child = next(r for r in new_recs if r.parent_reconstruction_id == new_parent.id)
    new_dangling = next(r for r in new_recs if r.id not in (new_parent.id, new_child.id))
    assert new_dangling.parent_reconstruction_id is None  # dropped: pointed outside the bundle

    new_measurements = (
        db.query(Measurement).filter(Measurement.reconstruction_id == new_parent.id).all()
    )
    assert len(new_measurements) == 1
    assert new_measurements[0].value == 1.5

    new_annotations = (
        db.query(Annotation).filter(Annotation.reconstruction_id == new_parent.id).all()
    )
    assert len(new_annotations) == 1
    assert new_annotations[0].label == "crack"

    # bundled splat artifact was copied back into place and the path rewritten
    assert new_parent.splat_path != str(splat)
    from pathlib import Path
    assert Path(new_parent.splat_path).is_file()


def test_round_trip_child_tables_footprints_flightlogs_defects(client, tmp_path):
    cfg = _cfg(tmp_path)
    db = _db(client)

    session = SessionModel(name="Full Session", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)

    img = Image(session_id=session.id, filename="a.jpg", filepath=str(tmp_path / "a.jpg"))
    db.add(img)
    db.commit()
    db.refresh(img)

    db.add(Footprint(image_id=img.id, geom_wkt="POINT(0 0)", ground_width_m=10.0))

    flight_log = FlightLog(session_id=session.id, filename="log.bin", format="dji")
    db.add(flight_log)
    db.commit()
    db.refresh(flight_log)
    db.add(FlightLogPoint(flight_log_id=flight_log.id, latitude=1.0, longitude=2.0))

    db.add(FlightEntry(session_id=session.id, battery_id="B1", start_pct=100, end_pct=20))
    db.add(SessionLogEntry(session_id=session.id, event_type="import", message="hi"))
    db.add(SessionFrameSelection(session_id=session.id, image_id=img.id))

    defect = Defect(session_id=session.id, category="crack", severity="high")
    db.add(defect)
    db.commit()
    db.refresh(defect)
    db.add(DefectImage(defect_id=defect.id, image_id=img.id))
    db.commit()

    archive_resp = _archive(client, cfg, session.id)
    assert archive_resp.status_code == 200
    zip_path = archive_resp.json()["bundle_path"]

    restore_resp = _restore(client, cfg, zip_path)
    assert restore_resp.status_code == 200
    new_session_id = restore_resp.json()["session_id"]

    new_img = db.query(Image).filter(Image.session_id == new_session_id).first()
    assert new_img is not None

    new_footprint = db.query(Footprint).filter(Footprint.image_id == new_img.id).first()
    assert new_footprint is not None
    assert new_footprint.ground_width_m == 10.0

    new_flight_log = db.query(FlightLog).filter(FlightLog.session_id == new_session_id).first()
    assert new_flight_log is not None
    new_points = (
        db.query(FlightLogPoint).filter(FlightLogPoint.flight_log_id == new_flight_log.id).all()
    )
    assert len(new_points) == 1
    assert new_points[0].latitude == 1.0

    assert (
        db.query(FlightEntry).filter(FlightEntry.session_id == new_session_id).count() == 1
    )
    assert (
        db.query(SessionLogEntry).filter(SessionLogEntry.session_id == new_session_id).count()
        == 1
    )
    assert (
        db.query(SessionFrameSelection)
        .filter(
            SessionFrameSelection.session_id == new_session_id,
            SessionFrameSelection.image_id == new_img.id,
        )
        .count()
        == 1
    )

    new_defect = db.query(Defect).filter(Defect.session_id == new_session_id).first()
    assert new_defect is not None
    assert (
        db.query(DefectImage)
        .filter(DefectImage.defect_id == new_defect.id, DefectImage.image_id == new_img.id)
        .count()
        == 1
    )


def test_restore_drops_project_id_not_included_in_bundle(client, tmp_path):
    cfg = _cfg(tmp_path)
    db = _db(client)
    from backend.db.models import Project

    project = Project(name="P")
    db.add(project)
    db.commit()
    db.refresh(project)

    session = SessionModel(name="Projected", folder_path=str(tmp_path), project_id=project.id)
    db.add(session)
    db.commit()
    db.refresh(session)

    archive_resp = _archive(client, cfg, session.id)
    zip_path = archive_resp.json()["bundle_path"]
    restore_resp = _restore(client, cfg, zip_path)
    new_session_id = restore_resp.json()["session_id"]

    new_session = db.query(SessionModel).filter(SessionModel.id == new_session_id).first()
    assert new_session.project_id is None
