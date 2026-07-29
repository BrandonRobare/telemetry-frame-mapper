from __future__ import annotations

from pathlib import Path


def _make_target_area(client, name="Plan Area"):
    body = {
        "name": name,
        "geom_geojson": (
            '{"type":"Polygon","coordinates":[[[-80.5,35.0],[-80.4,35.0],'
            '[-80.4,35.1],[-80.5,35.1],[-80.5,35.0]]]}'
        ),
    }
    resp = client.post("/target-areas", json=body)
    assert resp.status_code == 200
    return resp.json()


def test_generate_plan(client):
    area = _make_target_area(client)
    body = {
        "target_area_id": area["id"],
        "altitude_ft": 200,
        "side_overlap_pct": 0.7,
        "forward_overlap_pct": 0.8,
    }
    resp = client.post("/plans/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["lane_count"] > 0
    assert "kml_path" in data
    assert "id" in data


def test_generate_plan_missing_area(client):
    body = {
        "target_area_id": 999999,
        "altitude_ft": 200,
        "side_overlap_pct": 0.7,
        "forward_overlap_pct": 0.8,
    }
    resp = client.post("/plans/generate", json=body)
    assert resp.status_code == 404


def test_download_kml_not_found(client):
    resp = client.get("/plans/999999/kml")
    assert resp.status_code == 404


def test_download_kml(client):
    area = _make_target_area(client, name="KML Area")
    body = {
        "target_area_id": area["id"],
        "altitude_ft": 150,
        "side_overlap_pct": 0.65,
        "forward_overlap_pct": 0.75,
    }
    plan = client.post("/plans/generate", json=body).json()
    resp = client.get(f"/plans/{plan['id']}/kml")
    assert resp.status_code == 200
    assert "kml" in resp.headers["content-type"]
    assert b"<kml" in resp.content


def test_download_gpx_not_found(client):
    resp = client.get("/plans/999999/gpx")
    assert resp.status_code == 404


def test_download_gpx(client):
    area = _make_target_area(client, name="GPX Area")
    body = {
        "target_area_id": area["id"],
        "altitude_ft": 100,
        "side_overlap_pct": 0.6,
        "forward_overlap_pct": 0.7,
    }
    plan = client.post("/plans/generate", json=body).json()
    resp = client.get(f"/plans/{plan['id']}/gpx")
    assert resp.status_code == 200
    assert "gpx" in resp.headers["content-type"]
    assert b"<gpx" in resp.content


def test_generate_plan_invalid_overlap(client):
    area = _make_target_area(client, name="Invalid Overlap")
    body = {
        "target_area_id": area["id"],
        "altitude_ft": 200,
        "side_overlap_pct": 1.0,  # invalid — must be < 1.0
        "forward_overlap_pct": 0.8,
    }
    resp = client.post("/plans/generate", json=body)
    assert resp.status_code == 422


def test_generate_plan_invalid_forward_overlap(client):
    area = _make_target_area(client, name="Invalid Forward Overlap")
    body = {
        "target_area_id": area["id"],
        "altitude_ft": 200,
        "side_overlap_pct": 0.7,
        "forward_overlap_pct": 1.0,
    }
    resp = client.post("/plans/generate", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_plan_ok(client):
    area = _make_target_area(client, name="Validate Plan Area")
    plan = client.post(
        "/plans/generate",
        json={
            "target_area_id": area["id"],
            "altitude_ft": 200,
            "side_overlap_pct": 0.7,
            "forward_overlap_pct": 0.8,
        },
    ).json()

    resp = client.post(f"/plans/{plan['id']}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"] == plan["id"]
    assert data["valid"] is True
    assert isinstance(data["warnings"], list)
    assert data["violations"] == []
    assert isinstance(data["info"], list)


def test_validate_plan_reports_terrain_unavailable_without_dem(client):
    """No DEM is configured in the test environment, so the RTH/terrain checks
    degrade to an informational message rather than a warning or violation."""
    area = _make_target_area(client, name="Terrain Info Area")
    plan = client.post(
        "/plans/generate",
        json={
            "target_area_id": area["id"],
            "altitude_ft": 200,
            "side_overlap_pct": 0.7,
            "forward_overlap_pct": 0.8,
        },
    ).json()

    resp = client.post(f"/plans/{plan['id']}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert any("Terrain data unavailable" in msg for msg in data["info"])


def test_validate_plan_not_found(client):
    resp = client.post("/plans/999999/validate")
    assert resp.status_code == 404


def test_validate_plan_no_lanes(client):
    """A plan without lanes_geojson should return 422."""
    # Use the /target-areas create directly, then insert a plan without lanes via
    # the generate endpoint (which always sets lanes). Instead we test the 404 path
    # and verify the existing generate case above covers the positive path.
    # The no-lanes edge case is covered in the unit tests.
    pass  # covered by unit tests in test_mission_planner_ext.py


# ---------------------------------------------------------------------------
# Battery estimate in plan response
# ---------------------------------------------------------------------------


def test_plan_includes_battery_estimate(client):
    area = _make_target_area(client, name="Battery Area")
    plan = client.post(
        "/plans/generate",
        json={
            "target_area_id": area["id"],
            "altitude_ft": 200,
            "side_overlap_pct": 0.7,
            "forward_overlap_pct": 0.8,
        },
    ).json()
    assert "batteries_estimated" in plan
    assert plan["batteries_estimated"] is not None
    assert plan["batteries_estimated"] > 0


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


def test_get_segments(client):
    area = _make_target_area(client, name="Segment Area")
    plan = client.post(
        "/plans/generate",
        json={
            "target_area_id": area["id"],
            "altitude_ft": 200,
            "side_overlap_pct": 0.7,
            "forward_overlap_pct": 0.8,
        },
    ).json()

    resp = client.get(f"/plans/{plan['id']}/segments")
    assert resp.status_code == 200
    segments = resp.json()
    assert isinstance(segments, list)
    assert len(segments) > 0
    for seg in segments:
        assert "index" in seg
        assert "from_lane" in seg
        assert "to_lane" in seg
        assert "distance_m" in seg
        assert "kml_path" in seg
        assert "gpx_path" in seg


def test_get_segments_not_found(client):
    resp = client.get("/plans/999999/segments")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Gap re-fly
# ---------------------------------------------------------------------------


def test_generate_from_gaps_no_coverage_run(client):
    resp = client.post(
        "/plans/generate-from-gaps",
        json={
            "coverage_run_id": 999999,
            "altitude_ft": 200,
            "side_overlap_pct": 0.7,
            "forward_overlap_pct": 0.8,
        },
    )
    assert resp.status_code == 404


def test_plan_exports_land_in_the_configured_exports_dir(client, tmp_path, monkeypatch):
    """Plan KML/GPX must honour exports_dir, not a package-relative constant.

    They were written to backend/exports/, outside the configured directory, so
    /storage/summary never counted them, the disk-lifecycle policy never cleaned
    them, and artifact backup never copied them. #195 fixed exactly this for
    WebODM exports; the plans router was missed.
    """
    from backend.core.config import get_config
    from backend.routers import plans as plans_router

    configured = tmp_path / "configured_exports"
    cfg = get_config()
    monkeypatch.setattr(cfg, "exports_dir", str(configured), raising=False)

    resolved = plans_router._exports_dir()

    assert resolved == configured
    assert resolved.exists()
    package_relative = Path(plans_router.__file__).parent.parent / "exports"
    assert resolved != package_relative
