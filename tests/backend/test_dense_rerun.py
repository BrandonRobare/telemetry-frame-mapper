from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.db.models import Image, Reconstruction, ReconstructionFrame, SessionFrameSelection
from backend.db.models import Session as SessionModel
from backend.services.reconstruction import plan_dense_rerun


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def _weak_reconstruction(db):
    session = SessionModel(name="Dense rerun", folder_path="/tmp/dense")
    db.add(session)
    db.commit()
    images = []
    for index in range(6):
        image = Image(
            session_id=session.id,
            filename=f"frame_{index}.jpg",
            filepath=f"/tmp/frame_{index}.jpg",
            usable=True,
        )
        db.add(image)
        images.append(image)
    db.commit()
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=4,
        frames_registered=2,
    )
    db.add(rec)
    db.commit()
    for image, error in zip(
        (images[0], images[2], images[3], images[5]), (0.4, None, None, 0.7), strict=True
    ):
        db.add(
            ReconstructionFrame(
                reconstruction_id=rec.id,
                image_id=image.id,
                colmap_error_px=error,
            )
        )
    db.commit()
    return rec, images


def test_plan_dense_rerun_adds_viable_images_around_contiguous_weak_span(client):
    db = _db(client)
    rec, images = _weak_reconstruction(db)

    plan = plan_dense_rerun(db, rec)

    assert plan["source_image_ids"] == [images[0].id, images[2].id, images[3].id, images[5].id]
    assert plan["added_image_ids"] == [images[1].id, images[4].id]
    assert plan["rerun_image_ids"] == [image.id for image in images]
    assert plan["weak_spans"] == [
        {
            "source_image_ids": [images[2].id, images[3].id],
            "candidate_image_ids": [images[1].id, images[2].id, images[3].id, images[4].id],
            "added_image_ids": [images[1].id, images[4].id],
            "start_image_id": images[2].id,
            "end_image_id": images[3].id,
        }
    ]


def test_plan_dense_rerun_refuses_missing_reprojection_evidence(client):
    db = _db(client)
    rec, _ = _weak_reconstruction(db)
    db.query(ReconstructionFrame).filter(ReconstructionFrame.reconstruction_id == rec.id).update(
        {"colmap_error_px": None}
    )
    db.commit()

    with pytest.raises(ValueError, match="Per-frame reprojection data is unavailable"):
        plan_dense_rerun(db, rec)


def test_dense_rerun_router_requires_confirmation_and_preserves_parent_selection(client):
    db = _db(client)
    rec, images = _weak_reconstruction(db)
    db.add(SessionFrameSelection(session_id=rec.session_id, image_id=images[0].id))
    db.commit()

    assert client.post(f"/reconstruction/{rec.id}/dense-rerun", json={}).status_code == 422
    preview = client.get(f"/reconstruction/{rec.id}/dense-rerun-plan")
    assert preview.status_code == 200
    assert preview.json()["added_image_ids"] == [images[1].id, images[4].id]

    child = Reconstruction(
        id=999,
        session_id=rec.session_id,
        parent_reconstruction_id=rec.id,
        status="pending",
        preset="quick",
        progress_pct=0.0,
        frames_used=6,
        step="",
    )
    with patch("backend.routers.reconstruction.start_reconstruction", return_value=child) as start:
        response = client.post(f"/reconstruction/{rec.id}/dense-rerun", json={"confirm": True})

    assert response.status_code == 201
    assert response.json()["parent_reconstruction_id"] == rec.id
    assert start.call_args.kwargs["selected_image_ids"] == [image.id for image in images]
    assert start.call_args.kwargs["parent_reconstruction_id"] == rec.id
    assert [row.image_id for row in db.query(SessionFrameSelection).all()] == [images[0].id]


def test_dense_rerun_router_rejects_active_child(client):
    db = _db(client)
    rec, _ = _weak_reconstruction(db)
    db.add(
        Reconstruction(
            session_id=rec.session_id,
            parent_reconstruction_id=rec.id,
            status="pending",
        )
    )
    db.commit()

    response = client.post(f"/reconstruction/{rec.id}/dense-rerun", json={"confirm": True})

    assert response.status_code == 409
