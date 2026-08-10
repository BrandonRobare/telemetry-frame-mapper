import json
import math
import zipfile

import pytest

import backend.routers.export as export_router
from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def _make_session_with_gps_images(db, tmp_path):
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add_all(
        [
            Image(
                session_id=session.id, filename="a.jpg", filepath=str(tmp_path / "a.jpg"),
                latitude=10.0, longitude=20.0, altitude_m=100.0,
            ),
            Image(
                session_id=session.id, filename="b.jpg", filepath=str(tmp_path / "b.jpg"),
                latitude=11.0, longitude=21.0, altitude_m=150.0,
            ),
        ]
    )
    db.commit()
    return session


def test_share_bundle_contains_viewer_manifest_and_tileset(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(b"glb")
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(
        session_id=session.id, status="complete", mesh_glb_path=str(mesh), frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    body = client.post(f"/export/reconstructions/{rec.id}/share-bundle").json()
    assert body["cesium"]["tileset_json"] == "tileset.json"
    with zipfile.ZipFile(body["bundle_path"]) as zf:
        names = set(zf.namelist())
        tileset = json.loads(zf.read("tileset.json"))
    assert {"manifest.json", "index.html", "tileset.json", "artifacts/mesh.glb"} <= names

    assert tileset["asset"]["version"] == "1.1"
    assert tileset["geometricError"] > 0
    root = tileset["root"]
    region = root["boundingVolume"]["region"]
    assert region != [0, 0, 0, 0, 0, 0]
    assert region[0] == math.radians(20.0)  # west
    assert region[1] == math.radians(10.0)  # south
    assert region[2] == math.radians(21.0)  # east
    assert region[3] == math.radians(11.0)  # north
    assert region[4] == 100.0  # minHeight
    assert region[5] == 150.0  # maxHeight
    assert len(root["transform"]) == 16
    assert root["content"]["uri"] == "artifacts/mesh.glb"


def test_share_bundle_tileset_valid_without_glb(client, tmp_path, monkeypatch):
    """No mesh_glb_path (or file missing) -> still a valid, non-degenerate tileset, no content."""
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(session_id=session.id, status="complete", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    body = client.post(f"/export/reconstructions/{rec.id}/share-bundle").json()
    with zipfile.ZipFile(body["bundle_path"]) as zf:
        tileset = json.loads(zf.read("tileset.json"))
    root = tileset["root"]
    assert root["boundingVolume"]["region"] != [0, 0, 0, 0, 0, 0]
    assert tileset["geometricError"] > 0
    assert "content" not in root


def test_share_bundle_rejects_path_outside_exports(tmp_path):
    from backend.services.share_bundle import build_share_bundle

    with pytest.raises(ValueError, match="outside exports directory"):
        build_share_bundle(
            tmp_path / "exports" / ".." / "exports2" / "share.zip",
            Reconstruction(),
            tmp_path / "exports",
        )
