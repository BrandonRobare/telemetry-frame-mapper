from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

import backend.routers.reconstruction as reconstruction_router
import backend.routers.webodm as webodm_router
from backend.core.config import get_webodm_config
from backend.db.models import Image
from backend.db.models import Session as SessionModel
from backend.services.webodm import (
    WebODMError,
    cancel_task,
    create_project,
    create_task,
    download_asset,
    get_task,
)


def _config(**overrides):
    return {
        "enabled": True,
        "url": "https://webodm.example.test",
        "jwt_env": "WEBODM_TEST_JWT",
        "timeout_seconds": 5,
        "allow_insecure_http": False,
        **overrides,
    }


def test_webodm_config_is_disabled_and_secret_free_by_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("webodm:\n  enabled: true\n  url: https://webodm.example.test\n")

    config = get_webodm_config(str(path))

    assert config["enabled"] is True
    assert config["jwt_env"] == "WEBODM_JWT"
    assert "jwt" not in config


def test_webodm_client_uses_documented_project_task_and_poll_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBODM_TEST_JWT", "test-secret")
    first, second = tmp_path / "one.jpg", tmp_path / "two.jpg"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    responses = [
        httpx.Response(201, json={"id": 17}, request=httpx.Request("POST", "https://webodm.example.test/api/projects/")),
        httpx.Response(201, json={"id": 23}, request=httpx.Request("POST", "https://webodm.example.test/api/projects/17/tasks/")),
        httpx.Response(200, json={"id": 23, "status": 20}, request=httpx.Request("GET", "https://webodm.example.test/api/projects/17/tasks/23/")),
    ]

    with patch("backend.services.webodm.httpx.request", side_effect=responses) as request:
        assert create_project(_config(), "Mission") == 17
        assert (
            create_task(
                _config(), 17, "Task", [first, second], [{"name": "fast-orthophoto", "value": True}]
            )
            == 23
        )
        assert get_task(_config(), 17, 23)["status"] == 20

    project, task, poll = request.call_args_list
    assert project.args == ("POST", "https://webodm.example.test/api/projects/")
    assert project.kwargs["headers"] == {"Authorization": "JWT test-secret"}
    assert project.kwargs["data"] == {"name": "Mission"}
    assert task.args == ("POST", "https://webodm.example.test/api/projects/17/tasks/")
    assert task.kwargs["data"] == {
        "name": "Task",
        "options": '[{"name": "fast-orthophoto", "value": true}]',
    }
    assert [part[0] for part in task.kwargs["files"]] == ["images", "images"]
    assert poll.args == ("GET", "https://webodm.example.test/api/projects/17/tasks/23/")


def test_webodm_download_uses_documented_asset_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBODM_TEST_JWT", "test-secret")
    response = httpx.Response(
        200,
        content=b"geotiff",
        request=httpx.Request("GET", "https://webodm.example.test/api/projects/17/tasks/23/download/orthophoto.tif"),
    )
    with patch("backend.services.webodm.httpx.request", return_value=response) as request:
        saved = download_asset(_config(), 17, 23, "orthophoto.tif", tmp_path / "exports")

    assert saved.read_bytes() == b"geotiff"
    assert request.call_args.args == ("GET", "https://webodm.example.test/api/projects/17/tasks/23/download/orthophoto.tif")


def test_webodm_download_rejects_traversal_asset(tmp_path):
    with pytest.raises(WebODMError, match="supported mapping filename"):
        download_asset(_config(), 17, 23, "../escape.tif", tmp_path / "exports")


def test_webodm_cancel_uses_documented_endpoint(monkeypatch):
    monkeypatch.setenv("WEBODM_TEST_JWT", "test-secret")
    response = httpx.Response(
        200,
        json={},
        request=httpx.Request("POST", "https://webodm.example.test/api/projects/17/tasks/23/cancel/"),
    )
    with patch("backend.services.webodm.httpx.request", return_value=response) as request:
        cancel_task(_config(), 17, 23)

    assert request.call_args.args == (
        "POST",
        "https://webodm.example.test/api/projects/17/tasks/23/cancel/",
    )


def test_webodm_client_rejects_disabled_missing_token_and_unsafe_url(monkeypatch):
    with pytest.raises(WebODMError, match="disabled"):
        create_project(_config(enabled=False), "Mission")
    with pytest.raises(WebODMError, match="missing"):
        create_project(_config(), "Mission")
    monkeypatch.setenv("WEBODM_TEST_JWT", "token")
    with pytest.raises(WebODMError, match="HTTPS"):
        create_project(_config(url="http://webodm.example.test"), "Mission")


