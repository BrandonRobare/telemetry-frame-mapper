from __future__ import annotations

from backend.db.models import Defect, DefectImage, Image
from backend.db.models import Session as SessionModel


def _get_db(client):
    from backend.db.database import get_db
    from backend.main import app
    return next(app.dependency_overrides[get_db]())


def _make_session_and_image(db) -> tuple[SessionModel, Image]:
    s = SessionModel(name="Defect Model Test", folder_path="/tmp/dm", photo_count=1, usable_count=1)
    db.add(s)
    db.commit()
    db.refresh(s)
    img = Image(
        session_id=s.id,
        filename="a.jpg",
        filepath="/tmp/a.jpg",
        latitude=35.1,
        longitude=-80.2,
        usable=True,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return s, img


def test_defect_defaults(client):
    db = _get_db(client)
    s, img = _make_session_and_image(db)

    defect = Defect(session_id=s.id, category="crack", note="Hairline crack near footing")
    db.add(defect)
    db.commit()
    db.refresh(defect)

    assert defect.id is not None
    assert defect.created_at is not None
    assert defect.severity is None

    db.add(DefectImage(defect_id=defect.id, image_id=img.id))
    db.commit()

    links = db.query(DefectImage).filter(DefectImage.defect_id == defect.id).all()
    assert [link.image_id for link in links] == [img.id]


def test_defect_cascade_delete_on_session(client):
    db = _get_db(client)
    s, img = _make_session_and_image(db)
    defect = Defect(session_id=s.id, category="corrosion")
    db.add(defect)
    db.commit()
    db.refresh(defect)
    db.add(DefectImage(defect_id=defect.id, image_id=img.id))
    db.commit()
    defect_id = defect.id

    db.delete(s)
    db.commit()

    assert db.query(Defect).filter(Defect.id == defect_id).first() is None
    assert db.query(DefectImage).filter(DefectImage.defect_id == defect_id).first() is None


def test_defect_image_link_removed_when_defect_deleted(client):
    db = _get_db(client)
    s, img = _make_session_and_image(db)
    defect = Defect(session_id=s.id, category="other")
    db.add(defect)
    db.commit()
    db.refresh(defect)
    db.add(DefectImage(defect_id=defect.id, image_id=img.id))
    db.commit()
    defect_id = defect.id

    db.delete(defect)
    db.commit()

    assert db.query(DefectImage).filter(DefectImage.defect_id == defect_id).first() is None
    # The image itself must survive — only the link is removed.
    assert db.query(Image).filter(Image.id == img.id).first() is not None
