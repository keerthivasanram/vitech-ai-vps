"""Compatibility shim — the job model now lives in `observability/jobs.py`.

This module used to hold jobs in an in-process dict, so every job vanished on
restart: an ingest that ran overnight left no evidence it had happened, and no
specification, drawing or quotation was recorded at all. Jobs are now rows in
`data/ops.db` and are permanent.

The old `create_job` / `update` / `get` / `run` names are kept so the existing
call sites are unchanged, the same way `rules.py` shims `formula_service`.
"""
from .observability import jobs as _jobs
from .observability.store import upsert_job as _upsert


def create_job() -> str:
    """Open an ingest job. Returns the job id."""
    return _jobs.create("ingest", status=_jobs.QUEUED)


def update(job_id: str, **fields) -> None:
    """Patch a job. The old field names map onto the persistent schema."""
    patch = {"job_id": job_id}
    for key, value in fields.items():
        if key == "status":
            patch["status"] = {"done": _jobs.SUCCEEDED,
                               "error": _jobs.FAILED}.get(value, value)
        elif key in ("processed", "finished_at", "started_at", "error"):
            patch[key] = value
        # `traceback` is deliberately dropped: it belongs in the structured log,
        # not in a column the job list renders.
    _upsert(patch)


def get(job_id: str):
    return _jobs.get(job_id)


def run(job_id: str, work) -> None:
    _jobs.run(job_id, work)
