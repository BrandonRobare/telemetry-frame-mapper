"""Persistent SQLite-backed job queue for resource-heavy async work.

Replaces thread-per-job spawning with a durable queue that survives API
restarts.  A single background worker thread drains the queue, enforcing
GPU and concurrency caps so that only one heavy job runs at a time.

Jobs for different types (reconstruction, mesh, flythrough, comparison)
can run concurrently if they don't contend for the same resource, but the
default cap is 1 for GPU-bound work.  Failed jobs are retried up to
configured max_attempts.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from backend.db.database import SessionLocal
from backend.db.models import JobQueueEntry

logger = logging.getLogger(__name__)

# Job types — dispatch keys that map to handler functions.
RECONSTRUCTION = "reconstruction"
MESH_EXPORT = "mesh_export"
FLYTHROUGH_RENDER = "flythrough_render"
SESSION_COMPARISON = "session_comparison"

_RUNNING_JOBS: set[int] = set()
_RUNNING_LOCK = threading.Lock()

# Callback registry: job_type → handler(job_entry, db_session)
_handlers: dict[str, Callable] = {}

# Worker control
_worker: threading.Thread | None = None
_cancel_events: dict[int, threading.Event] = {}
_shutdown = threading.Event()
_lock_fh = None  # OS file lock guaranteeing a single drain worker across processes

# Configurable caps
_max_concurrent_gpu: int = 1  # Only one GPU job at a time


class JobNonRetryableError(RuntimeError):
    """A handler failure that should be recorded without re-queuing the job."""


def register_handler(job_type: str, handler: Callable) -> None:
    """Register a callable to execute when a job of ``job_type`` is drained.

    Signature: handler(job_entry: JobQueueEntry, db: Session) -> None
    The handler must set the target entity's status and mark the job
    completed/failed before returning.
    """
    _handlers[job_type] = handler


def enqueue(
    job_type: str,
    target_id: int,
    *,
    payload: dict | None = None,
    priority: int = 0,
    max_attempts: int = 1,
) -> JobQueueEntry:
    """Persist a job to the queue so it survives restarts."""
    db = _make_session()
    try:
        entry = JobQueueEntry(
            job_type=job_type,
            target_id=target_id,
            status="pending",
            priority=priority,
            payload_json=json.dumps(payload) if payload else None,
            max_attempts=max_attempts,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    finally:
        db.close()


def list_jobs(
    *,
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    job_type: str | None = None,
) -> list[dict]:
    """Return lightweight serializable job summaries."""
    db = _make_session()
    try:
        query = db.query(JobQueueEntry)
        if status is not None:
            query = query.filter(JobQueueEntry.status == status)
        if job_type is not None:
            query = query.filter(JobQueueEntry.job_type == job_type)
        entries = (
            query.order_by(JobQueueEntry.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [_serialize(e) for e in entries]
    finally:
        db.close()


def get_job(job_id: int) -> dict | None:
    """Get a single job by ID."""
    db = _make_session()
    try:
        entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == job_id).first()
        return _serialize(entry) if entry else None
    finally:
        db.close()


def cancel_job(job_id: int) -> bool:
    """Set a cancel event and mark a job cancelled in the DB.

    Returns True if the job was found and cancellable, False otherwise.
    """
    event = _cancel_events.get(job_id)
    if event:
        event.set()

    db = _make_session()
    try:
        entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == job_id).first()
        if entry is None:
            return False
        if entry.status not in ("pending", "running"):
            return False
        entry.status = "cancelled"
        entry.completed_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def _serialize(entry: JobQueueEntry) -> dict:
    payload = json.loads(entry.payload_json) if entry.payload_json else {}
    return {
        "id": entry.id,
        "job_type": entry.job_type,
        "target_id": entry.target_id,
        "status": entry.status,
        "priority": entry.priority,
        "error_msg": entry.error_msg,
        "attempt": entry.attempt,
        "max_attempts": entry.max_attempts,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
        "remote_job_id": payload.get("remote_job_id"),
    }


def update_payload(job_id: int, **values: object) -> None:
    """Merge durable handler metadata into a job payload without adding schema columns."""
    db = _make_session()
    try:
        entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == job_id).first()
        if entry is None:
            return
        payload = json.loads(entry.payload_json) if entry.payload_json else {}
        payload.update(values)
        entry.payload_json = json.dumps(payload)
        db.commit()
    finally:
        db.close()


def _lock_path() -> Path:
    """Lockfile beside the SQLite DB so every process coordinates on the same file."""
    from backend.db.database import REPO_ROOT, engine

    db_file = engine.url.database
    if db_file and db_file != ":memory:":
        base = Path(db_file).resolve().parent
    else:
        base = REPO_ROOT / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "jobq-worker.lock"


def _acquire_worker_lock() -> bool:
    """Take an exclusive OS lock so only one process drains the queue.

    The OS drops the lock when the holder exits or crashes, so there is no
    stale-lock handling.  Returns True on success, False if another process
    already holds it.
    """
    global _lock_fh
    if _lock_fh is not None:
        return True
    fh = open(_lock_path(), "a+")
    try:
        fh.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _lock_fh = fh
    return True


def _release_worker_lock() -> None:
    global _lock_fh
    if _lock_fh is None:
        return
    try:
        _lock_fh.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        _lock_fh.close()
        _lock_fh = None


def start_worker() -> None:
    """Launch the background drain loop (idempotent).

    Only the process that wins the OS drain lock runs a worker (and the
    startup reaper); others keep serving requests while the lock holder
    executes jobs.
    """
    # ponytail: single drain-worker via OS file lock — revisit if true
    # multi-worker job execution is ever needed
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    if not _acquire_worker_lock():
        logger.warning(
            "JobQueue: drain-worker lock held by another process; not starting a "
            "worker here (jobs run in the lock-holding process)."
        )
        return
    reaped = claim_stale_jobs()
    if reaped:
        logger.info("JobQueue: recovered %d orphaned running jobs on startup", reaped)
    _shutdown.clear()
    _worker = threading.Thread(target=_drain_loop, daemon=True, name="jobq-worker")
    _worker.start()


def shutdown_worker(timeout: float = 5.0) -> None:
    """Signal the worker to stop, wait for it, and release the drain lock."""
    _shutdown.set()
    if _worker is not None and _worker.is_alive():
        _worker.join(timeout=timeout)
    _release_worker_lock()


def claim_stale_jobs() -> int:
    """Recover jobs left 'running' by a previous process (startup, lock holder only).

    A local job is truly dead — its worker thread died with the process — so it
    is marked failed.  A reconstruction job whose target is ``running_remote`` is
    NOT dead: the remote worker keeps computing.  Such rows are reset to
    ``pending`` WITHOUT touching ``attempt`` so the drain loop re-dispatches and
    the existing ``remote_job_id`` short-circuit resumes polling instead of
    restarting the reconstruction.  Returns the number of rows acted on.
    """
    from backend.db.models import Reconstruction

    db = _make_session()
    try:
        now = datetime.now(UTC)
        acted = 0
        for entry in db.query(JobQueueEntry).filter(JobQueueEntry.status == "running").all():
            remote_alive = False
            if entry.job_type == RECONSTRUCTION:
                rec = (
                    db.query(Reconstruction)
                    .filter(Reconstruction.id == entry.target_id)
                    .first()
                )
                remote_alive = rec is not None and rec.status == "running_remote"
            if remote_alive:
                entry.status = "pending"
                entry.started_at = None
                entry.error_msg = None
            else:
                entry.status = "failed"
                entry.error_msg = "Worker restart — job was orphaned by previous shutdown"
                entry.completed_at = now
            acted += 1
        db.commit()
        return acted
    finally:
        db.close()


# Module-level session factory — tests can override to point at the test DB.
_make_session = SessionLocal


def _set_session_factory(factory) -> None:
    """Replace the session factory (for test injection)."""
    global _make_session
    _make_session = factory


def _claim_pending(db, entry_id: int, now: datetime) -> bool:
    """Atomically move one pending row to running. True iff this caller won it."""
    rows = (
        db.query(JobQueueEntry)
        .filter(JobQueueEntry.id == entry_id, JobQueueEntry.status == "pending")
        .update(
            {
                "status": "running",
                "started_at": now,
                "attempt": JobQueueEntry.attempt + 1,
                "error_msg": None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return rows == 1


def _drain_loop() -> None:
    """Single background thread that polls the queue and dispatches jobs.

    Enforces concurrency limits:
    - max 1 GPU-bound job (reconstruction, mesh, flythrough) at a time.
    - Comparison jobs are CPU-bound and can run alongside GPU work.
    """
    GPU_TYPES = {RECONSTRUCTION, MESH_EXPORT, FLYTHROUGH_RENDER}

    while not _shutdown.is_set():
        # Drain any pending job whose type's slot is free
        dispatched = False

        db = _make_session()
        try:
            # Check current concurrency
            with _RUNNING_LOCK:
                running_gpu = any(
                    _job_type_for_id(eid, db) in GPU_TYPES
                    for eid in _RUNNING_JOBS
                )

            # Pick the highest-priority, oldest pending job
            query = db.query(JobQueueEntry).filter(
                JobQueueEntry.status == "pending"
            ).order_by(
                JobQueueEntry.priority.desc(),
                JobQueueEntry.created_at.asc(),
            )

            for entry in query.all():
                is_gpu = entry.job_type in GPU_TYPES
                if is_gpu and running_gpu:
                    continue  # GPU slot occupied — skip for now

                if entry.job_type not in _handlers:
                    logger.warning("No handler registered for job_type=%s", entry.job_type)
                    entry.status = "failed"
                    entry.error_msg = f"No handler for {entry.job_type}"
                    entry.completed_at = datetime.now(UTC)
                    db.commit()
                    continue

                # Atomic claim: flip pending→running in one conditional UPDATE so
                # two drainers can never both grab the same row (double dispatch).
                if not _claim_pending(db, entry.id, datetime.now(UTC)):
                    continue  # Lost the race — another claim won this row.
                db.refresh(entry)

                with _RUNNING_LOCK:
                    _RUNNING_JOBS.add(entry.id)
                if is_gpu:
                    running_gpu = True

                # Dispatch in a daemon thread so the drain loop picks up
                # the next job if a non-GPU slot is free.
                cancel = threading.Event()
                _cancel_events[entry.id] = cancel
                t = threading.Thread(
                    target=_execute_job,
                    args=(entry.id, entry.job_type, entry.target_id, entry.payload_json, cancel),
                    daemon=True,
                    name=f"jobq-{entry.id}",
                )
                t.start()
                dispatched = True
                break  # One per loop iteration; pick next on next pass

        except Exception:
            logger.exception("JobQueue drain loop error")
        finally:
            db.close()

        if not dispatched:
            _shutdown.wait(timeout=0.5)


def _job_type_for_id(entry_id: int, db) -> str | None:
    entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == entry_id).first()
    return entry.job_type if entry else None


def _execute_job(
    job_id: int,
    job_type: str,
    target_id: int,
    payload_json: str | None,
    cancel: threading.Event,
) -> None:
    handler = _handlers.get(job_type)
    if handler is None:
        _mark_failed(job_id, f"No handler for {job_type}")
        return

    db = _make_session()
    try:
        entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == job_id).first()
        if entry is None:
            return
        handler(entry, db, cancel)
    except JobNonRetryableError as exc:
        _mark_failed(job_id, str(exc)[:5000], db=db)
    except Exception as exc:
        # The handler's session may hold an aborted transaction — roll it back
        # and close it before rebinding, or SQLite keeps the write lock and the
        # retry hits "database is locked".
        try:
            db.rollback()
        finally:
            db.close()
        db = _make_session()
        try:
            entry = db.query(JobQueueEntry).filter(JobQueueEntry.id == job_id).first()
            if entry is None:
                return
            if entry.attempt < entry.max_attempts:
                # Re-queue for retry
                entry.status = "pending"
                entry.error_msg = str(exc)[:5000]
                db.commit()
            else:
                _mark_failed(job_id, str(exc)[:5000], db=db)
        except Exception:
            logger.exception("Error handling job %s failure", job_id)
        finally:
            db.close()
    finally:
        _cancel_events.pop(job_id, None)
        with _RUNNING_LOCK:
            _RUNNING_JOBS.discard(job_id)
        try:
            db.close()
        except Exception:
            pass


def _mark_failed(job_id: int, error: str, *, db=None) -> None:
    own_db = db is None
    if own_db:
        db = _make_session()
    try:
        db.query(JobQueueEntry).filter(
            JobQueueEntry.id == job_id, JobQueueEntry.status != "cancelled"
        ).update({
            "status": "failed",
            "error_msg": error,
            "completed_at": datetime.now(UTC),
        })
        db.commit()
    finally:
        if own_db:
            db.close()


def mark_complete(job_id: int) -> None:
    """Mark a job as successfully completed."""
    db = _make_session()
    try:
        db.query(JobQueueEntry).filter(
            JobQueueEntry.id == job_id, JobQueueEntry.status != "cancelled"
        ).update({
            "status": "completed",
            "completed_at": datetime.now(UTC),
        })
        db.commit()
    finally:
        db.close()
