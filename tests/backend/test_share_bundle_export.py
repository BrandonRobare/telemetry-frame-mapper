from __future__ import annotations

import json
import math
import os
import zipfile
from typing import Literal
from unittest.mock import patch

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
                session_id=session.id,
                filename="a.jpg",
                filepath=str(tmp_path / "a.jpg"),
                latitude=10.0,
                longitude=20.0,
                altitude_m=100.0,
            ),
            Image(
                session_id=session.id,
                filename="b.jpg",
                filepath=str(tmp_path / "b.jpg"),
                latitude=11.0,
                longitude=21.0,
                altitude_m=150.0,
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


def _bundle_inputs(client, tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    mesh = exports / "mesh.glb"
    mesh.write_bytes(b"glb" * 4096)
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(
        session_id=session.id, status="complete", mesh_glb_path=str(mesh), frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return exports, exports / f"reconstruction_{rec.id}_share.zip", rec


def test_share_bundle_crash_mid_write_keeps_previous_bundle(client, tmp_path):
    """A crash while rebuilding must leave the previous bundle intact (#641)."""
    from backend.services.share_bundle import build_share_bundle

    exports, bundle, rec = _bundle_inputs(client, tmp_path)
    build_share_bundle(bundle, rec, exports)
    good = bundle.read_bytes()

    real_open = zipfile.ZipFile.open

    def failing_open(self, name, mode: Literal["r", "w"] = "r", *args, **kwargs):
        if name == "artifacts/mesh.glb":
            raise OSError("disk full")
        return real_open(self, name, mode, *args, **kwargs)

    with patch("backend.services.share_bundle.zipfile.ZipFile.open", failing_open):
        with pytest.raises(OSError, match="disk full"):
            build_share_bundle(bundle, rec, exports)

    assert bundle.read_bytes() == good
    with zipfile.ZipFile(bundle) as zf:
        assert zf.testzip() is None
        assert "artifacts/mesh.glb" in zf.namelist()
    assert not list(exports.glob("*.tmp"))


def test_share_bundle_rebuild_never_exposes_a_partial_zip(client, tmp_path):
    """The cesium-ion reader must never see a half-written bundle mid-rebuild (#641)."""
    from backend.services.share_bundle import build_share_bundle

    exports, bundle, rec = _bundle_inputs(client, tmp_path)
    build_share_bundle(bundle, rec, exports)
    good = bundle.read_bytes()

    observed = []
    real_open = zipfile.ZipFile.open

    def observing_open(self, name, mode: Literal["r", "w"] = "r", *args, **kwargs):
        if name == "artifacts/mesh.glb":
            observed.append(bundle.read_bytes())
        return real_open(self, name, mode, *args, **kwargs)

    with patch("backend.services.share_bundle.zipfile.ZipFile.open", observing_open):
        build_share_bundle(bundle, rec, exports)

    assert observed, "the rebuild never reached an artifact write"
    assert all(seen == good for seen in observed)


def test_share_bundle_rejects_path_outside_exports(tmp_path):
    from backend.services.share_bundle import build_share_bundle

    with pytest.raises(ValueError, match="outside exports directory"):
        build_share_bundle(
            tmp_path / "exports" / ".." / "exports2" / "share.zip",
            Reconstruction(),
            tmp_path / "exports",
        )


def test_share_bundle_rejects_parent_symlink_swapped_after_validation(tmp_path):
    """No mkdir/temp/replace may escape through a parent swapped after confinement."""
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    parent = exports / "nested"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    def swap_parent(rec):
        parent.rmdir()
        parent.symlink_to(outside, target_is_directory=True)
        return {"artifacts": {}}

    with (
        patch.object(share_bundle, "build_share_manifest", side_effect=swap_parent),
        patch.object(share_bundle, "build_tileset", return_value={}),
    ):
        with pytest.raises((OSError, ValueError)):
            share_bundle.build_share_bundle(parent / "share.zip", Reconstruction(), exports)
    assert not list(outside.iterdir())


def test_share_bundle_does_not_follow_final_destination_symlink(tmp_path):
    from backend.services.share_bundle import build_share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"unchanged")
    destination = exports / "share.zip"
    destination.symlink_to(victim)
    with pytest.raises(ValueError, match="outside exports directory"):
        build_share_bundle(destination, Reconstruction(), exports)
    assert victim.read_bytes() == b"unchanged"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not support directory-descriptor writes")
def test_share_bundle_publish_uses_open_parent_not_swapped_path(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    parent = exports / "nested"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    artifact = tmp_path / "mesh.glb"
    artifact.write_bytes(b"glb")
    rec = Reconstruction(mesh_glb_path=str(artifact))
    real_open = zipfile.ZipFile.open
    staged_names = []

    def swap_during_write(self, name, mode: Literal["r", "w"] = "r", *args, **kwargs):
        if name == "artifacts/mesh.glb":
            temp_name = next(parent.glob("*.tmp")).name
            staged_names.append(temp_name)
            parent.rename(exports / "parked")
            parent.symlink_to(outside, target_is_directory=True)
            (outside / temp_name).write_bytes(b"attacker")
        return real_open(self, name, mode, *args, **kwargs)

    with (
        patch.object(share_bundle, "build_tileset", return_value={}),
        patch.object(share_bundle.zipfile.ZipFile, "open", swap_during_write),
    ):
        share_bundle.build_share_bundle(parent / "share.zip", rec, exports)
    assert not (outside / "share.zip").exists()
    assert (outside / staged_names[0]).read_bytes() == b"attacker"
    with zipfile.ZipFile(exports / "parked" / "share.zip") as zf:
        assert zf.read("artifacts/mesh.glb") == b"glb"


def test_share_bundle_rejects_unsafe_archive_artifact_name(tmp_path):
    """A POSIX filename with backslashes must not become a traversal on Windows extraction."""
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    artifact = tmp_path / r"..\escape.glb"
    artifact.write_bytes(b"secret")
    rec = Reconstruction(mesh_glb_path=str(artifact))
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(ValueError, match="artifact name"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()


def test_share_bundle_rejects_symlink_artifact(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    target = tmp_path / "private.glb"
    target.write_bytes(b"secret")
    link = tmp_path / "linked.glb"
    link.symlink_to(target)
    rec = Reconstruction(mesh_glb_path=str(link))
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(ValueError, match="symlink artifact"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()
