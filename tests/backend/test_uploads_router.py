from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch

from PIL import Image as PILImage
from starlette.datastructures import UploadFile


def test_browser_upload_plan_rejects_oversized_total(client, tmp_path):
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 10,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits):
        resp = client.post("/uploads/imports/start", json={
            "name": "Too Big",
            "total_bytes": 11,
            "files": [{"path": "a.jpg", "size": 11}],
        })

    assert resp.status_code == 413


def test_browser_upload_rejects_unsafe_paths(client, tmp_path):
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 10,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits):
        resp = client.post("/uploads/imports/start", json={
            "name": "Unsafe",
            "total_bytes": 1,
            "files": [{"path": "../a.jpg", "size": 1}],
        })

    assert resp.status_code == 400


def test_browser_upload_chunks_complete_and_start_import(client, tmp_path):
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg", ".jpeg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits), \
         patch("backend.routers.uploads.start_import") as mock_start:
        start = client.post("/uploads/imports/start", json={
            "name": "Browser Import",
            "total_bytes": 6,
            "files": [{"path": "flight/a.jpg", "size": 6}],
        })
        assert start.status_code == 200
        upload_id = start.json()["upload_id"]
        assert start.json()["chunk_size"] == 4

        first = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "flight/a.jpg", "offset": "0"},
            files={"chunk": ("chunk", b"abcd", "application/octet-stream")},
        )
        assert first.status_code == 200
        assert first.json()["uploaded_bytes"] == 4

        second = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "flight/a.jpg", "offset": "4"},
            files={"chunk": ("chunk", b"ef", "application/octet-stream")},
        )
        assert second.status_code == 200
        assert second.json()["uploaded_bytes"] == 6

        done = client.post(f"/uploads/imports/{upload_id}/complete")
        assert done.status_code == 200
        body = done.json()
        assert body["status"] == "importing"
        assert body["session"]["name"] == "Browser Import"
        session_id = body["session_id"]

    uploaded = tmp_path / "imports" / ".browser_uploads" / upload_id / "flight" / "a.jpg"
    assert uploaded.read_bytes() == b"abcdef"
    assert mock_start.call_count == 1
    assert mock_start.call_args.args[0] == session_id


def test_browser_chunk_endpoint_reads_only_one_byte_beyond_limit(client, tmp_path, monkeypatch):
    """The browser endpoint itself must preserve the helper's allocation bound."""
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 10,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    requested_sizes: list[int] = []
    original_read = UploadFile.read

    async def recording_read(self, size: int = -1):
        requested_sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", recording_read)
    with patch("backend.routers.uploads.get_config", return_value=cfg), patch(
        "backend.routers.uploads.get_browser_upload_config", return_value=limits
    ):
        start = client.post(
            "/uploads/imports/start",
            json={
                "name": "Bounded browser upload",
                "total_bytes": 4,
                "files": [{"path": "a.jpg", "size": 4}],
            },
        )
        upload_id = start.json()["upload_id"]
        response = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "a.jpg", "offset": "0"},
            files={"chunk": ("chunk", b"abcd", "application/octet-stream")},
        )

    assert response.status_code == 200
    assert requested_sizes == [limits["chunk_size_bytes"] + 1]


def test_browser_upload_imports_nested_webkit_relative_path(client, tmp_path):
    """The browser uploader preserves a nested path which shared ingest then imports."""
    from backend.db.models import Image
    from backend.main import app
    from backend.services.ingest_orchestrator import _run
    from tests.conftest import TestSessionLocal

    payload = BytesIO()
    PILImage.new("RGB", (100, 100)).save(payload, format="JPEG")
    image_bytes = payload.getvalue()
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": len(image_bytes),
        "max_file_bytes": len(image_bytes),
        "max_total_bytes": len(image_bytes),
        "quota_bytes": len(image_bytes) * 2,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    ingest_cfg = {
        "accepted_extensions": [".jpg"],
        "filter_zero_gps": False,
        "thumbnail_size_px": 64,
        "thumbnail_jpeg_quality": 75,
    }

    with patch("backend.routers.uploads.get_config", return_value=cfg), patch(
        "backend.routers.uploads.get_browser_upload_config", return_value=limits
    ), patch("backend.core.config.get_ingest_config", return_value=ingest_cfg), patch(
        "backend.core.config.load_config"
    ) as mock_load_cfg, patch(
        "backend.routers.uploads.start_import",
        side_effect=lambda session_id, folder, _db_factory: _run(
            session_id, folder, TestSessionLocal
        ),
    ):
        mock_load_cfg.return_value.processed_dir = str(tmp_path / "processed")
        mock_load_cfg.return_value.thumbnail_size_px = 64
        mock_load_cfg.return_value.fov_horizontal_deg = 83
        mock_load_cfg.return_value.fov_vertical_deg = 53
        mock_load_cfg.return_value.target_crs = "EPSG:32617"
        start = client.post("/uploads/imports/start", json={
            "name": "Nested browser import",
            "total_bytes": len(image_bytes),
            "files": [{"path": "DCIM/100MEDIA/DJI_0001.jpg", "size": len(image_bytes)}],
        })
        upload_id = start.json()["upload_id"]
        chunk = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "DCIM/100MEDIA/DJI_0001.jpg", "offset": "0"},
            files={"chunk": ("chunk", image_bytes, "application/octet-stream")},
        )
        assert chunk.status_code == 200
        completed = client.post(f"/uploads/imports/{upload_id}/complete")

    assert completed.status_code == 200
    db = app.state.test_db_session
    images = db.query(Image).filter(Image.session_id == completed.json()["session_id"]).all()
    assert [image.filepath for image in images] == [
        str(
            tmp_path
            / "imports"
            / ".browser_uploads"
            / upload_id
            / "DCIM"
            / "100MEDIA"
            / "DJI_0001.jpg"
        )
    ]


