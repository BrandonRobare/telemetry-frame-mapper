from __future__ import annotations

import json as _json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.db.models import Image, Reconstruction, ReconstructionFrame
from backend.db.models import Session as SessionModel
from backend.routers.reconstruction import _status_sse_payload


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
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


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
    splat_file = tmp_path / "splat.ply"
    splat_file.write_bytes(b"ply data")

    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete",
        progress_pct=100.0, frames_used=3,
        splat_path=str(splat_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/splat?lod=full")
    assert resp.status_code == 200
    assert resp.content == b"ply data"


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

    def fake_export(_colmap_dir, _splat_path, output_path):
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
    bundle_path = rec_dir / "reconstruction_1_bundle.zip"
    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path) as zf:
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

    gaps_file = tmp_path / "gaps.json"
    cells = [{"x": 1.0, "y": 2.0, "z": 3.0, "size": 0.5, "level": "sparse"}]
    gaps_file.write_text(json_module.dumps(cells))

    rec = Reconstruction(
        session_id=s.id, status="complete", preset="quick",
        progress_pct=100.0, frames_used=3, step="done",
        splat_path=str(tmp_path / "splat.ply"),
        coverage_gaps_path=str(gaps_file),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["level"] == "sparse"


def test_coverage_gaps_computes_on_first_call(client, tmp_path):
    from unittest.mock import patch

    import numpy as np

    db = _get_db(client)
    s = _make_session_with_images(db)

    ply_path = tmp_path / "splat.ply"
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

    with patch("backend.routers.reconstruction.get_config") as mock_cfg, \
         patch("backend.services.reconstruction.get_config") as mock_svc_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        mock_svc_cfg.return_value.exports_dir = str(tmp_path)
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Verify coverage_gaps_path stored on record
    db.expire_all()
    db.refresh(rec)
    assert rec.coverage_gaps_path is not None
