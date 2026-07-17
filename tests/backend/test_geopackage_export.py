from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from backend.db.models import (
    FlightLog,
    FlightLogPoint,
    Footprint,
    Image,
    Measurement,
    Reconstruction,
    SessionComparison,
)
from backend.db.models import Session as SessionModel

geopandas = pytest.importorskip("geopandas")


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def test_geopackage_export_writes_available_layers_in_target_crs(client, monkeypatch, tmp_path):
    import backend.routers.export as export_router

    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Config", (), {"exports_dir": str(exports_dir), "target_crs": "EPSG:32617"})(),
    )
    db = _db(client)
    session = SessionModel(name="GeoPackage", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    db.refresh(session)

    image = Image(
        session_id=session.id,
        filename="image.jpg",
        filepath=str(tmp_path / "image.jpg"),
        timestamp=datetime(2026, 7, 17, 12, 0),
        latitude=35.0,
        longitude=-80.0,
        altitude_m=100.0,
        gps_source="exif",
        usable=True,
    )
    db.add(image)
    db.flush()
    db.add(Footprint(
        image_id=image.id,
        geom_geojson=json.dumps({
            "type": "Polygon",
            "coordinates": [[[-80.001, 34.999], [-79.999, 34.999], [-79.999, 35.001],
                             [-80.001, 35.001], [-80.001, 34.999]]],
        }),
        ground_width_m=20.0,
        ground_height_m=20.0,
        heading_estimated=False,
        pitch_oblique=False,
    ))
    flight_log = FlightLog(session_id=session.id, filename="flight.csv", point_count=2)
    db.add(flight_log)
    db.flush()
    db.add_all([
        FlightLogPoint(flight_log_id=flight_log.id, latitude=35.0, longitude=-80.0),
        FlightLogPoint(flight_log_id=flight_log.id, latitude=35.001, longitude=-80.0),
    ])

    gaps_path = tmp_path / "coverage_gaps.json"
    gaps_path.write_text(json.dumps([{"x": 0.0, "y": 0.0, "z": 1.0, "size": 0.5, "level": "thin"}]))
    reconstruction = Reconstruction(
        session_id=session.id,
        status="complete",
        coverage_gaps_path=str(gaps_path),
        geo_transform=json.dumps({
            "scale": 1.0,
            "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "translation": [0, 0, 0],
            "utm_zone": "17N",
            "utm_origin": [500000, 4000000],
        }),
    )
    db.add(reconstruction)
    db.commit()
    db.refresh(reconstruction)
    db.add(Measurement(
        reconstruction_id=reconstruction.id,
        kind="point",
        points_json=json.dumps([{"lat": 35.0, "lon": -80.0, "alt": 100.0}]),
        value=100.0,
        unit="m",
        label="Marker",
    ))

    diff_path = tmp_path / "comparison.json"
    diff_path.write_text(json.dumps({
        "utm_zone": "17N",
        "new": [{"x": 500001.0, "y": 4000001.0, "z": 2.0, "size": 0.5}],
        "removed": [],
    }))
    comparison = SessionComparison(
        session_a_id=session.id,
        session_b_id=session.id,
        reconstruction_a_id=reconstruction.id,
        reconstruction_b_id=reconstruction.id,
        status="complete",
        diff_path=str(diff_path),
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    sidecar = exports_dir / str(reconstruction.id) / "dsm.tif"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"not embedded")

    response = client.get(
        f"/export/reconstructions/{reconstruction.id}/geopackage?comparison_id={comparison.id}"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geopackage+sqlite3")
    package_path = tmp_path / "mapped_products.gpkg"
    package_path.write_bytes(response.content)
    with sqlite3.connect(package_path) as connection:
        layers = {
            row[0] for row in connection.execute("SELECT table_name FROM gpkg_contents")
        }
        references = connection.execute(
            "SELECT product, path, embedded FROM raster_references"
        ).fetchall()
    assert layers == {
        "image_locations",
        "footprints",
        "flight_paths",
        "coverage_gaps",
        "measurements",
        "comparison_change_cells",
        "raster_references",
    }
    assert references == [("dsm", str(sidecar), 0)]
    assert str(geopandas.read_file(package_path, layer="image_locations").crs) == "EPSG:32617"
    assert len(geopandas.read_file(package_path, layer="comparison_change_cells")) == 1


def test_geopackage_export_skips_unavailable_layers(client, monkeypatch, tmp_path):
    import backend.routers.export as export_router

    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type(
            "Config", (), {"exports_dir": str(tmp_path / "exports"), "target_crs": "EPSG:32617"}
        )(),
    )
    db = _db(client)
    session = SessionModel(name="Images only", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    reconstruction = Reconstruction(session_id=session.id, status="complete")
    db.add(reconstruction)
    db.add(Image(
        session_id=session.id,
        filename="image.jpg",
        filepath=str(tmp_path / "image.jpg"),
        latitude=35.0,
        longitude=-80.0,
    ))
    db.commit()
    db.refresh(reconstruction)

    response = client.get(f"/export/reconstructions/{reconstruction.id}/geopackage")

    assert response.status_code == 200
    package_path = tmp_path / "images_only.gpkg"
    package_path.write_bytes(response.content)
    with sqlite3.connect(package_path) as connection:
        layers = [row[0] for row in connection.execute("SELECT table_name FROM gpkg_contents")]
    assert layers == ["image_locations"]
