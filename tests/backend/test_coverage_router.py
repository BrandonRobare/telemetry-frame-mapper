from __future__ import annotations


def test_create_target_area(client):
    geojson = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    body = {"name": "Field A", "geom_geojson": geojson}
    resp = client.post("/target-areas", json=body)
    assert resp.status_code == 200
    assert resp.json()["id"] > 0


def test_list_target_areas(client):
    resp = client.get("/target-areas")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_target_area(client):
    geojson = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}'
    body = {"name": "ToDelete", "geom_geojson": geojson}
    area_id = client.post("/target-areas", json=body).json()["id"]
    assert client.delete(f"/target-areas/{area_id}").status_code == 200
    ids = [a["id"] for a in client.get("/target-areas").json()]
    assert area_id not in ids


def test_coverage_run_no_footprints(client):
    geojson = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    body = {"name": "Empty", "geom_geojson": geojson}
    area_id = client.post("/target-areas", json=body).json()["id"]
    from backend.db.database import get_db
    from backend.db.models import Session as SM
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    s = SM(name="empty", folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    resp = client.post(f"/coverage/run?session_id={s.id}&target_area_id={area_id}")
    assert resp.status_code == 200
    assert resp.json()["coverage_pct"] == 0.0


def test_coverage_results(client):
    resp = client.get("/coverage/results?session_id=999999")
    assert resp.status_code == 200  # returns null/empty, not 404


def test_delete_target_area_not_found(client):
    resp = client.delete("/target-areas/999999")
    assert resp.status_code == 404
