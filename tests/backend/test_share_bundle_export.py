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


# A solved COLMAP->UTM transform near the fixture images (34N, 20.5E 10.5N): yawed
# 30 degrees, scaled 2x and translated, so an ignored transform is visibly misplaced.
_COS30, _SIN30 = math.cos(math.radians(30)), math.sin(math.radians(30))
_GEO = {
    "scale": 2.0,
    "rotation": [[_COS30, -_SIN30, 0.0], [_SIN30, _COS30, 0.0], [0.0, 0.0, 1.0]],
    "translation": [5.0, -3.0, 20.0],
    "utm_zone": "34N",
    "utm_origin": [445287.0, 1160738.0],
}


def _placed_colmap_origin_ecef() -> tuple[float, float, float]:
    """Where the tileset must put the mesh's (0, 0, 0): through the stored transform."""
    from pyproj import Transformer

    from backend.services.cesium_tiles import geodetic_to_ecef

    easting = _GEO["utm_origin"][0] + _GEO["translation"][0]
    northing = _GEO["utm_origin"][1] + _GEO["translation"][1]
    lon, lat = Transformer.from_crs(32634, 4326, always_xy=True).transform(easting, northing)
    return geodetic_to_ecef(math.radians(lat), math.radians(lon), _GEO["translation"][2])


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
    (tmp_path / "exports").mkdir()
    mesh = tmp_path / "exports" / "mesh.glb"
    mesh.write_bytes(b"glb")
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        mesh_glb_path=str(mesh),
        frames_used=1,
        geo_transform=json.dumps(_GEO),
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
    # The mesh's COLMAP origin goes where the stored geo_transform says, not to an
    # image-GPS centroid (#950). The matrix is column-major: [12:15] is the translation.
    placed = root["transform"][12:15]
    assert math.dist(placed, _placed_colmap_origin_ecef()) < 0.01
    assert root["content"]["uri"] == "artifacts/mesh.glb"


def test_share_bundle_without_geo_transform_omits_only_the_tileset(client, tmp_path, monkeypatch):
    """NULL geo_transform: still share the artifacts, but place nothing on the globe (#950)."""
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports)})(),
    )
    exports.mkdir()
    mesh = exports / "mesh.glb"
    mesh.write_bytes(b"glb")
    splat = exports / "splat.ply"
    splat.write_bytes(b"ply")
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        mesh_glb_path=str(mesh),
        splat_path=str(splat),
        frames_used=1,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    with patch.object(share_bundle, "build_tileset") as tileset:
        resp = client.post(f"/export/reconstructions/{rec.id}/share-bundle")

    assert resp.status_code == 200
    body = resp.json()
    tileset.assert_not_called()
    with zipfile.ZipFile(body["bundle_path"]) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert {"manifest.json", "index.html", "artifacts/mesh.glb", "artifacts/splat.ply"} <= names
    assert "tileset.json" not in names
    for cesium in (body["cesium"], manifest["cesium"]):
        assert cesium["tileset_json"] is None
        assert f"reconstruction {rec.id} is not georeferenced" in cesium["tileset_omitted_reason"]


def test_share_bundle_manifest_names_the_tileset_only_when_georeferenced():
    from backend.services.share_bundle import build_share_manifest

    placed = build_share_manifest(Reconstruction(id=5, geo_transform=json.dumps(_GEO)))
    unplaced = build_share_manifest(Reconstruction(id=6))

    assert placed["cesium"]["tileset_json"] == "tileset.json"
    assert "tileset_omitted_reason" not in placed["cesium"]
    assert unplaced["cesium"]["tileset_json"] is None
    assert "not georeferenced" in unplaced["cesium"]["tileset_omitted_reason"]


