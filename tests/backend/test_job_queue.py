"""Tests for the persistent SQLite-backed job queue."""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import OperationalError

from backend.db.models import JobQueueEntry, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.job_queue import (
    MESH_EXPORT,
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


def test_list_jobs_exposes_effective_splat_settings(setup_test_db):
    from backend.main import app
    from backend.routers.jobs import list_jobs as list_reconstruction_jobs

    db = app.state.test_db_session
    s = _make_session(db)
    settings = {
        "preset": "quick",
        "accelerator_kind": "metal",
        "splat_backend": "metal_msplat",
        "iterations": 2400,
        "max_gaussians": 350000,
    }
    rec = Reconstruction(
        session_id=s.id,
        preset="quick",
        status="pending",
        frames_used=77,
        effective_splat_settings=json.dumps(settings),
    )
    db.add(rec)
    db.commit()

    jobs = list_reconstruction_jobs(skip=0, limit=50, status=None, db=db)

    assert jobs[0]["effective_splat_settings"] == settings


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


def test_cancel_pending_reconstruction_marks_target_cancelled(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id)

    assert cancel_job(entry.id)

    db.refresh(rec)
    assert rec.status == "cancelled"
    assert rec.step == "cancelled"
    assert rec.completed_at is not None


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


def test_claim_stale_reconstruction_marks_target_failed(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(
        session_id=s.id, preset="quick", status="running_colmap", frames_used=1
    )
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

    claim_stale_jobs()

    db.refresh(rec)
    assert rec.status == "failed"
    assert rec.step == "failed"
    assert "orphaned" in (rec.error_msg or "")
    assert rec.completed_at is not None


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
    handler_thread = []
    handler_name = f"test_dispatch_{id(handler_called)}"
    original_handler = jq._handlers.get(handler_name)

    def test_handler(entry, db_session, cancel):
        handler_thread.append(threading.current_thread())
        handler_args["entry_id"] = entry.id
        handler_args["target_id"] = entry.target_id
        mark_complete(entry.id)
        handler_called.set()

    try:
        register_handler(handler_name, test_handler)
        entry = enqueue(handler_name, rec.id)
        jq._shutdown.clear()
        start_worker()

        assert handler_called.wait(timeout=3), "Handler was not dispatched by worker"
        assert handler_args["entry_id"] == entry.id
        assert handler_args["target_id"] == rec.id

        # Worker used its own session; read the committed terminal state afresh.
        fresh_db = TestSessionLocal()
        try:
            stored = fresh_db.query(JobQueueEntry).filter(
                JobQueueEntry.id == entry.id
            ).one()
            assert stored.status == "completed"
        finally:
            fresh_db.close()
    finally:
        shutdown_worker(timeout=5.0)
        if handler_thread:
            handler_thread[0].join(timeout=5)
        handler_stopped = not handler_thread or not handler_thread[0].is_alive()
        if original_handler is None:
            jq._handlers.pop(handler_name, None)
        else:
            register_handler(handler_name, original_handler)
        assert handler_stopped, "dispatched handler did not stop"


# ---------------------------------------------------------------------------
# Handler outcomes — driven synchronously through _execute_job, no worker thread
# ---------------------------------------------------------------------------

def _claimed_job(db, job_type: str, *, rec_status: str = "running_colmap"):
    """A reconstruction row plus a queue entry the drain loop has already claimed."""
    from backend.services import job_queue as jq

    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status=rec_status, frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    entry = enqueue(job_type, rec.id)
    assert jq._claim_pending(db, entry.id, datetime.now(UTC)) is True
    return rec, entry


def _execute_with_handler(job_type: str, handler, entry, rec) -> None:
    from backend.services import job_queue as jq

    orig = jq._handlers.get(job_type)
    jq.register_handler(job_type, handler)
    try:
        jq._execute_job(entry.id, job_type, rec.id, None, threading.Event())
    finally:
        if orig is None:
            jq._handlers.pop(job_type, None)
        else:
            jq.register_handler(job_type, orig)


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
    assert "nonexistent_handler" not in jq._handlers

    jq._execute_job(entry.id, "nonexistent_handler", rec.id, None, threading.Event())

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).one()
    assert stored.status == "failed"
    assert stored.error_msg == "No handler for nonexistent_handler"
    assert stored.completed_at is not None
    db.refresh(rec)
    assert rec.status == "pending", "non-reconstruction jobs must not alter the target"


def test_handler_that_raises_marks_entry_and_reconstruction_failed(setup_test_db):
    from backend.main import app

    db = app.state.test_db_session
    rec, entry = _claimed_job(db, RECONSTRUCTION)

    def boom(e, db_session, cancel):
        raise ValueError("feature extraction exploded")

    _execute_with_handler(RECONSTRUCTION, boom, entry, rec)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).one()
    assert stored.status == "failed"
    assert stored.error_msg == "feature extraction exploded"
    db.refresh(rec)
    assert rec.status == "failed"
    assert rec.error_msg == "feature extraction exploded"