def test_browser_upload_accepts_user_selected_cloud_synced_folder(client, tmp_path):
    """Cloud-provider authorization stays in the desktop sync client/browser picker."""
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits), \
         patch("backend.routers.uploads.start_import"):
        start = client.post("/uploads/imports/start", json={
            "name": "Cloud Drive Flight",
            "total_bytes": 4,
            "files": [{"path": "OneDrive/flight/a.jpg", "size": 4}],
        })
        assert start.status_code == 200
        upload_id = start.json()["upload_id"]

        chunk = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "OneDrive/flight/a.jpg", "offset": "0"},
            files={"chunk": ("chunk", b"jpeg", "application/octet-stream")},
        )
        assert chunk.status_code == 200
        assert client.post(f"/uploads/imports/{upload_id}/complete").status_code == 200

    uploaded = (
        tmp_path / "imports" / ".browser_uploads" / upload_id / "OneDrive" / "flight" / "a.jpg"
    )
    assert uploaded.read_bytes() == b"jpeg"


def test_browser_upload_cancel_removes_staging_dir(client, tmp_path):
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits):
        start = client.post("/uploads/imports/start", json={
            "name": "Cancel Me",
            "total_bytes": 4,
            "files": [{"path": "a.jpg", "size": 4}],
        })
        upload_id = start.json()["upload_id"]
        staging = tmp_path / "imports" / ".browser_uploads" / upload_id
        assert staging.exists()

        resp = client.post(f"/uploads/imports/{upload_id}/cancel")

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert not staging.exists()



def test_browser_upload_progress_survives_in_memory_state_loss(client, tmp_path):
    from backend.routers import uploads

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits):
        start = client.post("/uploads/imports/start", json={
            "name": "Resume Me",
            "total_bytes": 4,
            "files": [{"path": "flight/a.jpg", "size": 4}],
        })
        assert start.status_code == 200
        upload_id = start.json()["upload_id"]
        chunk = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "flight/a.jpg", "offset": "0"},
            files={"chunk": ("chunk", b"ab", "application/octet-stream")},
        )
        assert chunk.status_code == 200

        uploads._UPLOADS.clear()
        uploads._UPLOAD_LOCKS.clear()

        progress = client.get(f"/uploads/imports/{upload_id}")

    assert progress.status_code == 200
    assert progress.json()["uploaded_bytes"] == 2
    manifest = tmp_path / "imports" / ".browser_uploads" / upload_id / ".upload.json"
    assert json.loads(manifest.read_text())["files"]["flight/a.jpg"]["received"] == 2


