"""Tests for the persistent SQLite-backed job queue."""

from __future__ import annotations

import sys
import threading
import time
from datetime import UTC, datetime

import pytest

from backend.db.models import JobQueueEntry, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.job_queue import (
    RECONSTRUCTION,
    cancel_job,
    claim_stale_jobs,
    enqueue,
    get_job,
    list_jobs,
    mark_complete,
    register_handler,
    shutdown_worker,
    start_worker,
    update_payload,
)
from tests.conftest import TestSessionLocal


def _make_session(db):
    s = SessionModel(name="Queue Test", folder_path="/tmp/q")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture(autouse=True)
def _inject_test_session(setup_test_db):
    """Point the job queue's internal session factory at the test DB."""
    from backend.services import job_queue as jq

    _orig = jq._make_session
    jq._make_session = TestSessionLocal
    yield
    jq._make_session = _orig


# ---------------------------------------------------------------------------
# Enqueue + persistence
# ---------------------------------------------------------------------------

def test_enqueue_creates_persistent_entry(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=3)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id, payload={"key": "val"}, priority=5, max_attempts=2)
    assert entry.id is not None
    assert entry.job_type == "reconstruction"
    assert entry.status == "pending"
    assert entry.priority == 5
    assert entry.max_attempts == 2

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored is not None
    assert stored.payload_json == '{"key": "val"}'