def test_share_bundle_tileset_valid_without_glb(client, tmp_path, monkeypatch):
    """No mesh_glb_path (or file missing) -> still a valid, non-degenerate tileset, no content."""
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    db = _db(client)
    session = _make_session_with_gps_images(db, tmp_path)
    rec = Reconstruction(
        session_id=session.id, status="complete", frames_used=1, geo_transform=json.dumps(_GEO)
    )
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
        session_id=session.id,
        status="complete",
        mesh_glb_path=str(mesh),
        frames_used=1,
        geo_transform=json.dumps(_GEO),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return exports, exports / f"reconstruction_{rec.id}_share.zip", rec


def test_share_bundle_manifest_uses_bundle_relative_paths(client, tmp_path):
    """A shared bundle must not reveal server paths, and its manifest must resolve in-bundle."""
    from backend.services.share_bundle import build_share_bundle

    exports, bundle, rec = _bundle_inputs(client, tmp_path)
    splat = exports / "nested" / "splat.ply"
    splat.parent.mkdir()
    splat.write_bytes(b"ply")
    rec.splat_path = str(splat)
    rec.pointcloud_path = str(exports / "missing.las")  # recorded, but gone from disk

    returned = build_share_bundle(bundle, rec, exports)

    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        manifest_text = zf.read("manifest.json").decode()
        index_html = zf.read("index.html").decode()
    manifest = json.loads(manifest_text)
    expected = {"mesh_glb": "artifacts/mesh.glb", "splat_ply": "artifacts/splat.ply"}
    assert manifest["artifacts"] == expected
    assert returned["artifacts"] == expected
    assert set(manifest["artifacts"].values()) <= names
    for text in (manifest_text, index_html):
        assert str(tmp_path) not in text
        assert os.path.abspath(str(exports)) not in text


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


