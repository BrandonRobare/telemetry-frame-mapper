import json

from backend.db.models import Reconstruction, SessionComparison
from backend.db.models import Session as SessionModel


def _db(client):
    from backend.main import app

    return app.state.test_db_session


def test_comparison_metrics_reports_area_volume_and_alignment(client, tmp_path):
    db = _db(client)
    a = SessionModel(name="A", folder_path="/tmp/a")
    b = SessionModel(name="B", folder_path="/tmp/b")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    ra = Reconstruction(session_id=a.id, status="complete", frames_used=1)
    rb = Reconstruction(session_id=b.id, status="complete", frames_used=1)
    db.add_all([ra, rb])
    db.commit()
    db.refresh(ra)
    db.refresh(rb)
    diff = tmp_path / "diff.json"
    diff.write_text(
        json.dumps(
            {
                "new": [{"size": 2}],
                "removed": [{"size": 1}],
                "alignment": {"method": "gcp", "status": "applied"},
            }
        )
    )
    comp = SessionComparison(
        session_a_id=a.id,
        session_b_id=b.id,
        reconstruction_a_id=ra.id,
        reconstruction_b_id=rb.id,
        status="complete",
        diff_path=str(diff),
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    body = client.get(f"/comparisons/{comp.id}/metrics").json()
    assert body["net_volume_m3"] == 7.0
    assert body["changed_area_m2"] == 5.0
    assert body["alignment"]["method"] == "gcp"