@pytest.mark.parametrize(
    ("job_type", "rec_status", "expected_rec_status"),
    [
        # A live reconstruction is terminalized with the same reason as its entry.
        (RECONSTRUCTION, "running_colmap", "failed"),
        # Other job types only point at the reconstruction; it must not be touched.
        (MESH_EXPORT, "complete", "complete"),
    ],
)
def test_handler_that_returns_early_marks_entry_failed_with_reason(
    setup_test_db, job_type, rec_status, expected_rec_status
):
    from backend.main import app

    db = app.state.test_db_session
    rec, entry = _claimed_job(db, job_type, rec_status=rec_status)

    def returns_early(e, db_session, cancel):
        return  # e.g. "if rec is None: return" — neither mark_complete nor a raise

    _execute_with_handler(job_type, returns_early, entry, rec)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).one()
    assert stored.status == "failed", "a handler that returns must not leave a phantom 'running'"
    assert "without reaching a terminal state" in (stored.error_msg or "")
    assert stored.completed_at is not None
    db.refresh(rec)
    assert rec.status == expected_rec_status
    if expected_rec_status == "failed":
        assert rec.error_msg == stored.error_msg


@pytest.mark.parametrize(
    ("finish", "expected"),
    [("complete", "completed"), ("cancel", "cancelled")],
)
def test_handler_terminal_state_is_kept_after_it_returns(setup_test_db, finish, expected):
    from backend.main import app

    db = app.state.test_db_session
    rec, entry = _claimed_job(db, RECONSTRUCTION)

    def finishes(e, db_session, cancel):
        if finish == "complete":
            mark_complete(e.id)
        else:
            cancel_job(e.id)

    _execute_with_handler(RECONSTRUCTION, finishes, entry, rec)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).one()
    assert stored.status == expected
    assert stored.error_msg is None


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------

