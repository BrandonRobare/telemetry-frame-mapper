from __future__ import annotations

_POLYGON = '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'


def _make_session(name: str = "live-coverage"):
    from backend.db.database import get_db
    from backend.db.models import Session as SM
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    session = SM(name=name, folder_path="/tmp", photo_count=0, usable_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session.id


def _add_footprint(session_id: int, filename: str) -> int:
    """Insert one image + footprint the way ingest_orchestrator does, one at a time
    (mirrors incremental per-image commits during import) and return the footprint id."""
    from backend.db.database import get_db
    from backend.db.models import Footprint, Image
    from backend.main import app

    db = next(app.dependency_overrides[get_db]())
    image = Image(session_id=session_id, filename=filename, filepath=f"/tmp/{filename}")
    db.add(image)
    db.commit()
    db.refresh(image)

    footprint = Footprint(
        image_id=image.id,
        geom_geojson=_POLYGON,
        ground_width_m=10.0,
        ground_height_m=8.0,
        heading_estimated=True,
    )
    db.add(footprint)
    db.commit()
    db.refresh(footprint)
    return footprint.id


def test_list_footprints_returns_all_for_session(client):
    session_id = _make_session()
    _add_footprint(session_id, "frame_001.jpg")
    _add_footprint(session_id, "frame_002.jpg")

    resp = client.get(f"/footprints?session_id={session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert [fp["id"] for fp in body] == sorted(fp["id"] for fp in body)


def test_list_footprints_since_id_filters_newer_only(client):
    """Polling clients pass since_id=<last seen id> to fetch only newly-persisted
    footprints, so live coverage overlays don't have to re-fetch the whole session
    on every poll tick while ingest is still running."""
    session_id = _make_session()
    first_id = _add_footprint(session_id, "frame_001.jpg")
    _add_footprint(session_id, "frame_002.jpg")
    third_id = _add_footprint(session_id, "frame_003.jpg")

    resp = client.get(f"/footprints?session_id={session_id}&since_id={first_id}")
    assert resp.status_code == 200
    body = resp.json()
    ids = [fp["id"] for fp in body]
    assert first_id not in ids
    assert third_id in ids
    assert len(body) == 2


def test_list_footprints_since_id_zero_returns_all(client):
    session_id = _make_session()
    _add_footprint(session_id, "frame_001.jpg")

    resp = client.get(f"/footprints?session_id={session_id}&since_id=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_footprints_since_id_beyond_latest_returns_empty(client):
    session_id = _make_session()
    last_id = _add_footprint(session_id, "frame_001.jpg")

    resp = client.get(f"/footprints?session_id={session_id}&since_id={last_id}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_footprints_scoped_to_session(client):
    session_a = _make_session("a")
    session_b = _make_session("b")
    _add_footprint(session_a, "a1.jpg")
    _add_footprint(session_b, "b1.jpg")

    resp = client.get(f"/footprints?session_id={session_a}&since_id=0")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["image_id"]
