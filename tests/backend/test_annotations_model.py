from __future__ import annotations

from backend.db.models import Annotation, Reconstruction
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def test_annotation_defaults(client):
    db = _get_db(client)
    s = SessionModel(name="Model Test", folder_path="/tmp/m", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete", progress_pct=100.0, frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    ann = Annotation(reconstruction_id=rec.id, label="Test", lat=1.0, lon=2.0, alt_m=10.0)
    db.add(ann)
    db.commit()
    db.refresh(ann)

    assert ann.color == "#ff6b35"
    assert ann.created_at is not None
    assert ann.id is not None


def test_annotation_cascade_delete(client):
    db = _get_db(client)
    s = SessionModel(name="Cascade Test", folder_path="/tmp/c", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="complete", progress_pct=100.0, frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    rec_id = rec.id

    ann = Annotation(
        reconstruction_id=rec_id, label="Will be deleted", lat=1.0, lon=2.0, alt_m=10.0
    )
    db.add(ann)
    db.commit()
    ann_id = ann.id

    db.delete(rec)
    db.commit()

    surviving = db.query(Annotation).filter(Annotation.id == ann_id).first()
    assert surviving is None
