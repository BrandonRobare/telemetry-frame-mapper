import zipfile

import backend.routers.export as export_router
from backend.db.models import Image
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


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
    assert "--gcp gcp_list.txt" in body["odm_options"]
    with zipfile.ZipFile(body["zip_path"]) as zf:
        names = set(zf.namelist())
    assert {
        "odm_georeferencing.csv",
        "odm_options_manifest.json",
        "gcp_list.txt",
        "images/frame_001.jpg",
    } <= names
