from __future__ import annotations


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
