from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.routers.export as export_router
from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def _complete_mesh_reconstruction(client, exports_dir: Path, *, obj_path: Path | None = None):
    db = _db(client)
    session = SessionModel(name="S", folder_path=str(exports_dir))
    db.add(session)
    db.commit()
    db.refresh(session)
    obj_path = obj_path or exports_dir / "source" / "mesh.obj"
    glb_path = exports_dir / "source" / "mesh.glb"
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    if not obj_path.exists():
        obj_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    glb_path.write_bytes(b"glb")
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        frames_used=1,
        mesh_glb_path=str(glb_path),
        mesh_obj_path=str(obj_path),
        geo_transform=json.dumps({
            "scale": 2.0,
            "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [3, 4, 5],
            "utm_zone": "17N",
            "utm_origin": [500000, 4000000],
        }),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_usd_handoff_contains_real_mesh_and_georeferencing(client, tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(
        export_router, "get_config", lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})()
    )
    rec = _complete_mesh_reconstruction(client, exports_dir)

    response = client.get(f"/export/reconstructions/{rec.id}/usd")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    bundle_path = exports_dir / str(rec.id) / f"mesh_{rec.id}_usd_handoff.zip"
    with zipfile.ZipFile(bundle_path) as bundle:
        assert set(bundle.namelist()) == {
            "mesh.usda", "mesh.usd.georef.json", "source/mesh.obj", "source/mesh.glb"
        }
        usda = bundle.read("mesh.usda").decode()
        metadata = json.loads(bundle.read("mesh.usd.georef.json"))
    assert usda.startswith("#usda 1.0")
    assert 'def Mesh "ReconstructionMesh"' in usda
    assert "point3f[] points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]" in usda
    assert "int[] faceVertexIndices = [0, 1, 2]" in usda
    assert metadata["geo_transform"]["utm_zone"] == "17N"
    assert "without an accuracy claim" in metadata["accuracy"]


def test_usd_handoff_crash_mid_write_keeps_previous_bundle(client, tmp_path, monkeypatch):
    """A crash while rebuilding the handoff ZIP must leave the previous one intact (#641)."""
    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(
        export_router, "get_config", lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})()
    )
    rec = _complete_mesh_reconstruction(client, exports_dir)
    assert client.get(f"/export/reconstructions/{rec.id}/usd").status_code == 200
    bundle_path = exports_dir / str(rec.id) / f"mesh_{rec.id}_usd_handoff.zip"
    good = bundle_path.read_bytes()

    with patch(
        "backend.routers.export.zipfile.ZipFile.write", side_effect=OSError("disk full")
    ):
        response = client.get(f"/export/reconstructions/{rec.id}/usd")

    assert response.status_code == 422
    assert bundle_path.read_bytes() == good
    with zipfile.ZipFile(bundle_path) as bundle:
        assert bundle.testzip() is None
    assert not list(bundle_path.parent.glob("*.tmp"))


def test_usda_crash_mid_write_keeps_previous_mesh(tmp_path):
    """A failed usda replace must not destroy the mesh.usda already on disk (#641)."""
    from backend.services.usd_export import write_usda_handoff

    output_dir = tmp_path / "exports" / "1"
    source = tmp_path / "mesh.obj"
    source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    usda_path, sidecar_path = write_usda_handoff(
        output_dir, source, reconstruction_id=1, session_id=1, geo_transform={}
    )
    good_usda = usda_path.read_text(encoding="utf-8")
    good_sidecar = sidecar_path.read_text(encoding="utf-8")

    source.write_text("v 9 9 9\nv 8 0 0\nv 0 8 0\nf 1 2 3\n", encoding="utf-8")
    with patch("backend.services.usd_export.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            write_usda_handoff(
                output_dir, source, reconstruction_id=1, session_id=1, geo_transform={}
            )

    assert usda_path.read_text(encoding="utf-8") == good_usda
    assert sidecar_path.read_text(encoding="utf-8") == good_sidecar
    assert not list(output_dir.glob("*.tmp"))


def test_usd_handoff_rejects_obj_outside_exports(client, tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(
        export_router, "get_config", lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})()
    )
    outside_mesh = tmp_path / "outside.obj"
    rec = _complete_mesh_reconstruction(client, exports_dir, obj_path=outside_mesh)

    response = client.get(f"/export/reconstructions/{rec.id}/usd")

    assert response.status_code == 422
    assert "outside exports directory" in response.json()["detail"]


def test_usd_handoff_requires_obj_geometry(client, tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(
        export_router, "get_config", lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})()
    )
    rec = _complete_mesh_reconstruction(client, exports_dir)
    db = _db(client)
    db.query(Reconstruction).filter(Reconstruction.id == rec.id).update({"mesh_obj_path": None})
    db.commit()

    response = client.get(f"/export/reconstructions/{rec.id}/usd")

    assert response.status_code == 422
    assert response.json()["detail"] == "USD geometry export requires an existing OBJ mesh"
