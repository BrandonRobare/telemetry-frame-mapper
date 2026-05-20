from __future__ import annotations

import json as _json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel


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


def test_cancel_reconstruction(client):
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
        resp = client.delete(f"/reconstruction/{rec.id}")
    assert resp.status_code == 200
    mock_cancel.assert_called_once_with(rec.id)


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

    with patch("backend.routers.reconstruction.get_config") as mock_cfg:
        mock_cfg.return_value.exports_dir = str(tmp_path)
        resp = client.get(f"/reconstruction/{rec.id}/coverage-gaps")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Verify coverage_gaps_path stored on record
    db.expire_all()
    db.refresh(rec)
    assert rec.coverage_gaps_path is not None
