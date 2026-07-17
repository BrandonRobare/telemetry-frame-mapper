from __future__ import annotations

import json

from backend.db.models import Measurement, Reconstruction
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_reconstruction(db) -> Reconstruction:
    s = SessionModel(name="Meas Model Test", folder_path="/tmp/m", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete", progress_pct=100.0, frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_measurement_defaults(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)

    points = [{"x": 0.0, "y": 0.0, "z": 0.0}, {"x": 1.0, "y": 0.0, "z": 0.0}]
    m = Measurement(
        reconstruction_id=rec.id,
        kind="distance",
        points_json=json.dumps(points),
        value=1.0,
        unit="m",
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    assert m.id is not None
    assert m.created_at is not None
    assert m.label is None
    assert json.loads(m.points_json) == points


def test_measurement_cascade_delete(client):
    db = _get_db(client)
    rec = _make_reconstruction(db)
    rec_id = rec.id

    m = Measurement(
        reconstruction_id=rec_id,
        kind="point",
        points_json=json.dumps([{"x": 0.0, "y": 0.0, "z": 0.0}]),
    )
    db.add(m)
    db.commit()
    m_id = m.id

    db.delete(rec)
    db.commit()

    surviving = db.query(Measurement).filter(Measurement.id == m_id).first()
    assert surviving is None
