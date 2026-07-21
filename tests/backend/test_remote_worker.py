from __future__ import annotations

import json
import threading
from unittest.mock import patch

import httpx
import pytest

from backend.core.config import get_remote_worker_config
from backend.db.models import JobQueueEntry, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.job_queue import JobNonRetryableError
from backend.services.reconstruction import _run_remote_pipeline
from backend.services.remote_worker import (
    RemoteWorkerError,
    dispatch_reconstruction,
    get_reconstruction_status,
)


def _config(**overrides):
    return {
        "enabled": True,
        "url": "https://worker.example.test",
        "auth_token_env": "REMOTE_WORKER_TEST_TOKEN",
        "timeout_seconds": 3,
        "poll_interval_seconds": 1,
        "allow_insecure_http": False,
        **overrides,
    }


def test_remote_worker_config_defaults_to_disabled_and_secret_free(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("remote_worker:\n  enabled: true\n  url: https://worker.example.test\n")

    config = get_remote_worker_config(str(path))

    assert config["enabled"] is True
    assert config["auth_token_env"] == "REMOTE_WORKER_TOKEN"
    assert "token" not in config


def test_remote_worker_dispatch_uses_bearer_token_without_putting_it_in_payload(monkeypatch):
    monkeypatch.setenv("REMOTE_WORKER_TEST_TOKEN", "test-secret")
    request = httpx.Request("POST", "https://worker.example.test/v1/reconstructions")
    response = httpx.Response(202, json={"job_id": "worker-42"}, request=request)

    with patch("backend.services.remote_worker.httpx.request", return_value=response) as mocked:
        remote_id = dispatch_reconstruction(
            _config(),
            {"preset": "quick", "colmap_dir": "/shared/data/colmap/1", "image_ids": [1, 2]},
            reconstruction_id=1,
            queue_job_id=9,
        )

    assert remote_id == "worker-42"
    assert mocked.call_args.kwargs["headers"] == {"Authorization": "Bearer test-secret"}
    assert mocked.call_args.kwargs["json"] == {
        "local_job_id": 9,
        "reconstruction_id": 1,
        "preset": "quick",
        "colmap_dir": "/shared/data/colmap/1",
        "image_ids": [1, 2],
    }


def test_remote_worker_rejects_http_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("REMOTE_WORKER_TEST_TOKEN", "test-secret")
    with pytest.raises(RemoteWorkerError, match="HTTPS"):
        get_reconstruction_status(_config(url="http://worker.test"), "worker-1")


def test_remote_pipeline_persists_worker_id_and_tracks_completion(setup_test_db):
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        session = SessionModel(name="Remote", folder_path="/shared/imports")
        db.add(session)
        db.commit()
        rec = Reconstruction(session_id=session.id, preset="quick", status="pending", frames_used=2)
        db.add(rec)
        db.commit()
        entry = JobQueueEntry(
            job_type="reconstruction",
            target_id=rec.id,
            status="running",
            payload_json=json.dumps(
                {"preset": "quick", "colmap_dir": "/shared/data/1", "image_ids": []}
            ),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        with (
            patch(
                "backend.services.reconstruction.dispatch_reconstruction", return_value="worker-7"
            ),
            patch(
                "backend.services.reconstruction.get_reconstruction_status",
                return_value={
                    "status": "complete",
                    "result": {"frames_registered": 2, "gaussian_count": 123, "psnr": 25.4},
                },
            ),
            patch("backend.services.reconstruction.update_payload") as update,
        ):
            _run_remote_pipeline(
                entry, db, threading.Event(), json.loads(entry.payload_json), _config()
            )

        db.refresh(rec)
        assert rec.status == "complete"
        assert rec.progress_pct == 100.0
        assert rec.frames_registered == 2
        assert rec.gaussian_count == 123
        update.assert_called_once_with(entry.id, remote_job_id="worker-7")


def test_remote_pipeline_records_terminal_worker_failure_without_retry(setup_test_db):
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        session = SessionModel(name="Remote", folder_path="/shared/imports")
        db.add(session)
        db.commit()
        rec = Reconstruction(session_id=session.id, preset="quick", status="pending", frames_used=2)
        db.add(rec)
        db.commit()
        entry = JobQueueEntry(
            job_type="reconstruction",
            target_id=rec.id,
            status="running",
            payload_json=json.dumps(
                {
                    "preset": "quick",
                    "colmap_dir": "/shared/data/1",
                    "image_ids": [],
                    "remote_job_id": "w-8",
                }
            ),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        with patch(
            "backend.services.reconstruction.get_reconstruction_status",
            return_value={"status": "failed", "error": "GPU unavailable"},
        ):
            with pytest.raises(JobNonRetryableError, match="GPU unavailable"):
                _run_remote_pipeline(
                    entry, db, threading.Event(), json.loads(entry.payload_json), _config()
                )

        db.refresh(rec)
        assert rec.status == "failed"
        assert rec.error_msg == "GPU unavailable"


def test_remote_pipeline_preserves_worker_reported_cancellation(setup_test_db):
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        session = SessionModel(name="Remote", folder_path="/shared/imports")
        db.add(session)
        db.commit()
        rec = Reconstruction(session_id=session.id, preset="quick", status="pending", frames_used=2)
        db.add(rec)
        db.commit()
        entry = JobQueueEntry(
            job_type="reconstruction",
            target_id=rec.id,
            status="running",
            payload_json=json.dumps({
                "preset": "quick",
                "colmap_dir": "/shared/data/1",
                "image_ids": [],
                "remote_job_id": "w-9",
            }),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        with patch(
            "backend.services.reconstruction.get_reconstruction_status",
            return_value={"status": "cancelled", "error": "Cancelled by worker"},
        ), patch("backend.services.reconstruction.cancel_remote_reconstruction") as cancel_remote:
            _run_remote_pipeline(
                entry, db, threading.Event(), json.loads(entry.payload_json), _config()
            )

        db.refresh(rec)
        db.refresh(entry)
        assert rec.status == "cancelled"
        assert entry.status == "cancelled"
        cancel_remote.assert_not_called()


def _remote_entry(db, remote_job_id: str | None = None) -> tuple:
    from backend.db.models import JobQueueEntry, Reconstruction
    from backend.db.models import Session as SessionModel

    session = SessionModel(name="Remote", folder_path="/shared/imports")
    db.add(session)
    db.commit()
    rec = Reconstruction(session_id=session.id, preset="quick", status="pending", frames_used=2)
    db.add(rec)
    db.commit()
    payload = {"preset": "quick", "colmap_dir": "/shared/data/1", "image_ids": []}
    if remote_job_id:
        payload["remote_job_id"] = remote_job_id
    entry = JobQueueEntry(
        job_type="reconstruction",
        target_id=rec.id,
        status="running",
        payload_json=json.dumps(payload),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return rec, entry


def test_remote_pipeline_survives_transient_poll_failures(setup_test_db):
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        rec, entry = _remote_entry(db, remote_job_id="w-transient")
        # Two dropped polls (below the 5-failure threshold), then success.
        poll = patch(
            "backend.services.reconstruction.get_reconstruction_status",
            side_effect=[
                RemoteWorkerError("connection reset"),
                RemoteWorkerError("read timeout"),
                {"status": "complete", "result": {"frames_registered": 2, "gaussian_count": 9}},
            ],
        )
        with poll, patch(
            "backend.services.reconstruction.cancel_remote_reconstruction"
        ) as cancel_remote:
            _run_remote_pipeline(
                entry,
                db,
                threading.Event(),
                json.loads(entry.payload_json),
                _config(poll_interval_seconds=0),
            )

        db.refresh(rec)
        assert rec.status == "complete"
        assert rec.frames_registered == 2
        cancel_remote.assert_not_called()


def test_remote_pipeline_fails_and_cancels_remote_after_sustained_failures(
    setup_test_db, monkeypatch
):
    from tests.conftest import TestSessionLocal

    # Inject short thresholds so we never wait the real 10-minute window.
    monkeypatch.setattr(
        "backend.services.reconstruction._REMOTE_POLL_MAX_CONSECUTIVE_FAILURES", 3
    )
    monkeypatch.setattr("backend.services.reconstruction._REMOTE_POLL_FAILURE_WINDOW_S", 0)

    with TestSessionLocal() as db:
        rec, entry = _remote_entry(db, remote_job_id="w-dead")
        with patch(
            "backend.services.reconstruction.get_reconstruction_status",
            side_effect=RemoteWorkerError("connection reset"),
        ), patch(
            "backend.services.reconstruction.cancel_remote_reconstruction"
        ) as cancel_remote:
            with pytest.raises(JobNonRetryableError, match="unreachable"):
                _run_remote_pipeline(
                    entry,
                    db,
                    threading.Event(),
                    json.loads(entry.payload_json),
                    _config(poll_interval_seconds=0),
                )

        db.refresh(rec)
        assert rec.status == "failed"
        cancel_remote.assert_called_once_with(_config(poll_interval_seconds=0), "w-dead")


def test_remote_pipeline_user_cancel_sends_remote_cancel(setup_test_db):
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        rec, entry = _remote_entry(db, remote_job_id="w-usercancel")
        cancel = threading.Event()
        cancel.set()  # user cancelled before the first poll
        with patch(
            "backend.services.reconstruction.cancel_remote_reconstruction"
        ) as cancel_remote:
            _run_remote_pipeline(
                entry, db, cancel, json.loads(entry.payload_json), _config()
            )

        db.refresh(rec)
        assert rec.status == "cancelled"
        cancel_remote.assert_called_once_with(_config(), "w-usercancel")
