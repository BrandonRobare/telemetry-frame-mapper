from __future__ import annotations

import io
import json
import zipfile

from backend.services.coverage import run_coverage

_POLYGON = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'


def _make_session_with_footprint():
    from backend.db.models import Footprint, Image
    from backend.db.models import Session as SM
    from backend.main import app

    db = app.state.test_db_session
    session = SM(name="exportable", folder_path="/tmp", photo_count=1, usable_count=1)
    db.add(session)
    db.commit()
    db.refresh(session)

    image = Image(session_id=session.id, filename="frame_001.jpg", filepath="/tmp/frame_001.jpg")
    db.add(image)
    db.commit()
    db.refresh(image)

    footprint = Footprint(
        image_id=image.id,
        geom_geojson=_POLYGON,
        ground_width_m=12.5,
        ground_height_m=9.5,
        heading_estimated=False,
    )
    db.add(footprint)
    db.commit()
    return session.id


def _make_coverage_run(session_id: int):
    from backend.db.models import CoverageRun, TargetArea
    from backend.main import app

    db = app.state.test_db_session
    target = TargetArea(name="field", geom_geojson=_POLYGON)
    db.add(target)
    db.commit()
    db.refresh(target)

    run = CoverageRun(
        target_area_id=target.id,
        session_ids=str(session_id),
        covered_area_m2=100.0,
        coverage_pct=75.0,
        gap_geojson=_POLYGON,
        overlap_geojson=(
            '{"type":"Polygon","coordinates":[[[0.1,0.1],[0.2,0.1],'
            '[0.2,0.2],[0.1,0.2],[0.1,0.1]]]}'
        ),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


def test_create_target_area(client):
    body = {"name": "Field A", "geom_geojson": _POLYGON}
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
    body = {"name": "Empty", "geom_geojson": _POLYGON}
    area_id = client.post("/target-areas", json=body).json()["id"]
    from backend.db.models import Session as SM
    from backend.main import app
    db = app.state.test_db_session
    s = SM(name="empty", folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    resp = client.post(f"/coverage/run?session_id={s.id}&target_area_id={area_id}")
    assert resp.status_code == 200
    assert resp.json()["coverage_pct"] == 0.0


def test_run_coverage_returns_gap_for_partial_footprint():
    target = {
        "type": "Polygon",
        "coordinates": [[
            [-81.0, 41.0],
            [-80.99, 41.0],
            [-80.99, 41.01],
            [-81.0, 41.01],
            [-81.0, 41.0],
        ]],
    }
    footprint = {
        "type": "Polygon",
        "coordinates": [[
            [-81.0, 41.0],
            [-80.995, 41.0],
            [-80.995, 41.01],
            [-81.0, 41.01],
            [-81.0, 41.0],
        ]],
    }

    result = run_coverage([json.dumps(footprint)], json.dumps(target))

    assert 45.0 < result["coverage_pct"] < 55.0
    assert result["covered_area_m2"] > 0
    assert result["gap_geojson"] is not None
    assert json.loads(result["gap_geojson"])["type"] == "Polygon"


def test_coverage_results(client):
    resp = client.get("/coverage/results?session_id=999999")
    assert resp.status_code == 200  # returns null/empty, not 404


def test_delete_target_area_not_found(client):
    resp = client.delete("/target-areas/999999")
    assert resp.status_code == 404


def test_export_footprints_geojson(client):
    session_id = _make_session_with_footprint()
    resp = client.get(f"/footprints/export?session_id={session_id}&format=geojson")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/geo+json")
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["filename"] == "frame_001.jpg"


def test_export_footprints_kmz(client):
    session_id = _make_session_with_footprint()
    resp = client.get(f"/footprints/export?session_id={session_id}&format=kmz")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.google-earth.kmz")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == [f"session_{session_id}_footprints.kml"]
        assert "frame_001.jpg" in archive.read(archive.namelist()[0]).decode()


def test_export_latest_coverage_geojson(client):
    session_id = _make_session_with_footprint()
    run_id = _make_coverage_run(session_id)
    resp = client.get(f"/coverage/results/export?session_id={session_id}&format=geojson")
    assert resp.status_code == 200
    body = resp.json()
    assert [feature["properties"]["kind"] for feature in body["features"]] == [
        "coverage_gap",
        "coverage_overlap",
    ]
    assert body["features"][0]["properties"]["coverage_run_id"] == run_id


def test_export_coverage_kml(client):
    session_id = _make_session_with_footprint()
    run_id = _make_coverage_run(session_id)
    resp = client.get(f"/coverage/{run_id}/export?format=kml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.google-earth.kml+xml")
    assert "coverage_gap" in resp.text
    assert "<Polygon>" in resp.text
