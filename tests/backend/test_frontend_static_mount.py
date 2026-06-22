from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

import backend.main as main_mod


def _mount_frontend(dist_dir):
    """Mirror the module's own mount logic against a patched path."""
    return main_mod.FrontendMount(
        "/",
        app=main_mod.SPAStaticFiles(directory=str(dist_dir), html=True),
        name="frontend-test",
    )


@pytest.fixture
def frontend_mount(tmp_path, monkeypatch):
    """Mount a throwaway built frontend at "/" for the duration of a test.

    Starlette matches mounts in registration order, so any real "/" mount
    that main.py registered at import time (e.g. because frontend/dist
    happens to exist in this checkout) would shadow a second one appended
    after it. Swap it out for the duration of the test and restore the
    original routes afterwards either way.
    """
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>built ui</body></html>")
    monkeypatch.setattr(main_mod, "frontend_dist", dist_dir)

    original_routes = list(main_mod.app.router.routes)
    main_mod.app.router.routes[:] = [
        route for route in original_routes if not (isinstance(route, Mount) and route.path == "")
    ]
    main_mod.app.router.routes.append(_mount_frontend(dist_dir))
    try:
        yield dist_dir
    finally:
        main_mod.app.router.routes[:] = original_routes


def test_serves_built_frontend_index_when_dist_exists(frontend_mount):
    """When frontend/dist/index.html exists, GET / returns it (SPA entry point)."""
    client = TestClient(main_mod.app)
    resp = client.get("/")

    assert resp.status_code == 200
    assert "built ui" in resp.text


def test_client_side_route_falls_back_to_index(frontend_mount):
    """Unmatched nested paths (client-side routes) serve index.html, not a 404."""
    client = TestClient(main_mod.app)
    resp = client.get("/some/react-route")

    assert resp.status_code == 200
    assert "built ui" in resp.text


def test_frontend_mount_does_not_shadow_api_routes(frontend_mount):
    """Non-GET requests to API routes must still reach the routers, not the
    static mount (regression check for the redirect-slash interaction)."""
    client = TestClient(main_mod.app)
    body = {
        "name": "Mount Shadow Check",
        "geom_geojson": (
            '{"type":"Polygon","coordinates":[[[-80.5,35.0],[-80.4,35.0],'
            '[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
        ),
    }
    resp = client.post("/target-areas", json=body)

    assert resp.status_code == 200


def test_app_still_works_when_frontend_dist_missing(tmp_path, monkeypatch):
    """When frontend/dist doesn't exist, the app starts fine and /health still works."""
    missing_dir = tmp_path / "does-not-exist"
    monkeypatch.setattr(main_mod, "frontend_dist", missing_dir)

    client = TestClient(main_mod.app)
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