def test_browser_upload_chunk_rejects_offset_when_file_size_drifted(client, tmp_path):
    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    limits = {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config", return_value=limits):
        start = client.post("/uploads/imports/start", json={
            "name": "Drift",
            "total_bytes": 4,
            "files": [{"path": "a.jpg", "size": 4}],
        })
        assert start.status_code == 200
        upload_id = start.json()["upload_id"]
        dest = tmp_path / "imports" / ".browser_uploads" / upload_id / "a.jpg"
        dest.write_bytes(b"stale")

        resp = client.post(
            f"/uploads/imports/{upload_id}/chunk",
            data={"path": "a.jpg", "offset": "0"},
            files={"chunk": ("chunk", b"ab", "application/octet-stream")},
        )

    assert resp.status_code == 409
    assert "offset" in resp.json()["detail"].lower()


def _idempotency_limits() -> dict:
    return {
        "chunk_size_bytes": 4,
        "max_file_bytes": 10,
        "max_total_bytes": 20,
        "quota_bytes": 100,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }


def _upload_one_file(client, name: str) -> str:
    start = client.post("/uploads/imports/start", json={
        "name": name,
        "total_bytes": 4,
        "files": [{"path": "a.jpg", "size": 4}],
    })
    assert start.status_code == 200
    upload_id = start.json()["upload_id"]
    chunk = client.post(
        f"/uploads/imports/{upload_id}/chunk",
        data={"path": "a.jpg", "offset": "0"},
        files={"chunk": ("chunk", b"abcd", "application/octet-stream")},
    )
    assert chunk.status_code == 200
    return upload_id


def test_browser_upload_complete_is_idempotent(client, db_session, tmp_path):
    """A retried /complete returns the first session instead of importing twice (#602)."""
    from backend.db.models import Session as SessionModel
    from backend.routers import uploads

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config",
               return_value=_idempotency_limits()), \
         patch("backend.routers.uploads.start_import") as mock_start:
        upload_id = _upload_one_file(client, "Retry Me")

        first = client.post(f"/uploads/imports/{upload_id}/complete")
        second = client.post(f"/uploads/imports/{upload_id}/complete")

        # Same replay once the in-memory state is lost and the manifest is reloaded.
        uploads._UPLOADS.clear()
        uploads._UPLOAD_LOCKS.clear()
        third = client.post(f"/uploads/imports/{upload_id}/complete")

    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 200]
    assert second.json() == first.json()
    assert third.json() == first.json()
    assert db_session.query(SessionModel).count() == 1
    assert mock_start.call_count == 1


def test_browser_upload_concurrent_complete_imports_once(client, db_session, tmp_path):
    """Two simultaneous /complete calls still produce one session and one import (#602)."""
    from backend.db.models import Session as SessionModel

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config",
               return_value=_idempotency_limits()), \
         patch("backend.routers.uploads.start_import") as mock_start:
        upload_id = _upload_one_file(client, "Double Click")
        barrier = threading.Barrier(2)

        def complete():
            barrier.wait(timeout=5)
            return client.post(f"/uploads/imports/{upload_id}/complete")

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [f.result() for f in [pool.submit(complete), pool.submit(complete)]]

    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["session_id"] == responses[1].json()["session_id"]
    assert db_session.query(SessionModel).count() == 1
    assert mock_start.call_count == 1


def _quota_limits() -> dict:
    return {
        "chunk_size_bytes": 1024,
        "max_file_bytes": 6000,
        "max_total_bytes": 6000,
        "quota_bytes": 10_000,
        "cleanup_after_hours": 24,
        "accepted_extensions": [".jpg"],
    }


def _quota_plan() -> dict:
    return {"name": "Reserve", "total_bytes": 6000, "files": [{"path": "a.jpg", "size": 6000}]}


def test_browser_upload_concurrent_starts_do_not_overcommit_quota(client, tmp_path):
    """Two simultaneous starts must not both reserve against the same measurement (#601)."""
    from backend.routers import uploads

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    barrier = threading.Barrier(2)
    real_dir_size = uploads._dir_size

    def gated_dir_size(path):
        size = real_dir_size(path)
        # Both starts meet here with their quota measurement in hand. Once the check
        # and the reservation share a critical section only one start can be here at
        # a time, so the barrier breaks on the timeout instead of tripping.
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return size

    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config",
               return_value=_quota_limits()), \
         patch("backend.routers.uploads._dir_size", gated_dir_size):

        def start():
            return client.post("/uploads/imports/start", json=_quota_plan())

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [f.result() for f in [pool.submit(start), pool.submit(start)]]

    assert sorted(r.status_code for r in responses) == [200, 507]
    staged = [p for p in (tmp_path / "imports" / ".browser_uploads").iterdir() if p.is_dir()]
    assert len(staged) == 1


def test_browser_upload_reservation_survives_state_loss_and_releases_on_cancel(client, tmp_path):
    """A started upload holds its whole plan against the quota until cancelled (#601)."""
    from backend.routers import uploads

    cfg = type("Cfg", (), {"imports_dir": str(tmp_path / "imports")})()
    with patch("backend.routers.uploads.get_config", return_value=cfg), \
         patch("backend.routers.uploads.get_browser_upload_config",
               return_value=_quota_limits()):
        first = client.post("/uploads/imports/start", json=_quota_plan())
        assert first.status_code == 200
        upload_id = first.json()["upload_id"]

        # No chunk has arrived, so the reservation exists only in the manifest.
        uploads._UPLOADS.clear()
        uploads._UPLOAD_LOCKS.clear()
        second = client.post("/uploads/imports/start", json=_quota_plan())
        assert second.status_code == 507

        assert client.post(f"/uploads/imports/{upload_id}/cancel").status_code == 200
        third = client.post("/uploads/imports/start", json=_quota_plan())

    assert third.status_code == 200
