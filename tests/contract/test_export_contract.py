"""Stable columns/property names from the actual public export producers."""

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.db.models import (
    Annotation,
    CoverageRun,
    Footprint,
    Image,
    Measurement,
    Reconstruction,
    TargetArea,
)
from backend.db.models import Session as SessionModel
from backend.main import app
from backend.services.georeferencing_workflows import ControlPoint, render_control_point_csv
from backend.services.reconstruction import diff_to_geojson
from backend.services.webodm_package import odm_georeferencing_csv, package_image_names

pytestmark = [pytest.mark.contract, pytest.mark.area_export_share]
SCHEMAS = json.loads((Path(__file__).parent / "fixtures/export_schemas.json").read_text())
POLYGON = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'


def test_csv_producers_keep_columns_and_no_header_variants():
    image = SimpleNamespace(id=1, filename="frame.jpg", latitude=1, longitude=2, altitude_m=3)
    rows = list(csv.reader(io.StringIO(odm_georeferencing_csv(package_image_names([image])))))
    assert rows[0] == SCHEMAS["csv"]["odm_georeferencing"]
    assert rows[1] == ["frame.jpg", "1", "2", "3"]
    point = ControlPoint(label="control", latitude=1, longitude=2, altitude_m=3)
    for variant, schema in SCHEMAS["csv"]["control_points"].items():
        rows = list(csv.reader(io.StringIO(render_control_point_csv([point], variant))))
        assert schema["header"] is False
        assert dict(zip(schema["columns"], rows[0], strict=True)) == {
            "label": "control",
            "latitude": "1.00000000",
            "longitude": "2.00000000",
            "altitude_m": "3.000",
        }
        assert len(rows) == 1


def test_geojson_producers_keep_property_keys_and_geometry_variants(client):
    db = app.state.test_db_session
    session = SessionModel(name="export contract", folder_path="/tmp/export-contract")
    db.add(session)
    db.flush()
    image = Image(session_id=session.id, filename="frame.jpg", filepath="/tmp/frame.jpg")
    rec = Reconstruction(session_id=session.id, preset="quick", status="complete", frames_used=1)
    db.add_all([image, rec])
    db.flush()
    db.add(Footprint(image_id=image.id, geom_geojson=POLYGON, heading_estimated=False))
    target = TargetArea(name="contract area", geom_geojson=POLYGON)
    db.add(target)
    db.flush()
    coverage = CoverageRun(
        target_area_id=target.id,
        session_ids=str(session.id),
        gap_geojson=POLYGON,
        overlap_geojson=POLYGON,
    )
    db.add(coverage)
    db.add(
        Annotation(
            reconstruction_id=rec.id,
            label="annotation",
            lat=1,
            lon=2,
            alt_m=3,
            color="#ffffff",
        )
    )
    for kind, coords in [
        ("point", [(0, 0)]),
        ("distance", [(0, 0), (1, 0)]),
        ("area", [(0, 0), (1, 0), (1, 1)]),
    ]:
        db.add(
            Measurement(
                reconstruction_id=rec.id,
                kind=kind,
                label=kind,
                value=1,
                unit="m",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                points_json=json.dumps([{"lat": lat, "lon": lon} for lon, lat in coords]),
            )
        )
    db.commit()
    endpoints = {
        "footprints": f"/footprints/export?session_id={session.id}",
        "annotations": f"/reconstruction/{rec.id}/annotations.geojson",
        "measurements": f"/export/reconstructions/{rec.id}/measurements.geojson",
    }
    for name, url in endpoints.items():
        response = client.get(url)
        assert response.status_code == 200, response.text
        features = response.json()["features"]
        assert features
        for feature in features:
            assert sorted(feature["properties"]) == SCHEMAS["geojson"][name]
        if name == "measurements":
            assert {f["geometry"]["type"] for f in features} == {"Point", "LineString", "Polygon"}
    response = client.get(f"/coverage/{coverage.id}/export")
    assert response.status_code == 200, response.text
    for feature in response.json()["features"]:
        kind = feature["properties"]["kind"]
        assert sorted(feature["properties"]) == SCHEMAS["geojson"][kind]
    response = client.get(f"/export/reconstructions/{rec.id}/measurements.csv")
    assert response.status_code == 200
    assert next(csv.reader(io.StringIO(response.text))) == SCHEMAS["csv"]["measurements"]


def test_comparison_geojson_keeps_collection_and_each_change_properties():
    diff = {
        "utm_zone": "17N",
        "summary": {},
        "comparison": {},
        "new": [{"x": 500000, "y": 3800000, "z": 5, "size": 1}],
        "removed": [{"x": 500001, "y": 3800000, "z": 5, "size": 1}],
    }
    result = diff_to_geojson(diff)
    assert sorted(result["properties"]) == SCHEMAS["geojson"]["comparison_collection"]
    for feature in result["features"]:
        assert (
            sorted(feature["properties"])
            == SCHEMAS["geojson"]["comparison_" + feature["properties"]["type"]]
        )
