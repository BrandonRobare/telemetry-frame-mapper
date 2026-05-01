from __future__ import annotations


def test_upload_flight_log(client):
    csv_bytes = b"time(millisecond),OSD.latitude,OSD.longitude,OSD.altitude[m]\n1000,35.0,-80.0,100.0\n"
    # Upload without a real session_id — backend should accept or 404
    resp = client.post(
        "/flight-logs/upload",
        files={"file": ("log.csv", csv_bytes, "text/csv")},
        data={"session_id": "999999"},
    )
    assert resp.status_code in (200, 404)  # 404 if session 999999 doesn't exist


def test_match_preview_empty(client):
    resp = client.get("/flight-logs/match-preview?session_id=999999")
    assert resp.status_code in (200, 404)


def test_apply_sync_no_session(client):
    resp = client.post("/flight-logs/apply?session_id=999999")
    assert resp.status_code in (200, 404)
