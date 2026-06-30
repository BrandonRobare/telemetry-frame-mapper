import zipfile

import backend.routers.export as export_router
from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def test_share_bundle_contains_viewer_manifest_and_tileset(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    mesh = tmp_path / "mesh.glb"
    mesh.write_bytes(b"glb")
    db = _db(client)
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)
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
    assert {"manifest.json", "index.html", "tileset.json", "artifacts/mesh.glb"} <= names