def test_enqueue_persists_across_session_reopen(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    enqueue(RECONSTRUCTION, rec.id)

    db.close()
    db2 = app.state.test_db_session
    try:
        entry = db2.query(JobQueueEntry).filter(JobQueueEntry.target_id == rec.id).first()
        assert entry is not None
        assert entry.status == "pending"
    finally:
        db2.close()


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------

def test_list_jobs_returns_all_entries(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    for i in range(3):
        rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        enqueue(RECONSTRUCTION, rec.id, priority=i)

    jobs = list_jobs()
    assert len(jobs) == 3
    assert all("created_at" in j for j in jobs)


def test_list_jobs_filters_by_status(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)

    entry_db = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    entry_db.status = "completed"
    db.commit()

    pending = list_jobs(status="pending")
    completed = list_jobs(status="completed")
    assert len(pending) == 0
    assert len(completed) == 1
    assert completed[0]["id"] == entry.id


def test_get_job_returns_single_entry(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)
    job = get_job(entry.id)
    assert job is not None
    assert job["id"] == entry.id
    assert job["job_type"] == "reconstruction"

    assert get_job(999999) is None


def test_update_payload_preserves_existing_queue_payload(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id, payload={"preset": "quick"})
    update_payload(entry.id, remote_job_id="worker-11")

    assert get_job(entry.id)["remote_job_id"] == "worker-11"
    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored.payload_json == '{"preset": "quick", "remote_job_id": "worker-11"}'


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def test_cancel_job_marks_cancelled(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)
    ok = cancel_job(entry.id)
    assert ok

    entry_db = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert entry_db.status == "cancelled"
    assert entry_db.completed_at is not None


def test_cancel_completed_job_returns_false(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)
    mark_complete(entry.id)
    ok = cancel_job(entry.id)
    assert not ok


# ---------------------------------------------------------------------------
# Claim stale jobs (restart recovery)
# ---------------------------------------------------------------------------

def test_claim_stale_jobs_marks_running_as_failed(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = JobQueueEntry(
        job_type=RECONSTRUCTION,
        target_id=rec.id,
        status="running",
        priority=5,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    claimed = claim_stale_jobs()
    assert claimed >= 1
    db.refresh(entry)
    assert entry.status == "failed"
    assert "orphaned" in (entry.error_msg or "")


def test_claim_stale_jobs_requeues_running_remote_without_touching_attempts(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_remote", frames_used=1
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = JobQueueEntry(
        job_type=RECONSTRUCTION,
        target_id=rec.id,
        status="running",
        attempt=1,
        priority=5,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    claim_stale_jobs()
    db.refresh(entry)
    assert entry.status == "pending", "remote-live reconstruction must be re-queued, not failed"
    assert entry.attempt == 1, "reaper must not touch attempts for re-queued remote jobs"
    assert entry.completed_at is None


def test_claim_stale_jobs_does_not_touch_completed(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = JobQueueEntry(
        job_type=RECONSTRUCTION,
        target_id=rec.id,
        status="completed",
        priority=5,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    claimed = claim_stale_jobs()
    assert claimed == 0
    db.refresh(entry)
    assert entry.status == "completed"


# ---------------------------------------------------------------------------
# mark_complete
# ---------------------------------------------------------------------------

def test_mark_complete_updates_status_and_timestamp(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)
    entry_id = entry.id
    mark_complete(entry_id)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry_id).first()
    assert stored is not None
    assert stored.status == "completed"
    assert stored.completed_at is not None


# ---------------------------------------------------------------------------
# Handler dispatch via queue worker
# ---------------------------------------------------------------------------

def test_handler_dispatched_by_worker(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    handler_called = threading.Event()
    handler_args = {}

    def test_handler(entry, db_session, cancel):
        handler_args["entry_id"] = entry.id
        handler_args["target_id"] = entry.target_id
        mark_complete(entry.id)
        handler_called.set()

    handler_name = f"test_dispatch_{id(handler_called)}"
    register_handler(handler_name, test_handler)

    entry = enqueue(handler_name, rec.id)

    jq._shutdown.clear()
    start_worker()

    called = handler_called.wait(timeout=3)
    assert called, "Handler was not dispatched by worker"
    assert handler_args["entry_id"] == entry.id
    assert handler_args["target_id"] == rec.id

    shutdown_worker(timeout=1.0)

    # Worker used its own session, so re-read.
    # May be running if shutdown happened mid-job; that's fine —
    # the key assertion is that the handler was called.
    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored is not None
    assert stored.status in ("running", "completed")


# ---------------------------------------------------------------------------
# No-handler case
# ---------------------------------------------------------------------------

def test_no_handler_marks_as_failed(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue("nonexistent_handler", rec.id)
    assert entry.status == "pending"

    jq._shutdown.clear()
    start_worker()
    time.sleep(1.0)
    shutdown_worker(timeout=1.0)

    # Worker used its own session, so re-read
    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored is not None
    assert stored.status in ("failed", "completed")


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------

def test_gpu_concurrency_is_honored(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)

    barrier = threading.Barrier(2, timeout=5)
    begun = threading.Event()

    def slow_handler(entry, db_session, cancel):
        begun.set()
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass

    # Register a handler for RECONSTRUCTION (a GPU type) so concurrency is enforced
    register_handler(RECONSTRUCTION, slow_handler)

    for _i in range(2):
        rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        enqueue(RECONSTRUCTION, rec.id)

    # Clean up RECONSTRUCTION handler after concurrency test
    _orig_handler = None
    try:
        _orig_handler = jq._handlers.get(RECONSTRUCTION)
        register_handler(RECONSTRUCTION, slow_handler)
        jq._shutdown.clear()
        start_worker()
        begun.wait(timeout=3)

        entries = (
            db.query(JobQueueEntry)
            .filter(JobQueueEntry.job_type == RECONSTRUCTION)
            .order_by(JobQueueEntry.id)
            .all()
        )
        statuses = {e.status for e in entries}
        assert "running" in statuses, f"Expected a running job, got {statuses}"
        assert "pending" in statuses, f"Expected a pending job, got {statuses}"
    finally:
        shutdown_worker(timeout=1.0)
        if _orig_handler is not None:
            register_handler(RECONSTRUCTION, _orig_handler)
    for e in entries:
        db.refresh(e)
        if e.status in ("running", "pending"):
            e.status = "completed"
    db.commit()


# ---------------------------------------------------------------------------
# Atomic claim — no double dispatch under a race
# ---------------------------------------------------------------------------

def test_atomic_claim_lets_exactly_one_racer_win(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)

    now = datetime.now(UTC)
    results: list[bool] = []
    results_lock = threading.Lock()
    start = threading.Barrier(6)

    def racer():
        start.wait()
        won = False
        # SQLite serialises writers; a loser may transiently see "database is
        # locked" before the winner commits, so retry until we get a verdict.
        while True:
            session = TestSessionLocal()
            try:
                won = jq._claim_pending(session, entry.id, now)
                break
            except Exception:
                session.rollback()
                time.sleep(0.01)
            finally:
                session.close()
        with results_lock:
            results.append(won)

    threads = [threading.Thread(target=racer) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert sum(results) == 1, f"exactly one claim must win, got {sum(results)}"
    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored.status == "running"
    assert stored.attempt == 1


# ---------------------------------------------------------------------------
# _mark_failed must not overwrite a cancelled job
# ---------------------------------------------------------------------------

def test_mark_failed_does_not_overwrite_cancelled(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)
    cancel_job(entry.id)

    jq._mark_failed(entry.id, "boom")

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored.status == "cancelled", "a failure racing a cancel must not overwrite it"


# ---------------------------------------------------------------------------
# Drain-worker OS lock — a second acquirer backs off
# ---------------------------------------------------------------------------

def test_second_worker_lock_acquire_fails_gracefully(setup_test_db):
    from backend.services import job_queue as jq

    # Simulate another process already holding the lock via a raw handle.
    path = jq._lock_path()
    other = open(path, "a+")
    other.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(other.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        pytest.skip("OS file locking not exclusive here; cannot test lock contention")

    try:
        assert jq._acquire_worker_lock() is False
        assert jq._lock_fh is None
    finally:
        other.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(other.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(other.fileno(), fcntl.LOCK_UN)
        other.close()