def test_reconstruction_backends_make_webodm_opt_in_and_secret_free(client, monkeypatch):
    monkeypatch.setattr(reconstruction_router, "get_webodm_config", lambda: _config(enabled=False))
    unavailable = client.get("/reconstruction/backends").json()["backends"]
    assert unavailable[0]["id"] == "colmap"
    assert unavailable[0]["available"] is True
    assert unavailable[1] == {
        "id": "webodm",
        "available": False,
        "detail": "WebODM connection is unavailable; review configuration and server logs.",
    }

    monkeypatch.setenv("WEBODM_TEST_JWT", "test-secret")
    monkeypatch.setattr(reconstruction_router, "get_webodm_config", _config)
    available = client.get("/reconstruction/backends").json()["backends"]
    assert available[1]["id"] == "webodm"
    assert available[1]["available"] is True
    assert "test-secret" not in available[1]["detail"]


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def test_submit_session_task_and_status_are_explicit(client, tmp_path, monkeypatch):
    image_paths = []
    for filename in ("one.jpg", "two.jpg"):
        path = tmp_path / filename
        path.write_bytes(b"jpg")
        image_paths.append(path)
    db = _db(client)
    session = SessionModel(name="Mission", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.add_all(
        [
            Image(session_id=session.id, filename=path.name, filepath=str(path), usable=True)
            for path in image_paths
        ]
    )
    db.commit()
    monkeypatch.setattr(webodm_router, "get_webodm_config", _config)

    with (
        patch.object(webodm_router, "create_project", return_value=17),
        patch.object(webodm_router, "create_task", return_value=23),
    ):
        submitted = client.post(
            f"/webodm/sessions/{session.id}/tasks",
            json={"options": [{"name": "fast-orthophoto", "value": True}]},
        )
    assert submitted.status_code == 201
    assert submitted.json() == {"project_id": 17, "task_id": 23, "images_submitted": 2}

    with patch.object(
        webodm_router,
        "get_task",
        return_value={"status": 30, "last_error": "not enough images", "available_assets": []},
    ):
        status = client.get("/webodm/projects/17/tasks/23")
    assert status.json()["status_name"] == "failed"
    assert status.json()["error"] == "not enough images"


def test_reconstruction_start_can_submit_the_webodm_backend(client, tmp_path, monkeypatch):
    image_paths = []
    for filename in ("one.jpg", "two.jpg"):
        path = tmp_path / filename
        path.write_bytes(b"jpg")
        image_paths.append(path)
    db = _db(client)
    session = SessionModel(name="Mission", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.add_all(
        [
            Image(session_id=session.id, filename=path.name, filepath=str(path), usable=True)
            for path in image_paths
        ]
    )
    db.commit()
    monkeypatch.setattr(reconstruction_router, "get_webodm_config", _config)
    with (
        patch.object(reconstruction_router, "validate_connection_config"),
        patch.object(reconstruction_router, "create_project", return_value=17),
        patch.object(reconstruction_router, "create_task", return_value=23) as create,
    ):
        response = client.post(
            "/reconstruction/start",
            json={
                "session_id": session.id,
                "backend": "webodm",
                "webodm_options": [{"name": "fast-orthophoto", "value": True}],
            },
        )
    assert response.status_code == 201
    assert response.json() == {
        "backend": "webodm",
        "session_id": session.id,
        "project_id": 17,
        "task_id": 23,
        "images_submitted": 2,
        "status_url": "/webodm/projects/17/tasks/23",
        "results_url": "/webodm/projects/17/tasks/23/results",
    }
    assert create.call_args.args[-1] == [{"name": "fast-orthophoto", "value": True}]


def test_reconstruction_start_webodm_fails_clearly_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(reconstruction_router, "get_webodm_config", lambda: _config(enabled=False))
    response = client.post("/reconstruction/start", json={"session_id": 1, "backend": "webodm"})
    assert response.status_code == 422
    assert response.json()["detail"] == "WebODM integration is disabled in config.yaml"


def test_pull_results_requires_completed_task_and_saves_to_exports(client, tmp_path, monkeypatch):
    monkeypatch.setattr(webodm_router, "get_webodm_config", _config)
    config = type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})()
    monkeypatch.setattr(webodm_router, "get_config", lambda: config)
    with patch.object(webodm_router, "get_task", return_value={"status": 20}):
        assert client.post("/webodm/projects/17/tasks/23/results", json={}).status_code == 409
    output = tmp_path / "exports" / "downloaded" / "orthophoto.tif"
    with (
        patch.object(
            webodm_router,
            "get_task",
            return_value={"status": 40, "available_assets": ["orthophoto.tif"]},
        ),
        patch.object(webodm_router, "download_asset", return_value=output) as download,
    ):
        response = client.post(
            "/webodm/projects/17/tasks/23/results", json={"assets": ["orthophoto.tif"]}
        )
    assert response.status_code == 200
    assert response.json()["saved_assets"] == [str(output)]
    download_dir = download.call_args.args[-1]
    assert download_dir.parent == tmp_path / "exports" / "webodm"
    assert download_dir.name.startswith("results-")
