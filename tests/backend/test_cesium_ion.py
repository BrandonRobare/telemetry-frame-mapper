from __future__ import annotations

import hashlib
from unittest.mock import patch

import httpx
import pytest

import backend.routers.export as export_router
from backend.core.config import get_cesium_ion_config
from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.cesium_ion import CesiumIonError, upload_tileset


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


def _bundle(tmp_path, payload=b"zip"):
    path = tmp_path / "tiles.zip"
    path.write_bytes(payload)
    return path


def test_upload_uses_ion_create_s3_put_and_completion_without_exposing_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "ion-secret")
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
        result = upload_tileset(_config(), "tiles.zip", _bundle(tmp_path), "Mission")

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
    assert not isinstance(storage.kwargs["content"], bytes | bytearray | str)
    assert "temporary-secret" not in str(storage.kwargs)
    assert complete.args == ("POST", "https://api.cesium.test/v1/assets/81/uploadComplete")
    assert complete.kwargs["headers"] == {"Authorization": "Bearer ion-secret"}


def test_cesium_upload_signs_the_file_digest_and_streams_the_bundle_from_disk(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "ion-secret")
    payload = b"PK\x03\x04" + b"tile" * 4096
    bundle = _bundle(tmp_path, payload)
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
    sent = {}

    def _record(method, url, **kwargs):
        if method == "PUT":
            sent["headers"] = kwargs["headers"]
            sent["body"] = kwargs["content"].read()
            return httpx.Response(200, request=httpx.Request("PUT", url))
        if url.endswith("/uploadComplete"):
            return httpx.Response(204, request=httpx.Request("POST", url))
        return created

    with patch("backend.services.cesium_ion.httpx.request", side_effect=_record):
        upload_tileset(_config(), "tiles.zip", bundle, "Mission")

    assert sent["body"] == payload
    assert sent["headers"]["x-amz-content-sha256"] == hashlib.sha256(payload).hexdigest()
    assert "UNSIGNED-PAYLOAD" not in str(sent["headers"])


def test_cesium_client_rejects_disabled_missing_token_and_unsafe_url(tmp_path, monkeypatch):
    bundle = _bundle(tmp_path)
    with pytest.raises(CesiumIonError, match="disabled"):
        upload_tileset(_config(enabled=False), "tiles.zip", bundle, "Mission")
    with pytest.raises(CesiumIonError, match="missing"):
        upload_tileset(_config(), "tiles.zip", bundle, "Mission")
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "secret")
    with pytest.raises(CesiumIonError, match="HTTPS"):
        upload_tileset(_config(api_url="http://cesium.test/v1"), "tiles.zip", bundle, "Mission")


def test_cesium_client_rejects_unsafe_bundle_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "secret")

    with pytest.raises(CesiumIonError, match="must be a filename"):
        upload_tileset(_config(), "../tiles.zip", _bundle(tmp_path), "Mission")


def _db(client):
    from backend.main import app

    return app.state.test_db_session


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
    assert upload.call_args.args[1] == f"reconstruction_{rec.id}_share.zip"
    assert upload.call_args.args[2].read_bytes().startswith(b"PK")


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
