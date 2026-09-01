"""The single persistent job model.

Replaces the in-process dict in `app/jobs.py`, which lost every job on restart —
so an ingest that ran overnight left no evidence it had happened, and no
specification, drawing or quotation was recorded at all.

One job per engineering artifact generated (specification, drawing, BOM,
quotation, package) and per ingest run. Jobs are PERMANENT: they are the
engineering record, and unlike request traces they are never purged.

Jobs are written SYNCHRONOUSLY, not through the telemetry queue. A dropped span
costs a line in a trace; a dropped job would mean an engineering document exists
with no record of who produced it or when.
"""
import time
import traceback
from typing import Any, Callable, Optional

from . import artifacts, context, store

KINDS = ("specification", "drawing", "bom", "quotation", "package", "ingest")

QUEUED, RUNNING, SUCCEEDED, FAILED = "queued", "running", "succeeded", "failed"


def new_job_id(kind: str) -> str:
    return f"{kind[:4]}_{context.new_request_id()}"


def create(kind: str, *, requirement: str = "", equipment: str = "",
           project: str = "", client: str = "", revision: str = "0",
           status: str = RUNNING) -> str:
    """Open a job row. Returns the job id.

    `requirement` is the customer's own words, kept verbatim because it is what
    every later question about the document resolves against. It is readable
    only through the Engineer/Admin roles and is never written to a log.
    """
    job_id = new_job_id(kind)
    now = time.time()
    store.upsert_job({
        "job_id": job_id,
        "request_id": context.request_id(),
        "kind": kind,
        "status": status,
        "equipment": equipment,
        "requirement": requirement,
        "project": project,
        "client": client,
        "revision": str(revision),
        "actor": context.actor(),
        "actor_kind": context.actor_kind(),
        "created_at": now,
        "started_at": now,
    })
    return job_id


def finish(job_id: str, *, status: str = SUCCEEDED, equipment: str = "",
           confidence_pct: Optional[int] = None, release_status: str = "",
           warning_count: int = 0, tbd_count: int = 0, processed: int = 0,
           error: str = "", summary: Optional[dict] = None) -> None:
    """Close a job with its engineering outcome."""
    import json
    row = store.get_job(job_id) or {}
    started = row.get("started_at") or row.get("created_at") or time.time()
    now = time.time()
    patch: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "finished_at": now,
        "duration_ms": int((now - started) * 1000),
        "warning_count": warning_count,
        "tbd_count": tbd_count,
        "processed": processed,
    }
    if equipment:
        patch["equipment"] = equipment
    if confidence_pct is not None:
        patch["confidence_pct"] = confidence_pct
    if release_status:
        patch["release_status"] = release_status
    if error:
        patch["error"] = error[:2000]
    if summary is not None:
        patch["summary"] = json.dumps(summary, default=str)[:4000]
    store.upsert_job(patch)


def fail(job_id: str, exc: BaseException) -> None:
    finish(job_id, status=FAILED, error=f"{type(exc).__name__}: {exc}")


def get(job_id: str) -> Optional[dict]:
    """A job with its artifacts and elapsed time."""
    job = store.get_job(job_id)
    if not job:
        return None
    job["artifacts"] = store.job_artifacts(job_id)
    if job.get("finished_at"):
        job["elapsed_s"] = round(job["finished_at"] - (job.get("started_at") or 0), 2)
    else:
        job["elapsed_s"] = round(time.time() - (job.get("started_at") or time.time()), 2)
    return job


def listing(**kwargs) -> list[dict]:
    return store.list_jobs(**kwargs)


def attach(job_id: str, name: str, data: bytes, kind: str = "") -> dict:
    """Store a customer-facing artifact immutably against a job."""
    return artifacts.store_bytes(job_id, name, data, kind=kind)


# --- background work (the old jobs.run, now persistent) ---------------------

def run(job_id: str, work: Callable[[Callable[[int], None]], int]) -> None:
    """Run `work(progress)` in a daemon thread, recording progress on the job.

    The context is captured BEFORE the thread starts: `contextvars` are per-task,
    so a thread spawned from a request would otherwise lose the request id and
    the job would be orphaned from its trace.
    """
    request_id = context.request_id()
    actor, kind_ = context.actor(), context.actor_kind()

    def task() -> None:
        context.begin(request_id, actor=actor, actor_kind=kind_)
        store.upsert_job({"job_id": job_id, "status": RUNNING})
        try:
            def progress(done: int) -> None:
                store.upsert_job({"job_id": job_id, "processed": done})

            total = work(progress)
            finish(job_id, status=SUCCEEDED, processed=total)
        except Exception as exc:
            finish(job_id, status=FAILED, processed=0,
                   error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"[:2000])

    import threading
    threading.Thread(target=task, daemon=True).start()
