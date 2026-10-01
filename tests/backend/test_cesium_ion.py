from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

import httpx
import pytest

import backend.routers.export as export_router
from backend.core.config import get_cesium_ion_config
from backend.db.models import Image, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.cesium_ion import CesiumIonError, upload_tileset

# The share bundle's tileset is placed with the solved transform; one near the
# fixture image (2E 1N, UTM 31N).
_GEO_TRANSFORM = json.dumps({
    "scale": 1.5,
    "rotation": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    "translation": [4.0, 2.0, 10.0],
    "utm_zone": "31N",
    "utm_origin": [388736.0, 110547.0],
})


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
    rec = Reconstruction(
        session_id=session.id, status="complete", frames_used=1, geo_transform=_GEO_TRANSFORM
    )
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
    rec = Reconstruction(
        session_id=session.id, status="complete", frames_used=1, geo_transform=_GEO_TRANSFORM
    )
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


def test_cesium_route_refuses_reconstruction_without_geo_transform(
    client, tmp_path, monkeypatch
):
    """A NULL geo_transform must not be published as a placed tileset (#950)."""
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
    with patch("backend.services.cesium_ion.upload_tileset") as upload:
        response = client.post(f"/export/reconstructions/{rec.id}/cesium-ion")

    assert response.status_code == 422
    assert "not georeferenced" in response.json()["detail"]
    upload.assert_not_called()


@pytest.mark.parametrize(
    "completion_url",
    [
        "https://attacker.example/v1/assets/81/uploadComplete",
        "https://api.cesium.test.attacker.example/v1/assets/81/uploadComplete",
        "https://api.cesium.test@attacker.example/v1/assets/81/uploadComplete",
        "https://user@api.cesium.test/v1/assets/81/uploadComplete",
        "https://api.cesium.test:8443/v1/assets/81/uploadComplete",
        "http://api.cesium.test/v1/assets/81/uploadComplete",
        "/v1/assets/81/uploadComplete",
    ],
)
def test_completion_url_off_the_ion_api_origin_never_receives_the_token(
    tmp_path, monkeypatch, completion_url
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
            "onComplete": {"method": "POST", "url": completion_url, "fields": {}},
        },
        request=httpx.Request("POST", "https://api.cesium.test/v1/assets"),
    )
    sent = []

    def _record(method, url, **kwargs):
        sent.append((method, url, kwargs.get("headers", {})))
        if method == "PUT":
            return httpx.Response(200, request=httpx.Request("PUT", url))
        if url == completion_url:
            return httpx.Response(204, request=httpx.Request("POST", "https://x.test"))
        return created

    with patch("backend.services.cesium_ion.httpx.request", side_effect=_record):
        with pytest.raises(CesiumIonError, match="completion URL"):
            upload_tileset(_config(), "tiles.zip", _bundle(tmp_path), "Mission")

    assert all(url != completion_url for _, url, _ in sent)
    token_urls = [url for _, url, headers in sent if "ion-secret" in str(headers)]
    assert token_urls == ["https://api.cesium.test/v1/assets"]
    # Nothing is uploaded for an asset that could not be completed.
    assert all(method != "PUT" for method, _, _ in sent)


def test_completion_url_on_the_configured_api_origin_is_accepted(tmp_path, monkeypatch):
    """Host comparison ignores case and an explicit default port."""
    monkeypatch.setenv("CESIUM_ION_TEST_TOKEN", "ion-secret")
    completion_url = "https://API.cesium.test:443/v1/assets/81/uploadComplete"
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
            "onComplete": {"method": "POST", "url": completion_url, "fields": {}},
        },
        request=httpx.Request("POST", "https://api.cesium.test/v1/assets"),
    )

    def _respond(method, url, **kwargs):
        if method == "PUT":
            return httpx.Response(200, request=httpx.Request("PUT", url))
        if url == completion_url:
            return httpx.Response(204, request=httpx.Request("POST", url))
        return created

    with patch("backend.services.cesium_ion.httpx.request", side_effect=_respond):
        result = upload_tileset(_config(), "tiles.zip", _bundle(tmp_path), "Mission")
    assert result == {"asset_id": 81, "status": "AWAITING_FILES"}