def test_share_bundle_does_not_create_untrusted_nested_parent(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(FileNotFoundError):
            share_bundle.build_share_bundle(
                exports / "new" / "share.zip", Reconstruction(), exports
            )
    assert not (exports / "new").exists()


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
    artifact = exports / "mesh.glb"
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
    artifact = exports / r"..\escape.glb"
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
    link = exports / "linked.glb"
    link.symlink_to(target)
    rec = Reconstruction(mesh_glb_path=str(link))
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(ValueError, match="symlink artifact"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFO only")
def test_share_bundle_fifo_fails_without_blocking(tmp_path):
    """A FIFO in an artifact field must fail rather than block waiting for a writer."""
    import subprocess
    import sys

    exports = tmp_path / "exports"
    exports.mkdir()
    fifo = exports / "mesh.glb"
    os.mkfifo(fifo)
    script = (
        "from backend.services.share_bundle import build_share_bundle; "
        "from backend.db.models import Reconstruction; "
        "import pathlib; "
        f"build_share_bundle(pathlib.Path({str(exports / 'share.zip')!r}), "
        f"Reconstruction(mesh_glb_path={str(fifo)!r}), pathlib.Path({str(exports)!r}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], timeout=3, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "non-file artifact" in result.stderr
    assert not (exports / "share.zip").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor confinement")
def test_share_bundle_rejects_untrusted_artifact_parent_symlink(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "mesh.glb").write_bytes(b"private")
    (exports / "linked").symlink_to(outside, target_is_directory=True)
    rec = Reconstruction(mesh_glb_path=str(exports / "linked" / "mesh.glb"))
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(ValueError, match="artifact"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor confinement")
def test_share_bundle_rejects_parent_swapped_during_artifact_open(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    parent = exports / "nested"
    parent.mkdir(parents=True)
    (parent / "mesh.glb").write_bytes(b"public")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "mesh.glb").write_bytes(b"private")
    rec = Reconstruction(mesh_glb_path=str(parent / "mesh.glb"))
    original_open = share_bundle.os.open

    def swap_before_open(path, *args, **kwargs):
        if path == "nested":
            parent.rename(exports / "parked")
            parent.symlink_to(outside, target_is_directory=True)
        return original_open(path, *args, **kwargs)

    with (
        patch.object(share_bundle, "build_tileset", return_value={}),
        patch.object(share_bundle.os, "open", side_effect=swap_before_open),
    ):
        with pytest.raises((ValueError, OSError)):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()


def test_share_bundle_uses_configured_processed_and_colmap_roots(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    data = tmp_path / "data"
    colmap = data / "colmap" / "42"
    colmap.mkdir(parents=True)
    (processed / "mesh.glb").write_bytes(b"mesh")
    (colmap / "cloud.las").write_bytes(b"cloud")
    cfg = type("Cfg", (), {"processed_dir": str(processed), "data_dir": str(data)})()
    rec = Reconstruction(
        id=42,
        colmap_dir=str(colmap),
        mesh_glb_path=str(processed / "mesh.glb"),
        pointcloud_path=str(colmap / "cloud.las"),
    )
    with (
        patch.object(share_bundle, "get_config", return_value=cfg),
        patch.object(share_bundle, "build_tileset", return_value={}),
    ):
        share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    with zipfile.ZipFile(exports / "share.zip") as zf:
        assert zf.read("artifacts/mesh.glb") == b"mesh"
        assert zf.read("artifacts/cloud.las") == b"cloud"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor confinement")
def test_share_bundle_rejects_exports_root_swapped_after_validation(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    def swap_root(rec):
        exports.rename(tmp_path / "parked")
        exports.symlink_to(outside, target_is_directory=True)
        return {"artifacts": {}}

    with (
        patch.object(share_bundle, "build_share_manifest", side_effect=swap_root),
        patch.object(share_bundle, "build_tileset", return_value={}),
    ):
        with pytest.raises((OSError, ValueError)):
            share_bundle.build_share_bundle(exports / "share.zip", Reconstruction(), exports)
    assert not list(outside.iterdir())


def test_share_bundle_rejects_other_reconstruction_colmap_root(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    data = tmp_path / "data"
    other = data / "colmap" / "43"
    other.mkdir(parents=True)
    (other / "cloud.las").write_bytes(b"private")
    cfg = type("Cfg", (), {"processed_dir": str(processed), "data_dir": str(data)})()
    rec = Reconstruction(id=42, colmap_dir=str(other), pointcloud_path=str(other / "cloud.las"))
    with (
        patch.object(share_bundle, "get_config", return_value=cfg),
        patch.object(share_bundle, "build_tileset", return_value={}),
    ):
        with pytest.raises(ValueError, match="outside authorized artifact roots"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor confinement")
def test_share_bundle_artifact_read_uses_open_parent_after_swap(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    parent = exports / "nested"
    parent.mkdir(parents=True)
    (parent / "mesh.glb").write_bytes(b"public")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "mesh.glb").write_bytes(b"private")
    rec = Reconstruction(mesh_glb_path=str(parent / "mesh.glb"))
    original_open = share_bundle.os.open

    def swap_after_parent_open(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        if path == "nested":
            parent.rename(exports / "parked")
            parent.symlink_to(outside, target_is_directory=True)
        return fd

    with (
        patch.object(share_bundle, "build_tileset", return_value={}),
        patch.object(share_bundle.os, "open", side_effect=swap_after_parent_open),
    ):
        share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    with zipfile.ZipFile(exports / "share.zip") as zf:
        assert zf.read("artifacts/mesh.glb") == b"public"


def test_share_bundle_rejects_artifact_outside_configured_roots(tmp_path):
    from backend.services import share_bundle

    exports = tmp_path / "exports"
    exports.mkdir()
    private = tmp_path / "secret.glb"
    private.write_bytes(b"private")
    rec = Reconstruction(mesh_glb_path=str(private), colmap_dir=str(tmp_path))
    with patch.object(share_bundle, "build_tileset", return_value={}):
        with pytest.raises(ValueError, match="outside authorized artifact roots"):
            share_bundle.build_share_bundle(exports / "share.zip", rec, exports)
    assert not (exports / "share.zip").exists()
