"""Engineering job history — the Package Center's read side.

The same persisted jobs the admin console shows, at ENGINEER level, because
producing specifications, drawings and packages is what an engineer does and
their own history should not require an administrator.

This is a read-only view. Nothing here creates, mutates or deletes a job — jobs
are written by the engines that produce the documents, and are permanent.

Scope note: every signed-in engineer sees every job. That matches the security
matrix's existing position — the offer corpus, which carries client names and
prices, is already engineer-level — and the single-tenant decision that one
company's engineers share one workspace. Per-record ownership was explicitly
deferred past 1.0.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from ..observability import artifacts as obs_artifacts, jobs as obs_jobs

router = APIRouter()

_MEDIA = {
    "pdf": "application/pdf",
    "svg": "image/svg+xml",
    "zip": "application/zip",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
    "dxf": "application/dxf",
}


@router.get("/api/jobs")
def list_jobs(limit: int = 100, kind: str = "", status: str = "",
              equipment: str = "", actor: str = ""):
    """Job history, newest first. Filterable by kind, status, equipment and author."""
    return {"ok": True, "jobs": obs_jobs.listing(
        limit=limit, kind=kind, status=status, equipment=equipment, actor=actor)}


@router.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    """One job: its requirement, engineering outcome and stored artifacts."""
    job = obs_jobs.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "no such job"}, status_code=404)
    return {"ok": True, "job": job}


@router.get("/api/jobs/{job_id}/artifact/{name}")
def job_artifact(job_id: str, name: str):
    """Download a stored artifact.

    The checksum is verified before the bytes are served: a file that no longer
    matches its digest is not the document that was issued, so it is reported
    missing rather than handed over as though it were.
    """
    found = obs_artifacts.read(job_id, name)
    if not found:
        return JSONResponse(
            {"ok": False,
             "error": "Artifact not found, or its checksum no longer matches."},
            status_code=404)
    data, row = found
    return Response(
        content=data,
        media_type=_MEDIA.get(row.get("kind"), "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{row["name"]}"',
                 "X-Checksum-SHA256": row.get("sha256") or ""})
