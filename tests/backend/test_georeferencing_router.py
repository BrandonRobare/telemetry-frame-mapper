import pytest

from backend.db.models import Image
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def test_precision_workflow_detects_rtk_and_recommends_force_gps(client):
    db = _db(client)
    session = SessionModel(name="RTK", folder_path="/tmp/rtk")
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        Image(
            session_id=session.id,
            filename="a.jpg",
            filepath="/tmp/a.jpg",
            usable=True,
            latitude=1,
            longitude=2,
            gps_source="rtk",
        )
    )
    db.commit()

    body = client.get(f"/georeferencing/sessions/{session.id}/precision").json()

    assert body["workflow"] == "rtk"
    assert "--force-gps" in body["recommended_webodm_options"]


def test_build_gcp_list_returns_webodm_text(client):
    resp = client.post(
        "/georeferencing/gcp-list",
        json=[
            {
                "image_filename": "frame_001.jpg",
                "pixel_x": 10,
                "pixel_y": 20,
                "longitude": -81.5,
                "latitude": 41.2,
                "altitude_m": 300,
                "label": "north-pad",
            }
        ],
    )

    assert resp.status_code == 200
    header, row = resp.json()["contents"].splitlines()
    # ODM's GCPFile reads line 1 as the SRS header verbatim; a "#" breaks it.
    assert header == "EPSG:4326"
    assert row.split() == [
        "-81.50000000",
        "41.20000000",
        "300.000",
        "10.000",
        "20.000",
        "frame_001.jpg",
        "north-pad",
    ]


def test_build_gcp_list_keeps_seven_columns_without_altitude(client):
    resp = client.post(
        "/georeferencing/gcp-list",
        json=[
            {
                "image_filename": "IMG_0525.JPG",
                "pixel_x": 1024,
                "pixel_y": 768,
                "longitude": -81.0,
                "latitude": 28.0,
            }
        ],
    )

    assert resp.status_code == 200
    row = resp.json()["contents"].splitlines()[1]
    # A missing altitude must still leave seven columns, not shift them left.
    assert row.split() == [
        "-81.00000000",
        "28.00000000",
        "0.000",
        "1024.000",
        "768.000",
        "IMG_0525.JPG",
        "IMG_0525.JPG",
    ]


@pytest.mark.parametrize(
    "override",
    [{"image_filename": "DJI 0001.JPG"}, {"label": "north pad"}, {"image_filename": ""}],
)
def test_build_gcp_list_rejects_whitespace_in_filename_or_label(client, override):
    resp = client.post(
        "/georeferencing/gcp-list",
        json=[
            {
                "image_filename": "frame_001.jpg",
                "pixel_x": 10,
                "pixel_y": 20,
                "longitude": -81.5,
                "latitude": 41.2,
                **override,
            }
        ],
    )

    assert resp.status_code == 422


@pytest.mark.parametrize("format", ["pix4d", "dronedeploy"])
def test_control_point_csv_import_and_export_use_supported_wgs84_mapping(client, format):
    contents = "north-pad,41.20000000,-81.50000000,300.250\n"

    imported = client.post(
        "/georeferencing/control-points/import",
        json={"format": format, "contents": contents},
    )

    assert imported.status_code == 200
    assert imported.json()["points"] == [
        {"label": "north-pad", "latitude": 41.2, "longitude": -81.5, "altitude_m": 300.25}
    ]
    exported = client.post(
        "/georeferencing/control-points/export",
        json={"format": format, "points": imported.json()["points"]},
    )
    assert exported.status_code == 200
    assert exported.json()["contents"] == contents


def test_control_point_csv_rejects_headers_invalid_coordinates_and_unknown_format(client):
    header = client.post(
        "/georeferencing/control-points/import",
        json={"format": "dronedeploy", "contents": "label,latitude,longitude,elevation\n"},
    )
    assert header.status_code == 422
    assert "must be numbers" in header.json()["detail"]

    invalid_coordinates = client.post(
        "/georeferencing/control-points/import",
        json={"format": "pix4d", "contents": "gcp-1,91,-81.5,300\n"},
    )
    assert invalid_coordinates.status_code == 422
    assert "latitude must be between -90 and 90" in invalid_coordinates.json()["detail"]

    unknown_format = client.post(
        "/georeferencing/control-points/export",
        json={
            "format": "other",
            "points": [{"label": "gcp-1", "latitude": 1, "longitude": 2, "altitude_m": 3}],
        },
    )
    assert unknown_format.status_code == 422
    assert "format must be one of" in unknown_format.json()["detail"]
