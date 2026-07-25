from __future__ import annotations

import os

from backend.core.config import get_config, get_deployment_config
from backend.main import app, processed_dir


def test_processed_dir_resolves_via_config():
    assert processed_dir == os.path.abspath(get_config().processed_dir)


def test_cors_uses_deployment_profile():
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs["allow_origins"] == get_deployment_config()["cors_origins"]


# ---------------------------------------------------------------------------
# Host header pinning (DNS rebinding)
# ---------------------------------------------------------------------------


def test_health_allows_loopback_host(client):
    resp = client.get("/health", headers={"Host": "127.0.0.1:8000"})
    assert resp.status_code == 200


def test_rejects_unknown_host_header(client):
    """CORS does not stop DNS rebinding: an attacker page on a domain that re-resolves
    to 127.0.0.1 is same-origin with the loopback API, and every route is
    unauthenticated by default. Browsers cannot set Host, so pinning it closes that.
    """
    resp = client.get("/health", headers={"Host": "evil.test"})
    assert resp.status_code == 400


def test_rejects_unknown_host_on_a_data_route(client):
    # /settings leaks the absolute imports_dir, which is step one of the upload →
    # restore → download chain. It must be unreachable from a rebound origin too.
    resp = client.get("/settings", headers={"Host": "attacker.example"})
    assert resp.status_code == 400
