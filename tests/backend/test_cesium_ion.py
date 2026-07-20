from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest

import backend.routers.export as export_router
from backend.core.config import get_cesium_ion_config
from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.cesium_ion import CesiumIonError, _directory_prefix, upload_tileset


def _config(**overrides):
    return {
        "enabled": True,
        "api_url": "https://api.cesium.test/v1",
        "token_env": "CESIUM_ION_TEST_TOKEN",
        "timeout_seconds": 5,
        "allow_insecure_http": False,
        **overrides,
    }


def test_cesium_config_is_disabled_and_secret_free_by_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("cesium_ion:\n  enabled: true\n")

    config = get_cesium_ion_config(str(path))

    assert config["enabled"] is True
    assert config["token_env"] == "CESIUM_ION_TOKEN"
    assert "token" not in {key for key in config if key != "token_env"}


def test_upload_uses_ion_create_s3_put_and_completion_without_exposing_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "ion-secret")
    exports_dir = tmp_path / "exports"
    bundle = exports_dir / "tiles.zip"
    monkeypatch.setattr(
        "backend.services.cesium_ion.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )
    bundle.parent.mkdir()
    bundle.write_bytes(b"zip")
    created = httpx.Response(
        201,
        json={
            "assetMetadata": {"id": 81, "status": "AWAITING_FILES"},
            "uploadLocation": {
                "bucket": "assets.cesium.test",
                "prefix": "sources/81/",
                "endpoint": "https://assets.cesium.test",
                "accessKey": "temporary-access",
                "secretAccessKey": "temporary-secret",
                "sessionToken": "temporary-session",
            },
            "onComplete": {
                "method": "POST",
                "url": "https://api.cesium.test/v1/assets/81/uploadComplete",
                "fields": {},
            },
        },
        request=httpx.Request("POST", "https://api.cesium.test/v1/assets"),
    )
    uploaded = httpx.Response(
        200, request=httpx.Request("PUT", "https://assets.cesium.test/sources/81/tiles.zip")
    )
    completed = httpx.Response(
        204, request=httpx.Request("POST", "https://api.cesium.test/v1/assets/81/uploadComplete")
    )

    with patch(
        "backend.services.cesium_ion.httpx.request", side_effect=[created, uploaded, completed]
    ) as request:
        result = upload_tileset(_config(), bundle, "Mission")

    assert result == {"asset_id": 81, "status": "AWAITING_FILES"}
    create, storage, complete = request.call_args_list
    assert create.args == ("POST", "https://api.cesium.test/v1/assets")
    assert create.kwargs["json"] == {
        "name": "Mission",
        "type": "3DTILES",
        "options": {"sourceType": "3DTILES"},
    }
    assert create.kwargs["headers"] == {"Authorization": "Bearer ion-secret"}
    assert storage.args == ("PUT", "https://assets.cesium.test/sources/81/tiles.zip")
    assert storage.kwargs["content"] == b"zip"
    assert "temporary-secret" not in str(storage.kwargs)
    assert complete.args == ("POST", "https://api.cesium.test/v1/assets/81/uploadComplete")
    assert complete.kwargs["headers"] == {"Authorization": "Bearer ion-secret"}


def test_cesium_client_rejects_disabled_missing_token_and_unsafe_url(tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    bundle = exports_dir / "tiles.zip"
    monkeypatch.setattr(
        "backend.services.cesium_ion.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )
    bundle.parent.mkdir()
    bundle.write_bytes(b"zip")
    with pytest.raises(CesiumIonError, match="disabled"):
        upload_tileset(_config(enabled=False), bundle, "Mission")
    with pytest.raises(CesiumIonError, match="missing"):
        upload_tileset(_config(), bundle, "Mission")
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "secret")
    with pytest.raises(CesiumIonError, match="HTTPS"):
        upload_tileset(_config(api_url="http://cesium.test/v1"), bundle, "Mission")


def test_cesium_client_rejects_bundle_outside_exports(tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "secret")
    monkeypatch.setattr(
        "backend.services.cesium_ion.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )

    for bundle in (
        exports_dir / ".." / "outside" / "tiles.zip",
        tmp_path / "exports-other" / "tiles.zip",
    ):
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_bytes(b"zip")
        with patch("builtins.open") as bundle_open:
            with pytest.raises(CesiumIonError, match="inside the exports directory"):
                upload_tileset(_config(), bundle, "Mission")
        bundle_open.assert_not_called()


def test_cesium_path_check_preserves_filesystem_root():
    root = os.path.normcase(os.path.abspath(os.sep))

    assert _directory_prefix(root) == root
    assert os.path.normcase(os.path.join(root, "exports")).startswith(_directory_prefix(root))


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def test_cesium_route_builds_existing_bundle_and_returns_only_asset_status(
    client, tmp_path, monkeypatch
):
    db = _db(client)
    session = SessionModel(name="Mission", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.add(
        Image(
            session_id=session.id,
            filename="a.jpg",
            filepath=str(tmp_path / "a.jpg"),
            latitude=1,
            longitude=2,
        )
    )
    rec = Reconstruction(session_id=session.id, status="complete", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    monkeypatch.setattr(export_router, "get_cesium_ion_config", _config)
    with patch(
        "backend.services.cesium_ion.upload_tileset",
        return_value={"asset_id": 81, "status": "AWAITING_FILES"},
    ) as upload:
        response = client.post(f"/export/reconstructions/{rec.id}/cesium-ion")

    assert response.status_code == 200
    assert response.json() == {"asset_id": 81, "status": "AWAITING_FILES"}
    assert upload.call_args.args[1].name == f"reconstruction_{rec.id}_share.zip"


def test_cesium_route_returns_actionable_safe_error(client, tmp_path, monkeypatch):
    db = _db(client)
    session = SessionModel(name="Mission", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.add(
        Image(
            session_id=session.id,
            filename="a.jpg",
            filepath=str(tmp_path / "a.jpg"),
            latitude=1,
            longitude=2,
        )
    )
    rec = Reconstruction(session_id=session.id, status="complete", frames_used=1)
    db.add(rec)
    db.commit()
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    monkeypatch.setattr(export_router, "get_cesium_ion_config", _config)
    with patch(
        "backend.services.cesium_ion.upload_tileset",
        side_effect=CesiumIonError(
            "Cesium ion token is missing from environment variable CESIUM_ION_TOKEN"
        ),
    ):
        response = client.post(f"/export/reconstructions/{rec.id}/cesium-ion")

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Cesium ion token is missing from environment variable CESIUM_ION_TOKEN"
    )
