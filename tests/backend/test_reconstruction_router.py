from __future__ import annotations

import io
import json as _json
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.db.models import Image, JobQueueEntry, Reconstruction, ReconstructionFrame
from backend.db.models import Session as SessionModel
from backend.routers.reconstruction import _status_sse_payload
from backend.services.job_queue import RECONSTRUCTION, claim_stale_jobs, enqueue


def _make_session_with_images(db, count=3):
    s = SessionModel(name="Recon Test", folder_path="/tmp/r", photo_count=count, usable_count=count)
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(count):
        img = Image(
            session_id=s.id,
            filename=f"frame_{i:05d}.jpg",
            filepath=f"/tmp/frame_{i:05d}.jpg",
            usable=True,
            latitude=35.0 + i * 0.001,
            longitude=-80.0,
            altitude_m=100.0,
        )
        db.add(img)
    db.commit()
    return s


def _get_db(client):
    from backend.main import app
    return app.state.test_db_session


def test_start_reconstruction(client):
    db = _get_db(client)
    s = _make_session_with_images(db)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec = Reconstruction(
            id=1, session_id=s.id, status="pending", preset="quick",
            progress_pct=0.0, frames_used=3, step="",
        )
        mock_start.return_value = rec
        resp = client.post("/reconstruction/start", json={"session_id": s.id, "preset": "quick"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["preset"] == "quick"


def test_start_reconstruction_invalid_preset(client):
    resp = client.post("/reconstruction/start", json={"session_id": 1, "preset": "turbo"})
    assert resp.status_code == 422


def test_start_reconstruction_already_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        mock_start.side_effect = ValueError("already in progress")
        resp = client.post("/reconstruction/start", json={"session_id": s.id, "preset": "quick"})

    assert resp.status_code == 409


def test_get_reconstruction_status(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=42.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running_colmap"
    assert data["progress_pct"] == 42.0


def test_get_reconstruction_status_not_found(client):
    resp = client.get("/reconstruction/999999/status")
    assert resp.status_code == 404


def test_get_reconstruction_diagnostics(client, tmp_path):
    db = _get_db(client)
    session = _make_session_with_images(db)
    images = db.query(Image).filter_by(session_id=session.id).order_by(Image.id).all()

    colmap_dir = tmp_path / "colmap"
    sparse_dir = colmap_dir / "sparse" / "0"
    sparse_dir.mkdir(parents=True)
    (sparse_dir / "images.txt").write_text(
        "# comments\n"
        f"1 1 0 0 0 0 0 0 1 {images[0].filename}\n"
        "10 20 -1\n"
        f"2 1 0 0 0 0 0 0 1 {images[2].filename}\n"
        "10 20 -1\n"
    )
    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=3,
        frames_registered=2,
        colmap_dir=str(colmap_dir),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    for image in images:
        db.add(ReconstructionFrame(reconstruction_id=rec.id, image_id=image.id))
    db.commit()

    resp = client.get(f"/reconstruction/{rec.id}/diagnostics")

    assert resp.status_code == 200
    data = resp.json()
    assert data["reconstruction_id"] == rec.id
    assert data["summary"]["frames_used"] == 3
    assert data["summary"]["registered_count"] == 2
    assert data["summary"]["unregistered_count"] == 1
    assert [img["filename"] for img in data["unregistered_images"]] == [images[1].filename]
    assert data["map_heatmap"][0]["filename"] == images[1].filename
    assert any(suggestion["code"] == "retry_guided" for suggestion in data["suggestions"])


def test_get_reconstruction_diagnostics_not_found(client):
    resp = client.get("/reconstruction/999999/diagnostics")
    assert resp.status_code == 404


def test_status_sse_payload_serializes_reconstruction_status(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=42.0, frames_used=3, step="feature matching",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    event = _status_sse_payload(rec)
    event_lines = event.splitlines()
    assert event_lines[0] == "event: status"
    data_line = event_lines[1]
    assert data_line.startswith("data: ")
    data = _json.loads(data_line.removeprefix("data: "))
    assert data["id"] == rec.id
    assert data["status"] == "running_colmap"
    assert data["progress_pct"] == 42.0


def test_stream_reconstruction_status_events_not_found(client):
    resp = client.get("/reconstruction/999999/status/events")
    assert resp.status_code == 404


def test_cancel_reconstruction_requests_stop_without_deleting_record(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=20.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.cancel_reconstruction") as mock_cancel:
        resp = client.post(f"/reconstruction/{rec.id}/cancel")
    assert resp.status_code == 200
    mock_cancel.assert_called_once_with(rec.id)
    data = resp.json()
    assert data["status"] == "cancelling"
    assert data["step"] == "cancelling"
    db.refresh(rec)
    assert rec.status == "cancelling"
    assert db.query(Reconstruction).filter(Reconstruction.id == rec.id).first() is not None


def test_cancel_reconstruction_rejects_stopped_jobs(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.cancel_reconstruction") as mock_cancel:
        resp = client.post(f"/reconstruction/{rec.id}/cancel")
    assert resp.status_code == 409
    mock_cancel.assert_not_called()


def test_cancel_pending_reconstruction_is_terminal_and_can_be_deleted(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=3)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    enqueue(RECONSTRUCTION, rec.id)

    response = client.post(f"/reconstruction/{rec.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert client.delete(f"/reconstruction/{rec.id}").status_code == 200


def test_recovered_stale_reconstruction_can_restart_and_be_deleted(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap", frames_used=3
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    db.add(JobQueueEntry(job_type=RECONSTRUCTION, target_id=rec.id, status="running"))
    db.commit()

    claim_stale_jobs()

    status = client.get(f"/reconstruction/{rec.id}/status")
    assert status.json()["status"] == "failed"
    restart = client.post("/reconstruction/start", json={"session_id": s.id, "preset": "quick"})
    assert restart.status_code == 201
    assert client.delete(f"/reconstruction/{rec.id}").status_code == 200


def test_delete_reconstruction_rejects_running_jobs_without_cleanup(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    artifact = tmp_path / "exports" / "running" / "splat.ply"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact")
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=20.0, frames_used=3, splat_path=str(artifact),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.cleanup_reconstruction_artifacts") as cleanup:
        resp = client.delete(f"/reconstruction/{rec.id}")
    assert resp.status_code == 409
    cleanup.assert_not_called()
    assert artifact.exists()
    assert db.query(Reconstruction).filter(Reconstruction.id == rec.id).first() is not None


def test_delete_reconstruction_removes_artifacts(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    processed_dir = tmp_path / "processed"
    data_dir = tmp_path / "data"
    colmap_dir = data_dir / "colmap" / str(s.id)
    export_dir = exports_dir / "pending"
    colmap_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    splat = export_dir / "splat.ply"
    preview = export_dir / "splat_preview.ply"
    pointcloud = export_dir / "pointcloud.las"
    thumb = processed_dir / "thumbs" / "splat_pending.jpg"
    for path in (splat, preview, pointcloud, thumb):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"artifact")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        colmap_dir=str(colmap_dir), splat_path=str(splat),
        splat_preview_path=str(preview), pointcloud_path=str(pointcloud),
        thumb_path=str(thumb),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    actual_export_dir = exports_dir / str(rec.id)
    export_dir.rename(actual_export_dir)
    rec.splat_path = str(actual_export_dir / "splat.ply")
    rec.splat_preview_path = str(actual_export_dir / "splat_preview.ply")
    rec.pointcloud_path = str(actual_export_dir / "pointcloud.las")
    db.commit()

    cfg = type("Cfg", (), {
        "processed_dir": str(processed_dir),
        "exports_dir": str(exports_dir),
        "data_dir": str(data_dir),
    })()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.delete(f"/reconstruction/{rec.id}")

    assert resp.status_code == 200
    assert not colmap_dir.exists()
    assert not actual_export_dir.exists()
    assert not thumb.exists()


def test_start_reconstruction_with_target_area(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    from backend.db.models import TargetArea
    ta = TargetArea(
        name="Test Area",
        geom_geojson=_json.dumps({
            "type": "Polygon",
            "coordinates": [[[-80.001, 34.99], [-79.999, 34.99],
                             [-79.999, 35.01], [-80.001, 35.01], [-80.001, 34.99]]],
        }),
    )
    db.add(ta)
    db.commit()
    db.refresh(ta)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec = Reconstruction(
            id=1, session_id=s.id, status="pending", preset="quick",
            progress_pct=0.0, frames_used=3, step="",
        )
        mock_start.return_value = rec
        resp = client.post(
            "/reconstruction/start",
            json={"session_id": s.id, "preset": "quick", "target_area_id": ta.id},
        )

    assert resp.status_code == 201
    _args, kwargs = mock_start.call_args
    assert kwargs.get("target_area_geojson") == ta.geom_geojson


def test_start_reconstruction_target_area_not_found(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    resp = client.post(
        "/reconstruction/start",
        json={"session_id": s.id, "preset": "quick", "target_area_id": 999999},
    )
    assert resp.status_code == 404


def test_set_frame_selection(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    from backend.db.models import Image as ImageModel
    image_ids = [img.id for img in db.query(ImageModel).filter_by(session_id=s.id).all()]

    resp = client.post(
        "/reconstruction/frame-selection",
        json={"session_id": s.id, "image_ids": image_ids[:2]},
    )
    assert resp.status_code == 204

    resp2 = client.get(f"/reconstruction/frame-selection/{s.id}")
    assert resp2.status_code == 200
    assert set(resp2.json()["image_ids"]) == set(image_ids[:2])


def test_set_frame_selection_replaces_previous(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    from backend.db.models import Image as ImageModel
    all_ids = [img.id for img in db.query(ImageModel).filter_by(session_id=s.id).all()]

    client.post("/reconstruction/frame-selection",
                json={"session_id": s.id, "image_ids": all_ids})
    client.post("/reconstruction/frame-selection",
                json={"session_id": s.id, "image_ids": [all_ids[0]]})

    resp = client.get(f"/reconstruction/frame-selection/{s.id}")
    assert set(resp.json()["image_ids"]) == {all_ids[0]}


def test_clear_frame_selection(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    from backend.db.models import Image as ImageModel
    image_ids = [img.id for img in db.query(ImageModel).filter_by(session_id=s.id).all()]

    client.post("/reconstruction/frame-selection",
                json={"session_id": s.id, "image_ids": image_ids})
    resp = client.delete(f"/reconstruction/frame-selection/{s.id}")
    assert resp.status_code == 204

    resp2 = client.get(f"/reconstruction/frame-selection/{s.id}")
    assert resp2.json()["image_ids"] == []


def test_get_frame_selection_empty(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    resp = client.get(f"/reconstruction/frame-selection/{s.id}")
    assert resp.status_code == 200
    assert resp.json()["image_ids"] == []


def test_download_splat_not_found(client):
    resp = client.get("/reconstruction/999999/splat")
    assert resp.status_code == 404


def test_download_splat_still_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=50.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/splat")
    assert resp.status_code == 202


def test_download_splat_complete(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    splat_file = exports_dir / "1" / "splat.ply"
    splat_file.parent.mkdir(parents=True)
    splat_file.write_bytes(b"ply data")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.get(f"/reconstruction/{rec.id}/splat?lod=full")
    assert resp.status_code == 200
    assert resp.content == b"ply data"


def test_download_splat_rejects_path_outside_exports(client, tmp_path):
    """splat_path is a DB column, and a crafted session-archive restore could once
    point it anywhere. The download route must confine it the way its sibling in
    share_links.py already does, not trust the stored value."""
    db = _get_db(client)
    s = _make_session_with_images(db)
    secret = tmp_path / "id_rsa"
    secret.write_bytes(b"PRIVATE KEY")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        splat_path=str(secret),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.get(f"/reconstruction/{rec.id}/splat?lod=full")

    assert resp.status_code == 403
    assert b"PRIVATE KEY" not in resp.content


def test_download_splat_invalid_lod(client):
    resp = client.get("/reconstruction/1/splat?lod=tiny")
    assert resp.status_code == 422


def test_download_pointcloud_not_found(client):
    resp = client.get("/reconstruction/999999/pointcloud")
    assert resp.status_code == 404


def test_download_pointcloud_still_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_gsplat",
        progress_pct=95.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/pointcloud")
    assert resp.status_code == 202


def test_download_pointcloud_returns_cached_file(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    exports_dir = tmp_path / "exports"
    pointcloud_file = exports_dir / str(rec.id) / "pointcloud.las"
    pointcloud_file.parent.mkdir(parents=True)
    pointcloud_file.write_bytes(b"las data")

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.get(f"/reconstruction/{rec.id}/pointcloud")

    assert resp.status_code == 200
    assert resp.content == b"las data"
    assert "pointcloud_" in resp.headers["content-disposition"]


def test_download_pointcloud_computes_on_first_call(client, tmp_path):
    from unittest.mock import patch

    db = _get_db(client)
    s = _make_session_with_images(db)
    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    splat_file = tmp_path / "splat.ply"
    splat_file.write_bytes(b"ply data")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        colmap_dir=str(colmap_dir), splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    def fake_export(_colmap_dir, _splat_path, output_path, *, laz_backend=False):
        assert laz_backend is False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"generated las")
        return output_path

    with patch("backend.routers.reconstruction.get_config") as mock_cfg, \
         patch("backend.routers.reconstruction._export_point_cloud", side_effect=fake_export):
        mock_cfg.return_value.exports_dir = str(tmp_path)
        resp = client.get(f"/reconstruction/{rec.id}/pointcloud")

    assert resp.status_code == 200
    assert resp.content == b"generated las"
    db.expire_all()
    db.refresh(rec)
    assert rec.pointcloud_path is not None
    assert Path(rec.pointcloud_path).exists()


def test_generate_mesh_starts_job(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, mesh_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.start_mesh_export", return_value=rec) as mock_start:
        resp = client.post(f"/reconstruction/{rec.id}/mesh")

    assert resp.status_code == 202
    assert resp.json()["mesh_status"] == "pending"
    mock_start.assert_called_once()


def test_generate_mesh_conflict(client):
    with patch("backend.routers.reconstruction.start_mesh_export") as mock_start:
        mock_start.side_effect = ValueError("Mesh export already running for reconstruction 1")
        resp = client.post("/reconstruction/1/mesh")

    assert resp.status_code == 409


def test_get_mesh_status(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, mesh_status="failed", mesh_error="missing dep",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/mesh/status")
    assert resp.status_code == 200
    assert resp.json()["mesh_error"] == "missing dep"


def test_download_mesh_returns_cached_glb(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, mesh_status="complete",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    exports_dir = tmp_path / "exports"
    glb = exports_dir / str(rec.id) / "mesh.glb"
    glb.parent.mkdir(parents=True)
    glb.write_bytes(b"glb")
    rec.mesh_glb_path = str(glb)
    db.commit()

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.get(f"/reconstruction/{rec.id}/mesh?format=glb")

    assert resp.status_code == 200
    assert resp.content == b"glb"
    assert resp.headers["content-type"] == "model/gltf-binary"


def test_download_mesh_rejects_path_outside_exports(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, mesh_status="complete",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    exports_dir = tmp_path / "exports"
    outside = tmp_path / "outside" / "mesh.glb"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"glb")
    rec.mesh_glb_path = str(outside)
    db.commit()

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.get(f"/reconstruction/{rec.id}/mesh?format=glb")

    assert resp.status_code == 403


def test_download_mesh_running_returns_202(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, mesh_status="running",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/mesh?format=obj")
    assert resp.status_code == 202


def test_download_bundle_returns_zip_with_mesh_thumbnail_georef_and_metadata(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    processed_dir = tmp_path / "processed"
    rec_dir = exports_dir / "1"
    rec_dir.mkdir(parents=True)
    processed_dir.mkdir()
    glb = rec_dir / "custom-name.glb"
    glb.write_bytes(b"glb bytes")
    thumb = processed_dir / "thumb.jpg"
    thumb.write_bytes(b"jpeg bytes")
    georef = rec_dir / "mesh_georef.json"
    georef.write_text('{"geo_transform":{"scale":1.0}}')

    rec = Reconstruction(
        id=1,
        session_id=s.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=12,
        frames_registered=10,
        psnr=18.5,
        ssim=0.72,
        mesh_status="complete",
        mesh_glb_path=str(glb),
        thumb_path=str(thumb),
    )
    db.add(rec)
    db.commit()

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        mock_cfg.return_value.processed_dir = str(processed_dir)
        resp = client.get("/reconstruction/1/download-bundle")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert sorted(zf.namelist()) == [
            "mesh.glb",
            "mesh_georef.json",
            "metadata.json",
            "thumbnail.jpg",
        ]
        assert zf.read("mesh.glb") == b"glb bytes"
        assert zf.read("thumbnail.jpg") == b"jpeg bytes"
        assert _json.loads(zf.read("mesh_georef.json"))["geo_transform"]["scale"] == 1.0
        metadata = _json.loads(zf.read("metadata.json"))
    assert metadata["id"] == 1
    assert metadata["session_id"] == s.id
    assert metadata["frames_used"] == 12
    assert metadata["frames_registered"] == 10
    assert metadata["psnr"] == 18.5
    assert metadata["ssim"] == 0.72
    assert metadata["files"]["glb"] == "mesh.glb"
    assert metadata["files"]["thumbnail"] == "thumbnail.jpg"


def test_download_bundle_regenerates_georef_when_missing(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    processed_dir = tmp_path / "processed"
    glb = exports_dir / "1" / "mesh.glb"
    glb.parent.mkdir(parents=True)
    glb.write_bytes(b"glb")
    geo = {
        "scale": 2.0,
        "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [1.0, 2.0, 3.0],
        "utm_zone": "17N",
        "utm_origin": [500000.0, 3869000.0],
    }
    rec = Reconstruction(
        id=1,
        session_id=s.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=3,
        mesh_status="complete",
        mesh_glb_path=str(glb),
        geo_transform=_json.dumps(geo),
    )
    db.add(rec)
    db.commit()

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        mock_cfg.return_value.processed_dir = str(processed_dir)
        resp = client.get("/reconstruction/1/download-bundle")

    assert resp.status_code == 200
    georef = _json.loads((exports_dir / "1" / "mesh_georef.json").read_text())
    assert georef["reconstruction_id"] == 1
    assert georef["geo_transform"] == geo


def test_download_bundle_not_found(client):
    resp = client.get("/reconstruction/999999/download-bundle")
    assert resp.status_code == 404


def test_download_bundle_reconstruction_still_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="running_gsplat",
        progress_pct=50.0,
        frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/download-bundle")
    assert resp.status_code == 202


def test_download_bundle_missing_glb_returns_404(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=3,
        mesh_status="complete",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/download-bundle")
    assert resp.status_code == 404


def test_download_bundle_rejects_glb_path_outside_exports(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)
    outside = tmp_path / "outside" / "mesh.glb"
    outside.parent.mkdir()
    outside.write_bytes(b"glb")
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=3,
        mesh_status="complete",
        mesh_glb_path=str(outside),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path / "exports")
        mock_cfg.return_value.processed_dir = str(tmp_path / "processed")
        resp = client.get(f"/reconstruction/{rec.id}/download-bundle")

    assert resp.status_code == 403


def _bundle_ready_reconstruction(client, tmp_path):
    """Complete reconstruction whose bundle can be built without any real pipeline."""
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    processed_dir = tmp_path / "processed"
    rec_dir = exports_dir / "1"
    rec_dir.mkdir(parents=True)
    processed_dir.mkdir()
    glb = rec_dir / "mesh.glb"
    # Large enough that a torn read shows up as a short body, not a lucky match.
    glb.write_bytes(bytes(range(256)) * 4096)
    (rec_dir / "mesh_georef.json").write_text('{"geo_transform":{"scale":1.0}}')
    db.add(
        Reconstruction(
            id=1,
            session_id=s.id,
            preset="quick",
            status="complete",
            progress_pct=100.0,
            frames_used=3,
            mesh_status="complete",
            mesh_glb_path=str(glb),
        )
    )
    db.commit()
    cfg = SimpleNamespace(exports_dir=str(exports_dir), processed_dir=str(processed_dir))
    return rec_dir, glb, cfg


def test_download_bundle_concurrent_downloads_do_not_share_a_file(client, tmp_path):
    """Two overlapping downloads must build separate archives (#684)."""
    rec_dir, glb, cfg = _bundle_ready_reconstruction(client, tmp_path)

    real_zipfile = zipfile.ZipFile
    barrier = threading.Barrier(2, timeout=30)
    build_paths: list[str] = []
    results: dict[int, object] = {}

    def barriered_zipfile(file, *args, **kwargs):
        build_paths.append(str(file))
        # Hold both requests here so their writes genuinely overlap.
        barrier.wait()
        return real_zipfile(file, *args, **kwargs)

    def download(tag):
        try:
            results[tag] = client.get("/reconstruction/1/download-bundle")
        except BaseException as exc:  # surfaced by the assertions below
            results[tag] = exc

    with (
        patch("backend.routers.reconstruction.get_config", lambda: cfg),
        patch("backend.routers.reconstruction.zipfile.ZipFile", barriered_zipfile),
    ):
        threads = [threading.Thread(target=download, args=(tag,)) for tag in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive()

    assert len(build_paths) == 2
    assert build_paths[0] != build_paths[1], (
        f"concurrent downloads shared one bundle path: {build_paths[0]}"
    )

    for tag in (0, 1):
        resp = results[tag]
        assert not isinstance(resp, BaseException), resp
        assert resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            assert zf.testzip() is None
            assert sorted(zf.namelist()) == ["mesh.glb", "mesh_georef.json", "metadata.json"]
            assert zf.read("mesh.glb") == glb.read_bytes()

    # Both temp bundles are cleaned up once their responses are sent.
    assert sorted(p.name for p in rec_dir.iterdir()) == ["mesh.glb", "mesh_georef.json"]


def test_download_bundle_failed_build_leaves_no_zip_behind(client, tmp_path):
    """A crash mid-build must not leave a partial archive on disk (#684)."""
    rec_dir, _glb, cfg = _bundle_ready_reconstruction(client, tmp_path)

    def exploding_zipfile(file, *args, **kwargs):
        Path(file).write_bytes(b"PK\x03\x04 half-written")
        raise RuntimeError("boom")

    with (
        patch("backend.routers.reconstruction.get_config", lambda: cfg),
        patch("backend.routers.reconstruction.zipfile.ZipFile", exploding_zipfile),
        pytest.raises(RuntimeError, match="boom"),
    ):
        client.get("/reconstruction/1/download-bundle")

    assert sorted(p.name for p in rec_dir.iterdir()) == ["mesh.glb", "mesh_georef.json"]


def test_render_video_validates_keyframes(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(
        f"/reconstruction/{rec.id}/render-video",
        json={"keyframes": [{"position": [0, 0, 3]}]},
    )
    assert resp.status_code == 422


def test_render_video_starts_fallback_job(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, flythrough_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    payload = {
        "keyframes": [
            {"position": [0, 0, 3], "target": [0, 0, 0], "duration_s": 1},
            {"position": [3, 0, 0], "target": [0, 0, 0], "duration_s": 1},
        ]
    }
    with patch("backend.routers.reconstruction.start_flythrough_render", return_value=rec):
        resp = client.post(f"/reconstruction/{rec.id}/render-video", json=payload)

    assert resp.status_code == 202
    assert resp.json()["flythrough_status"] == "pending"


def test_download_flythrough_returns_cached_mp4(client, tmp_path):
    db = _get_db(client)
    s = _make_session_with_images(db)

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, flythrough_status="complete",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    exports_dir = tmp_path / "exports"
    video = exports_dir / str(rec.id) / "flythrough.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.get(f"/reconstruction/{rec.id}/flythrough")

    assert resp.status_code == 200
    assert resp.content == b"mp4"
    assert resp.headers["content-type"] == "video/mp4"


def test_get_geo_transform(client):
    import json as _json
    db = _get_db(client)
    s = _make_session_with_images(db)
    geo = {
        "scale": 1.0,
        "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [0.0, 0.0, 0.0],
        "utm_zone": "17N",
        "utm_origin": [500000.0, 3869000.0],
        "rmse_m": 1.25,
        "trimmed_point_count": 2,
    }
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        geo_transform=_json.dumps(geo),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/geo-transform")
    assert resp.status_code == 200
    data = resp.json()
    assert data["utm_zone"] == "17N"
    assert data["scale"] == 1.0
    assert data["rmse_m"] == 1.25
    assert data["trimmed_point_count"] == 2


def test_get_geo_transform_not_found(client):
    resp = client.get("/reconstruction/999999/geo-transform")
    assert resp.status_code == 404


def test_get_geo_transform_unavailable(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=30.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/geo-transform")
    assert resp.status_code == 404


def test_get_log_empty(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=10.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/log")
    assert resp.status_code == 200
    assert resp.json() == {"lines": []}


def test_get_log_not_found(client):
    resp = client.get("/reconstruction/999999/log")
    assert resp.status_code == 404


def test_get_log_limit_param(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap",
        progress_pct=20.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/log?limit=50")
    assert resp.status_code == 200
    assert "lines" in resp.json()


def test_status_includes_training_metrics(client):
    import json
    db = _get_db(client)
    s = _make_session_with_images(db)
    metrics = [{"iter": 1000, "psnr": 18.2, "ssim": 0.71}]
    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        training_metrics=json.dumps(metrics),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["training_metrics"] is not None
    assert len(data["training_metrics"]) == 1
    assert data["training_metrics"][0]["iter"] == 1000
    assert data["training_metrics"][0]["psnr"] == pytest.approx(18.2)


def test_status_training_metrics_null_when_not_set(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/status")
    assert resp.status_code == 200
    assert resp.json()["training_metrics"] is None


def test_coverage_gaps_404_when_not_found(client):
    resp = client.get("/reconstruction/99999/coverage-gaps")
    assert resp.status_code == 404


def test_coverage_gaps_404_when_not_complete(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(session_id=s.id, status="running_gsplat", preset="quick",
                         progress_pct=50.0, frames_used=3, step="training")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")
    assert resp.status_code == 404


def test_coverage_gaps_returns_cached_json(client, tmp_path):
    import json as json_module
    db = _get_db(client)
    s = _make_session_with_images(db)

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    gaps_file = exports_dir / "gaps.json"
    cells = [{"x": 1.0, "y": 2.0, "z": 3.0, "size": 0.5, "level": "sparse"}]
    gaps_file.write_text(json_module.dumps(cells))

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        splat_path=str(exports_dir / "splat.ply"),
        coverage_gaps_path=str(gaps_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["level"] == "sparse"


def test_coverage_gaps_rejects_cache_path_outside_exports(client, tmp_path):
    """coverage_gaps_path is read straight off the DB row and returned to the client,
    so it needs the same containment as every other stored artifact path."""
    db = _get_db(client)
    s = _make_session_with_images(db)
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    secret = tmp_path / "secrets.json"
    secret.write_text('{"token": "leaked"}')

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        splat_path=str(exports_dir / "splat.ply"),
        coverage_gaps_path=str(secret),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")

    assert resp.status_code == 403
    assert b"leaked" not in resp.content


def test_coverage_gaps_computes_on_first_call(client, tmp_path):
    import numpy as np

    db = _get_db(client)
    s = _make_session_with_images(db)

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    ply_path = exports_dir / "splat.ply"
    header = (
        b"ply\nformat binary_little_endian 1.0\n"
        b"element vertex 4\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"end_header\n"
    )
    arr = np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0], [5, 5, 5]], dtype=np.float32)
    ply_path.write_bytes(header + arr.tobytes())

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        splat_path=str(ply_path),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with patch("backend.routers.reconstruction.get_config", return_value=cfg):
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Verify coverage_gaps_path stored on record
    db.expire_all()
    db.refresh(rec)
    assert rec.coverage_gaps_path is not None
    assert rec.coverage_gaps_path == str(ply_path.parent / f"coverage_gaps_{rec.id}.json")


def test_coverage_gaps_returns_cells_when_cache_path_commit_fails(client, tmp_path):
    from unittest.mock import patch

    import numpy as np

    db = _get_db(client)
    s = _make_session_with_images(db)

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    ply_path = exports_dir / "splat.ply"
    header = (
        b"ply\nformat binary_little_endian 1.0\n"
        b"element vertex 4\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"end_header\n"
    )
    arr = np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0], [5, 5, 5]], dtype=np.float32)
    ply_path.write_bytes(header + arr.tobytes())

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        splat_path=str(ply_path),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    cfg = type("Cfg", (), {"exports_dir": str(exports_dir), "processed_dir": str(tmp_path)})()
    with (
        patch("backend.routers.reconstruction.get_config", return_value=cfg),
        patch.object(db, "commit", side_effect=RuntimeError("commit failed")),
    ):
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# cleanup route
# ---------------------------------------------------------------------------


def test_cleanup_not_found(client):
    resp = client.post("/reconstruction/999999/cleanup")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_cleanup_still_running(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_gsplat",
        progress_pct=95.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(f"/reconstruction/{rec.id}/cleanup")
    assert resp.status_code == 422
    assert "must be complete" in resp.json()["detail"]


def test_cleanup_no_splat_path(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(f"/reconstruction/{rec.id}/cleanup")
    assert resp.status_code == 404
    assert "no splat" in resp.json()["detail"].lower()


def test_cleanup_splat_missing_on_disk(client):
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        splat_path="/tmp/nonexistent_splat_cleanup_test.ply",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(f"/reconstruction/{rec.id}/cleanup")
    assert resp.status_code == 404
    assert "not found on disk" in resp.json()["detail"].lower()


def test_cleanup_succeeds(client, tmp_path):
    import numpy as np

    from backend.services.ply_io import GaussianCloud, write_3dgs_ply

    db = _get_db(client)
    s = _make_session_with_images(db)

    # Write a valid 3DGS PLY file.
    n = 30
    rng = np.random.default_rng(42)
    cloud = GaussianCloud(
        means=rng.normal(size=(n, 3)).astype(np.float32),
        sh0=rng.normal(size=(n, 3)).astype(np.float32),
        shN=rng.normal(size=(n, 0, 3)).astype(np.float32),
        opacities=rng.normal(size=(n,)).astype(np.float32),
        scales=rng.normal(scale=0.5, size=(n, 3)).astype(np.float32),
        quats=rng.normal(size=(n, 4)).astype(np.float32),
    )
    exports_dir = tmp_path / "exports"
    rec_dir = exports_dir / "100"  # will match rec.id after DB insert
    rec_dir.mkdir(parents=True)
    splat_file = rec_dir / "splat.ply"
    write_3dgs_ply(splat_file, cloud)

    rec = Reconstruction(
        id=100, session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.post(f"/reconstruction/{rec.id}/cleanup")

    assert resp.status_code == 201
    data = resp.json()
    assert data["n_before"] == n
    assert 1 <= data["n_after"] <= n
    assert data["cleaned_path"].endswith("splat_cleaned.ply")
    assert "n_before" in data["stats"]
    assert "n_after_opacity" in data["stats"]
    assert "n_after_outlier" in data["stats"]

    # Original file untouched.
    assert splat_file.exists()
    from backend.services.ply_io import read_3dgs_ply
    original = read_3dgs_ply(splat_file)
    assert original.means.shape[0] == n

    # Cleaned file exists and is valid.
    cleaned_path = tmp_path / "exports" / "100" / "splat_cleaned.ply"
    assert cleaned_path.exists()
    cleaned = read_3dgs_ply(cleaned_path)
    assert cleaned.means.shape[0] == data["n_after"]


def test_cleanup_with_target_area_crops_splat(client, tmp_path):
    import numpy as np

    from backend.db.models import TargetArea
    from backend.services.ply_io import GaussianCloud, read_3dgs_ply, write_3dgs_ply

    db = _get_db(client)
    s = _make_session_with_images(db)
    target = TargetArea(
        name="crop",
        geom_geojson='{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}',
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    exports_dir = tmp_path / "exports"
    rec_dir = exports_dir / "101"
    rec_dir.mkdir(parents=True)
    splat_file = rec_dir / "splat.ply"
    cloud = GaussianCloud(
        means=np.array([[0.5, 0.5, 0.0], [2.0, 2.0, 0.0], [-1.0, 0.5, 0.0]], dtype=np.float32),
        sh0=np.zeros((3, 3), dtype=np.float32),
        shN=np.zeros((3, 0, 3), dtype=np.float32),
        opacities=np.ones(3, dtype=np.float32),
        scales=np.zeros((3, 3), dtype=np.float32),
        quats=np.zeros((3, 4), dtype=np.float32),
    )
    write_3dgs_ply(splat_file, cloud)

    rec = Reconstruction(
        id=101, session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.post(
            f"/reconstruction/{rec.id}/cleanup",
            json={"target_area_id": target.id, "opacity_keep_ratio": 1.0, "outlier_k": 0},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["stats"]["target_area_clipped"] == 2
    assert data["n_after"] == 1
    cleaned = read_3dgs_ply(exports_dir / "101" / "splat_cleaned.ply")
    assert cleaned.means.shape[0] == 1
    assert cleaned.means[0].tolist() == [0.5, 0.5, 0.0]


def test_cleanup_target_area_not_found(client, tmp_path):
    import numpy as np

    from backend.services.ply_io import GaussianCloud, write_3dgs_ply

    db = _get_db(client)
    s = _make_session_with_images(db)
    splat_file = tmp_path / "splat.ply"
    cloud = GaussianCloud(
        means=np.zeros((1, 3), dtype=np.float32),
        sh0=np.zeros((1, 3), dtype=np.float32),
        shN=np.zeros((1, 0, 3), dtype=np.float32),
        opacities=np.ones(1, dtype=np.float32),
        scales=np.zeros((1, 3), dtype=np.float32),
        quats=np.zeros((1, 4), dtype=np.float32),
    )
    write_3dgs_ply(splat_file, cloud)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.post(f"/reconstruction/{rec.id}/cleanup", json={"target_area_id": 999999})

    assert resp.status_code == 404
    assert "target area" in resp.json()["detail"].lower()


def test_download_pointcloud_laz_format_requested(client, tmp_path):
    """GET /reconstruction/{id}/pointcloud?format=laz returns .laz content type."""
    from unittest.mock import patch

    db = _get_db(client)
    s = _make_session_with_images(db)
    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    splat_file = tmp_path / "splat.ply"
    splat_file.write_bytes(b"ply data")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        colmap_dir=str(colmap_dir), splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    def fake_export(_colmap_dir, _splat_path, output_path, *, laz_backend=False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"compressed laz data")
        return output_path

    with patch("backend.routers.reconstruction.get_config") as mock_cfg, \
         patch("backend.routers.reconstruction._export_point_cloud", side_effect=fake_export):
        mock_cfg.return_value.exports_dir = str(tmp_path)
        resp = client.get(f"/reconstruction/{rec.id}/pointcloud?format=laz")

    assert resp.status_code == 200
    assert resp.content == b"compressed laz data"
    assert "pointcloud_" in resp.headers["content-disposition"]
    assert ".laz" in resp.headers["content-disposition"]


def test_download_pointcloud_format_validation(client):
    """Query parameter format must be 'las' or 'laz'."""
    db = _get_db(client)
    s = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/pointcloud?format=xyz")
    assert resp.status_code == 422  # FastAPI query validation


def test_semantic_label_routes_lifecycle_and_overlay(client, tmp_path):
    from unittest.mock import patch

    import numpy as np

    from backend.services.ply_io import GaussianCloud, write_3dgs_ply
    from backend.services.semantic_labels import write_sidecar

    db = _get_db(client)
    session = _make_session_with_images(db)
    cloud = GaussianCloud(
        means=np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float32),
        sh0=np.zeros((2, 3), dtype=np.float32),
        shN=np.zeros((2, 0, 3), dtype=np.float32),
        opacities=np.array([0.1, 0.9], dtype=np.float32),
        scales=np.zeros((2, 3), dtype=np.float32),
        quats=np.tile(np.array([1, 0, 0, 0], dtype=np.float32), (2, 1)),
    )
    splat = write_3dgs_ply(tmp_path / "splat.ply", cloud)
    sidecar = write_sidecar(
        tmp_path,
        labels=np.array([0, 1], dtype=np.uint8),
        confidence=np.ones(2, dtype=np.float16),
        labels_medium=np.array([1], dtype=np.uint8),
        labels_preview=np.array([1], dtype=np.uint8),
    )
    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=2,
        splat_path=str(splat),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    def fake_start(rec_id, db_arg):
        started = db_arg.query(Reconstruction).filter(Reconstruction.id == rec_id).first()
        started.semantic_status = "complete"
        started.semantic_labels_path = str(sidecar)
        db_arg.commit()
        db_arg.refresh(started)
        return started

    with patch("backend.routers.reconstruction.start_semantic_labeling", side_effect=fake_start):
        start = client.post(f"/reconstruction/{rec.id}/semantic-labels")
    assert start.status_code == 202
    assert start.json()["semantic_status"] == "complete"

    status = client.get(f"/reconstruction/{rec.id}/semantic-labels/status")
    assert status.status_code == 200
    assert status.json()["semantic_labels_path"] == str(sidecar)

    summary = client.get(f"/reconstruction/{rec.id}/semantic-labels?lod=preview")
    assert summary.status_code == 200
    assert summary.json()["class_counts"]["vegetation"] == 1

    overlay = client.get(f"/reconstruction/{rec.id}/semantic-labels/overlay?lod=preview")
    assert overlay.status_code == 200
    assert overlay.content[:4] == (1).to_bytes(4, "little")


def test_semantic_label_start_error_matrix(client, tmp_path):
    db = _get_db(client)
    session = _make_session_with_images(db)
    rec = Reconstruction(
        session_id=session.id,
        preset="quick",
        status="complete",
        progress_pct=100.0,
        frames_used=2,
        splat_path=str(tmp_path / "missing.ply"),
        semantic_status="running",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch("backend.routers.reconstruction.start_semantic_labeling") as mock_start:
        mock_start.side_effect = ValueError(
            "Semantic labeling already running for reconstruction 1"
        )
        assert client.post(f"/reconstruction/{rec.id}/semantic-labels").status_code == 409
        mock_start.side_effect = ValueError("Splat file not found on disk")
        assert client.post(f"/reconstruction/{rec.id}/semantic-labels").status_code == 404
        mock_start.side_effect = ValueError(
            "Reconstruction must be complete before semantic labeling"
        )
        assert client.post(f"/reconstruction/{rec.id}/semantic-labels").status_code == 422


# ---------------------------------------------------------------------------
# Multi-session reconstruction tests
# ---------------------------------------------------------------------------


def _make_session_named(db, name):
    s = SessionModel(name=name, folder_path=f"/tmp/{name.lower().replace(' ', '_')}",
                     photo_count=3, usable_count=3)
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(3):
        db.add(Image(
            session_id=s.id,
            filename=f"{name}_frame_{i:05d}.jpg",
            filepath=f"/tmp/{name}_frame_{i:05d}.jpg",
            usable=True,
            latitude=35.0 + i * 0.001,
            longitude=-80.0,
            altitude_m=100.0,
        ))
    db.commit()
    return s


def test_start_reconstruction_multi_session(client):
    db = _get_db(client)
    s1 = _make_session_named(db, "Flight A")
    s2 = _make_session_named(db, "Flight B")

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec_mock = Reconstruction(
            id=100, session_id=s1.id, preset="quick", status="pending",
            progress_pct=0.0, step="", frames_used=6,
            source_session_ids=_json.dumps([s1.id, s2.id]),
        )
        mock_start.return_value = rec_mock
        resp = client.post("/reconstruction/start", json={
            "session_ids": [s1.id, s2.id],
            "preset": "quick",
        })

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == 100
    assert data["source_session_ids"] == [s1.id, s2.id]
    kwargs = mock_start.call_args.kwargs
    assert kwargs["source_session_ids"] == [s1.id, s2.id]
    assert mock_start.call_args.args[0] == s1.id


def test_start_reconstruction_multi_session_missing_sessions(client):
    db = _get_db(client)
    s1 = _make_session_named(db, "Flight A")

    resp = client.post("/reconstruction/start", json={
        "session_ids": [s1.id, 99999],
        "preset": "quick",
    })
    assert resp.status_code == 422


def test_start_reconstruction_session_ids_empty_list(client):
    resp = client.post("/reconstruction/start", json={
        "session_ids": [],
        "preset": "quick",
    })
    assert resp.status_code == 422


def test_start_reconstruction_both_session_id_and_session_ids(client):
    db = _get_db(client)
    s1 = _make_session_named(db, "Flight A")
    s2 = _make_session_named(db, "Flight B")

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec_mock = Reconstruction(
            id=101, session_id=s1.id, preset="full", status="pending",
            progress_pct=0.0, step="", frames_used=6,
            source_session_ids=_json.dumps([s1.id, s2.id]),
        )
        mock_start.return_value = rec_mock
        resp = client.post("/reconstruction/start", json={
            "session_id": 99999,
            "session_ids": [s1.id, s2.id],
            "preset": "full",
        })

    assert resp.status_code == 201
    kwargs = mock_start.call_args.kwargs
    assert kwargs["source_session_ids"] == [s1.id, s2.id]


def test_start_reconstruction_multi_session_with_target_area(client):
    db = _get_db(client)
    s1 = _make_session_named(db, "Flight A")
    s2 = _make_session_named(db, "Flight B")

    from backend.db.models import TargetArea as TargetAreaModel
    target_area_geojson = (
        '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    )
    ta = TargetAreaModel(name="Test Area", geom_geojson=target_area_geojson)
    db.add(ta)
    db.commit()
    db.refresh(ta)

    with patch("backend.routers.reconstruction.start_reconstruction") as mock_start:
        rec_mock = Reconstruction(
            id=102, session_id=s1.id, preset="quick", status="pending",
            progress_pct=0.0, step="", frames_used=4,
            source_session_ids=_json.dumps([s1.id, s2.id]),
        )
        mock_start.return_value = rec_mock
        resp = client.post("/reconstruction/start", json={
            "session_ids": [s1.id, s2.id],
            "preset": "quick",
            "target_area_id": ta.id,
        })

    assert resp.status_code == 201
    kwargs = mock_start.call_args.kwargs
    assert kwargs["source_session_ids"] == [s1.id, s2.id]
    assert kwargs["target_area_geojson"] == ta.geom_geojson


def test_list_all_jobs_includes_source_session_ids(client):
    db = _get_db(client)
    s1 = _make_session_named(db, "Flight A")
    s2 = _make_session_named(db, "Flight B")
    rec = Reconstruction(
        session_id=s1.id, preset="quick", status="pending",
        progress_pct=0.0, step="", frames_used=4,
        source_session_ids=_json.dumps([s1.id, s2.id]),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get("/jobs/")
    assert resp.status_code == 200
    assert resp.json()
    found = [j for j in resp.json() if j["id"] == rec.id]
    assert len(found) == 1
    assert found[0]["source_session_ids"] == [s1.id, s2.id]


def test_splat_transform_cleanup_failed_subprocess_is_not_201(client, tmp_path):
    """A failed npx run must not return 201 advertising a cleaned_path that was
    never written (#645)."""
    db = _get_db(client)
    s = _make_session_with_images(db)

    exports_dir = tmp_path / "exports"
    rec_dir = exports_dir / "645"
    rec_dir.mkdir(parents=True)
    splat_file = rec_dir / "splat.ply"
    splat_file.write_bytes(b"ply data")

    rec = Reconstruction(
        id=645, session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3, splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    probe = {"available": True, "node_path": "/usr/bin/node", "npx_path": "/usr/bin/npx"}
    failed = SimpleNamespace(returncode=1, stdout="", stderr="npm ERR! network unreachable")
    with (
        patch("backend.routers.reconstruction.get_config") as mock_cfg,
        patch("backend.services.splat_transform.splat_transform_available", return_value=probe),
        patch("backend.services.splat_transform.subprocess.run", return_value=failed),
    ):
        mock_cfg.return_value.exports_dir = str(exports_dir)
        resp = client.post(f"/reconstruction/{rec.id}/splat-transform-cleanup")

    assert resp.status_code == 422
    assert "network unreachable" in resp.json()["detail"]
    assert not (rec_dir / "splat_transform_cleaned.ply").exists()
