from backend.db.models import Image
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


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
    assert "# EPSG:4326" in resp.json()["contents"]
    assert "frame_001.jpg north-pad" in resp.json()["contents"]
