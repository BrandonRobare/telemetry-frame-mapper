from __future__ import annotations

from backend.db.models import Image
from backend.services.artifact_cleanup import remove_artifacts, session_artifact_paths


def test_session_artifact_removal_does_not_remove_paths_outside_configured_roots(tmp_path):
    processed_dir = tmp_path / "processed"
    inside = processed_dir / "1" / "thumbs" / "frame.jpg"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"thumb")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"keep")
    cfg = type(
        "Cfg",
        (),
        {
            "processed_dir": str(processed_dir),
            "exports_dir": str(tmp_path / "exports"),
            "data_dir": str(tmp_path / "data"),
        },
    )()

    paths = session_artifact_paths(
        1,
        [
            Image(
                session_id=1,
                filename="inside.jpg",
                filepath="/tmp/inside.jpg",
                thumb_path=str(inside),
            ),
            Image(
                session_id=1,
                filename="outside.jpg",
                filepath="/tmp/outside.jpg",
                thumb_path=str(outside),
            ),
        ],
        [],
        cfg,
    )
    removed = remove_artifacts(paths, cfg)

    assert str(inside.resolve()) in removed
    assert not inside.exists()
    assert outside.exists()
