from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import backend.main as main
from backend.core.config import get_api_key_config, get_pin_lock_config
from backend.services import job_queue
from backend.services.share_links import hash_password


@pytest.fixture
def enabled_pin_lock(monkeypatch):
    monkeypatch.setattr(
        main,
        "pin_lock_config",
        {"enabled": True, "pin_hash_env": "TEST_PIN_HASH", "session_ttl": 60},
    )
    monkeypatch.setenv("TEST_PIN_HASH", hash_password("1234"))
    main.app.state.pin_lock_sessions.clear()
    main.app.state.unlock_attempts.clear()
    yield
    main.app.state.pin_lock_sessions.clear()
    main.app.state.unlock_attempts.clear()


@pytest.fixture
def enabled_api_key(enabled_pin_lock, monkeypatch):
    monkeypatch.setattr(
        main,
        "api_key_config",
        {"enabled": True, "key_hash_env": "TEST_API_KEY_HASH"},
    )
    monkeypatch.setenv("TEST_API_KEY_HASH", hash_password("automation-key"))
    yield


def test_pin_lock_disabled_leaves_routes_unlocked(client):
    assert client.get("/sessions").status_code != 401


def test_pin_lock_refuses_a_second_api_process(enabled_pin_lock, monkeypatch):
    monkeypatch.setattr(main, "configure_application_logging", lambda config: None)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(job_queue, "start_worker", lambda: False)

    async def open_lifespan():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="single API process"):
        asyncio.run(open_lifespan())


def test_pin_lock_rejects_missing_or_malformed_hash(tmp_path, monkeypatch):
    config = Path(tmp_path / "config.yaml")
    config.write_text("pin_lock:\n  enabled: true\n  pin_hash_env: TEST_PIN_HASH\n")
    monkeypatch.delenv("TEST_PIN_HASH", raising=False)
    with pytest.raises(ValueError, match="valid scrypt hash"):
        get_pin_lock_config(str(config))
    monkeypatch.setenv("TEST_PIN_HASH", "not-a-hash")
    with pytest.raises(ValueError, match="valid scrypt hash"):
        get_pin_lock_config(str(config))


@pytest.mark.parametrize("ttl", ["true", "59", "0", "not-a-number"])
def test_pin_lock_rejects_invalid_session_ttl(tmp_path, ttl):
    config = Path(tmp_path / "config.yaml")
    config.write_text(f"pin_lock:\n  session_ttl: {ttl}\n")
    with pytest.raises(ValueError, match="integer of at least 60"):
        get_pin_lock_config(str(config))


def test_pin_lock_rejects_then_unlocks_all_protected_routes(client, enabled_pin_lock):
    for path in ("/", "/sessions", "/processed/thumbnail.jpg", "/share/token/example"):
        assert client.get(path).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/pin-lock/status").json() == {"enabled": True}

    failed = client.post("/pin-lock/unlock", json={"pin": "wrong"})
    assert failed.status_code == 403
    assert "set-cookie" not in failed.headers

    unlocked = client.post("/pin-lock/unlock", json={"pin": "1234"})
    assert unlocked.status_code == 204
    cookie = unlocked.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie
    assert client.get("/sessions").status_code != 401


def test_api_key_requires_an_enabled_pin_lock(tmp_path, monkeypatch):
    config = Path(tmp_path / "config.yaml")
    config.write_text("api_key:\n  enabled: true\n  key_hash_env: TEST_API_KEY_HASH\n")
    monkeypatch.setenv("TEST_API_KEY_HASH", hash_password("automation-key"))
    with pytest.raises(ValueError, match="requires pin_lock.enabled"):
        get_api_key_config(str(config))


def test_api_key_rejects_missing_or_malformed_hash(tmp_path, monkeypatch):
    config = Path(tmp_path / "config.yaml")
    config.write_text(
        "pin_lock:\n  enabled: true\n  pin_hash_env: TEST_PIN_HASH\n"
        "api_key:\n  enabled: true\n  key_hash_env: TEST_API_KEY_HASH\n"
    )
    monkeypatch.setenv("TEST_PIN_HASH", hash_password("1234"))
    monkeypatch.delenv("TEST_API_KEY_HASH", raising=False)
    with pytest.raises(ValueError, match="valid scrypt hash"):
        get_api_key_config(str(config))
    monkeypatch.setenv("TEST_API_KEY_HASH", "not-a-hash")
    with pytest.raises(ValueError, match="valid scrypt hash"):
        get_api_key_config(str(config))


def test_api_key_allows_protected_routes_without_cookie(client, enabled_api_key):
    assert client.get("/sessions").status_code == 401
    assert client.get("/sessions", headers={"x-drone-mapping-key": "wrong"}).status_code == 401
    assert client.get(
        "/sessions", headers={"X-Drone-Mapping-Key": "automation-key"}
    ).status_code == 200
    assert client.get("/metrics").status_code == 200


def test_unlock_throttles_repeated_failures_then_resets(client, enabled_pin_lock):
    for _ in range(5):
        assert client.post("/pin-lock/unlock", json={"pin": "wrong"}).status_code == 403
    blocked = client.post("/pin-lock/unlock", json={"pin": "1234"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0

    # Expire the backoff window; a correct PIN then unlocks and clears the counter.
    for entry in main.app.state.unlock_attempts.values():
        entry[1] = 0
    unlocked = client.post("/pin-lock/unlock", json={"pin": "1234"})
    assert unlocked.status_code == 204
    assert main.app.state.unlock_attempts == {}


def test_pin_lock_cookie_is_secure_for_https_proxy(client, enabled_pin_lock):
    response = client.post(
        "/pin-lock/unlock", json={"pin": "1234"}, headers={"X-Forwarded-Proto": "https"}
    )
    assert response.status_code == 204
    assert "secure" in response.headers["set-cookie"].lower()


def test_pin_lock_expiry_and_restart_reject_sessions(client, enabled_pin_lock, monkeypatch):
    unlocked = client.post("/pin-lock/unlock", json={"pin": "1234"})
    token = unlocked.cookies[main.PIN_LOCK_COOKIE_NAME]
    digest = next(iter(main.app.state.pin_lock_sessions))
    main.app.state.pin_lock_sessions[digest] = 0
    assert client.get("/sessions").status_code == 401

    client.cookies.set(main.PIN_LOCK_COOKIE_NAME, token)
    main.app.state.pin_lock_sessions.clear()
    assert client.get("/sessions").status_code == 401
