import zipfile
from pathlib import Path

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