def test_gpu_concurrency_is_honored(setup_test_db):
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)

    release = threading.Event()
    begun = threading.Event()
    handler_thread = []
    original_handler = jq._handlers.get(RECONSTRUCTION)

    def slow_handler(entry, db_session, cancel):
        handler_thread.append(threading.current_thread())
        begun.set()
        release.wait()

    entry_ids = []
    for _i in range(2):
        rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        entry_ids.append(enqueue(RECONSTRUCTION, rec.id).id)

    try:
        register_handler(RECONSTRUCTION, slow_handler)
        jq._shutdown.clear()
        start_worker()
        assert begun.wait(timeout=3), "GPU handler did not start"

        entries = (
            db.query(JobQueueEntry)
            .filter(JobQueueEntry.id.in_(entry_ids))
            .order_by(JobQueueEntry.id)
            .all()
        )
        statuses = {e.status for e in entries}
        assert "running" in statuses, f"Expected a running job, got {statuses}"
        assert "pending" in statuses, f"Expected a pending job, got {statuses}"
    finally:
        jq._shutdown.set()
        release.set()
        shutdown_worker(timeout=5.0)
        for thread in handler_thread:
            thread.join(timeout=5)
        handler_stopped = all(not thread.is_alive() for thread in handler_thread)
        if original_handler is None:
            jq._handlers.pop(RECONSTRUCTION, None)
        else:
            register_handler(RECONSTRUCTION, original_handler)
        assert handler_stopped, "GPU handler did not stop"
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
    errors: list[Exception] = []
    results_lock = threading.Lock()
    start = threading.Barrier(6)

    def racer():
        start.wait()
        deadline = time.monotonic() + 5
        # SQLite serialises writers; a loser may transiently see "database is
        # locked" before the winner commits, so retry until we get a verdict.
        while time.monotonic() < deadline:
            session = TestSessionLocal()
            try:
                won = jq._claim_pending(session, entry.id, now)
            except OperationalError as exc:
                session.rollback()
                if "locked" not in str(exc).lower():
                    with results_lock:
                        errors.append(exc)
                    return
                time.sleep(0.01)
                continue
            except Exception as exc:
                with results_lock:
                    errors.append(exc)
                return
            finally:
                session.close()
            with results_lock:
                results.append(won)
            return
        with results_lock:
            errors.append(TimeoutError("SQLite claim stayed locked past retry deadline"))

    threads = [threading.Thread(target=racer) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert all(not t.is_alive() for t in threads), "claim racers did not finish"
    assert not errors, f"claim racers failed: {errors}"
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
# _execute_job retry path — the only terminal transition that lacked a guard
# ---------------------------------------------------------------------------

def test_retry_does_not_resurrect_cancelled(setup_test_db):
    """A cancelled job whose handler raises a non-cancellation error stays cancelled.

    Regression for #630: the retry branch in ``_execute_job`` was the only
    terminal transition without a cancelled guard, so an OSError from
    ``_write_cancel_checkpoint`` flipped the row back to pending and re-ran a
    reconstruction the user had stopped.
    """
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id, max_attempts=2)
    # Claim it so the row is running with attempt=1 (the real mid-training state).
    assert jq._claim_pending(db, entry.id, datetime.now(UTC)) is True
    # User cancels mid-training; the checkpoint write then fails with an OSError.
    assert cancel_job(entry.id) is True

    def boom_handler(e, db_session, cancel):
        raise OSError("checkpoint PLY write failed")

    orig = jq._handlers.get(RECONSTRUCTION)
    jq.register_handler(RECONSTRUCTION, boom_handler)
    try:
        jq._execute_job(entry.id, RECONSTRUCTION, rec.id, None, threading.Event())
    finally:
        if orig is not None:
            jq.register_handler(RECONSTRUCTION, orig)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored.status == "cancelled", (
        f"a cancelled job must not be re-queued by the retry path, got {stored.status!r}"
    )


def test_retry_still_retries_non_cancelled(setup_test_db):
    """A non-cancelled job that fails below max_attempts is re-queued to pending."""
    from backend.main import app
    from backend.services import job_queue as jq

    db = app.state.test_db_session
    s = _make_session(db)
    rec = Reconstruction(session_id=s.id, preset="quick", status="pending", frames_used=1)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    entry = enqueue(RECONSTRUCTION, rec.id, max_attempts=2)
    assert jq._claim_pending(db, entry.id, datetime.now(UTC)) is True
    # Not cancelled — the row stays running.

    def boom_handler(e, db_session, cancel):
        raise OSError("transient failure")

    orig = jq._handlers.get(RECONSTRUCTION)
    jq.register_handler(RECONSTRUCTION, boom_handler)
    try:
        jq._execute_job(entry.id, RECONSTRUCTION, rec.id, None, threading.Event())
    finally:
        if orig is not None:
            jq.register_handler(RECONSTRUCTION, orig)

    stored = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry.id).first()
    assert stored.status == "pending", (
        f"a non-cancelled job below max_attempts must retry, got {stored.status!r}"
    )


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
