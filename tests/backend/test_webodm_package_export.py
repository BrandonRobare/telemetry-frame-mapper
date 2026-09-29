from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.routers.export as export_router
from backend.db.models import Image
from backend.db.models import Session as SessionModel
from backend.services.webodm_package import WebodmPackageOptions, build_webodm_package


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def test_webodm_package_includes_images_and_manifest(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    img = tmp_path / "frame_001.jpg"
    img.write_bytes(b"jpg")
    db = _db(client)
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        Image(
            session_id=session.id,
            filename="frame_001.jpg",
            filepath=str(img),
            usable=True,
            latitude=1,
            longitude=2,
            altitude_m=3,
        )
    )
    db.commit()
    body = client.post(
        f"/export/webodm-package?session_id={session.id}&mode=gcp&include_gcp=true"
    ).json()
    # The package has no surveyed GCPs to ship, so it must not instruct the
    # operator to pass --gcp for the empty template (#629).
    assert "--gcp gcp_list.txt" not in body["odm_options"]
    # ...but the operator is told how to turn it on once they fill the template in,
    # or their control points would be silently ignored by ODM (#629).
    assert "--gcp gcp_list.txt" in body["gcp_note"]
    assert Path(body["zip_path"]).name == f"webodm_package_{session.id}_gcp.zip"
    with zipfile.ZipFile(body["zip_path"]) as zf:
        names = set(zf.namelist())
        gcp_list = zf.read("gcp_list.txt").decode()
    assert {
        "odm_georeferencing.csv",
        "odm_options_manifest.json",
        "gcp_list.txt",
        "images/frame_001.jpg",
    } <= names
    # ODM reads line 1 as the SRS header verbatim, so no leading "#".
    assert gcp_list == "EPSG:4326\n"


def test_webodm_georeferencing_csv_crash_mid_write_keeps_previous_zip(
    client, tmp_path, monkeypatch
):
    """The CSV-only ZIP is rebuilt in place too, so it needs the same guard (#641)."""
    exports = tmp_path / "exports"
    monkeypatch.setattr(
        export_router, "get_config", lambda: type("Cfg", (), {"exports_dir": str(exports)})()
    )
    db = _db(client)
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        Image(
            session_id=session.id, filename="a.jpg", filepath=str(tmp_path / "a.jpg"),
            usable=True, latitude=1, longitude=2, altitude_m=3,
        )
    )
    db.commit()

    zip_path = Path(
        client.post(f"/export/webodm-georeferencing-csv?session_id={session.id}").json()["zip_path"]
    )
    good = zip_path.read_bytes()

    with patch(
        "backend.routers.export.zipfile.ZipFile.writestr", side_effect=OSError("disk full")
    ):
        with pytest.raises(OSError, match="disk full"):
            client.post(f"/export/webodm-georeferencing-csv?session_id={session.id}")

    assert zip_path.read_bytes() == good
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.read("odm_georeferencing.csv").decode().startswith("filename,")
    assert not list(exports.glob("*.tmp"))


@pytest.mark.parametrize("filename", ["../escape.zip", "../exports-sibling/package.zip"])
def test_webodm_package_rejects_path_outside_exports(tmp_path, filename):
    exports = tmp_path / "exports"
    exports.mkdir()

    with pytest.raises(ValueError, match="inside exports directory"):
        build_webodm_package(
            exports / filename,
            [],
            WebodmPackageOptions(),
            exports_dir=exports,
        )


@pytest.mark.integration
@pytest.mark.area_export_share
@pytest.mark.parametrize("endpoint", ["webodm-georeferencing-csv", "webodm-package"])
def test_odm_georeferencing_csv_neutralizes_formula_filenames(
    client, tmp_path, monkeypatch, endpoint
):
    """A filename a spreadsheet would run as a formula reaches the CSV as inert text (#942)."""
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    evil = '=HYPERLINK("evil.example","x").jpg'
    src = tmp_path / evil
    src.write_bytes(b"jpg")
    db = _db(client)
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        Image(
            session_id=session.id, filename=evil, filepath=str(src),
            usable=True, latitude=-33.5, longitude=151.25, altitude_m=12.0,
        )
    )
    db.commit()

    body = client.post(f"/export/{endpoint}?session_id={session.id}").json()
    with zipfile.ZipFile(body["zip_path"]) as zf:
        text = zf.read("odm_georeferencing.csv").decode()

    # The name holds commas and quotes, so the cell is quoted and carries the ' guard...
    assert '"\'=HYPERLINK(""evil.example"",""x"").jpg"' in text
    # ...and reads back as one text cell, while the (negative) coordinates stay numbers.
    assert list(csv.reader(io.StringIO(text))) == [
        ["filename", "latitude", "longitude", "altitude"],
        ["'" + evil, "-33.5", "151.25", "12.0"],
    ]


@pytest.mark.unit
@pytest.mark.area_export_share
def test_webodm_package_csv_names_match_zip_members_one_to_one(tmp_path):
    """Every CSV row names an image the zip carries, and every zipped image has a row (#942)."""
    exports = tmp_path / "exports"
    flight = tmp_path / "flight"
    for folder, name in (
        ("a", "DJI_0001.JPG"),
        ("b", "DJI_0001.JPG"),
        ("c", "DJI_0003.JPG"),
        ("d", "DJI_0003.JPG"),
    ):
        (flight / folder).mkdir(parents=True)
        (flight / folder / name).write_bytes(folder.encode())

    def image(filename: str, path: Path) -> Image:
        return Image(
            filename=filename, filepath=str(path), latitude=1.0, longitude=2.0, altitude_m=3.0
        )

    images = [
        # One camera name in two folders of a single import: ingest stores each under
        # a unique filename, but the source basenames still collide.
        image("DJI_0001__aaaaaaaaaaaa.JPG", flight / "a" / "DJI_0001.JPG"),
        image("DJI_0001__bbbbbbbbbbbb.JPG", flight / "b" / "DJI_0001.JPG"),
        # One stored filename twice, e.g. two imports merged into one session.
        image("DJI_0003.JPG", flight / "c" / "DJI_0003.JPG"),
        image("DJI_0003.JPG", flight / "d" / "DJI_0003.JPG"),
        # The source file is gone, so the zip cannot carry it and the CSV must not list it.
        image("DJI_0004.JPG", flight / "missing" / "DJI_0004.JPG"),
    ]

    manifest = build_webodm_package(
        exports / "package.zip", images, WebodmPackageOptions(), exports_dir=exports
    )

    with zipfile.ZipFile(manifest["zip_path"]) as zf:
        members = zf.namelist()
        rows = list(csv.DictReader(io.StringIO(zf.read("odm_georeferencing.csv").decode())))
        csv_members = [f"images/{row['filename']}" for row in rows]
        assert len(members) == len(set(members)), members
        assert sorted(csv_members) == sorted(m for m in members if m.startswith("images/"))
        # Each row's name is the member holding that image, not a same-named neighbour.
        assert zf.read("images/DJI_0001__aaaaaaaaaaaa.JPG") == b"a"
        assert zf.read("images/DJI_0001__bbbbbbbbbbbb.JPG") == b"b"
        assert {zf.read("images/DJI_0003.JPG"), zf.read("images/DJI_0003__2.JPG")} == {
            b"c",
            b"d",
        }
    assert len(rows) == manifest["copied_image_count"] == 4
    assert manifest["image_count"] == 5
