"""Tiny in-process background job manager.

This is the prototype-grade job queue: it runs ingestion in a background
thread so the API returns immediately and the client can poll progress. It
proves the async/batched architecture.

For production, swap the `run` function for a Celery/RQ task (needs Redis) —
the ingest_source() call inside stays identical. Nothing else changes.
"""
import threading
import time
import traceback
import uuid
from typing import Any, Callable

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def create_job() -> str:
    job_id = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "processed": 0,
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
        }
    return job_id


def update(job_id: str, **fields: Any) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job = dict(job)
    if job["finished_at"]:
        job["elapsed_s"] = round(job["finished_at"] - job["started_at"], 2)
    else:
        job["elapsed_s"] = round(time.time() - job["started_at"], 2)
    return job


def run(job_id: str, work: Callable[[Callable[[int], None]], int]) -> None:
    """Run `work(progress)` in a daemon thread. `work` reports count via
    the progress callback and returns the final total."""

    def task() -> None:
        update(job_id, status="running")
        try:
            def progress(done: int) -> None:
                update(job_id, processed=done)

            total = work(progress)
            update(job_id, status="done", processed=total,
                   finished_at=time.time())
        except Exception as exc:  # surface the real error to the client
            update(job_id, status="error", error=str(exc),
                   traceback=traceback.format_exc(), finished_at=time.time())

    threading.Thread(target=task, daemon=True).start()
