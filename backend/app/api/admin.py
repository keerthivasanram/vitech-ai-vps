"""Administrative operations. Every route here is administrator-only, enforced
centrally by `auth/policy.py` rather than per-function."""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .. import config
from ..auth import store as auth_store

router = APIRouter()


@router.post("/api/admin/reload-index")
def admin_reload_index():
    """Refresh retrieval after an out-of-process ingest WITHOUT a full restart.

    ChromaDB embedded caches its query index per process, so documents added by
    the `rag.ingest` CLI aren't searchable by the running server until this is
    called (or the backend restarts). Clears the Chroma cache + the retrieval
    cache and reports the live document count. Guard with API_KEY in production.
    """
    from ..store import reload_collection
    from rag.cache import bump_version
    col = reload_collection()
    bump_version()
    total = col.count()
    docs = 0
    try:
        docs = len(col.get(where={"type": "document"}, include=[])["ids"])
    except Exception:
        pass
    return {"ok": True, "reloaded": True, "total_items": total, "documents": docs}


def _probe(fn) -> dict:
    """Run one service check, timed, never raising."""
    started = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as exc:
        detail, ok = f"{type(exc).__name__}: {exc}"[:200], False
    return {"ok": ok, "ms": round((time.perf_counter() - started) * 1000, 1),
            "detail": detail}


@router.get("/api/admin/health/detail")
def health_detail():
    """The diagnostics the public health endpoint no longer exposes.

    This is the panel that answers the most common failure in this platform:
    "the agent says it cannot call tools" almost always means the backend or
    Ollama is down, not that the model is misbehaving.
    """
    def _chroma():
        from ..store import get_collection
        return f"{get_collection().count()} items indexed"

    def _ollama():
        import httpx
        r = httpx.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5.0)
        r.raise_for_status()
        names = [m.get("name") for m in (r.json().get("models") or [])]
        return f"{len(names)} model(s): {', '.join(n for n in names if n)[:120]}"

    def _redis():
        from .. import session
        return f"session backend: {session.backend()}"

    def _auth():
        return (f"{auth_store.user_count()} user(s), "
                f"{len(auth_store.list_services())} service principal(s)")

    return {
        "status": "ok",
        "llm": {"model": config.OLLAMA_MODEL, "host": config.OLLAMA_HOST},
        # Which model writes the specification narrative. Everything else (chat,
        # lookups, the verify pass) is always the local model above; the numbers
        # in a spec are computed in Python regardless of what this says.
        "spec_llm": {
            "provider": config.spec_provider(),
            "configured": config.SPEC_LLM_PROVIDER,
            "model": (config.OPENAI_MODEL if config.spec_provider() == "openai"
                      else config.OLLAMA_MODEL),
            "api_key_set": bool(config.OPENAI_API_KEY),
        },
        "services": {
            "chromadb": _probe(_chroma),
            "ollama": _probe(_ollama),
            "session_store": _probe(_redis),
            "auth_db": _probe(_auth),
        },
    }


@router.get("/api/admin/audit")
def audit(limit: int = 200, actor: str = "", action: str = ""):
    """The audit trail: who did what, reads included."""
    return {"ok": True, "entries": auth_store.read_audit(limit, actor=actor, action=action)}


@router.get("/api/admin/principals")
def principals():
    """Accounts and service principals. Never any hash or key material."""
    return {"ok": True, "users": auth_store.list_users(),
            "services": auth_store.list_services()}


@router.get("/api/admin/policy")
def policy_matrix():
    """The live access-control policy, as the server actually enforces it."""
    from ..auth import policy as pol
    return {"ok": True, "rules": pol.describe()}


@router.post("/api/admin/sessions/purge")
def purge_sessions(request: Request):
    """Delete expired sessions."""
    removed = auth_store.purge_expired_sessions()
    return {"ok": True, "removed": removed}


# --- Developer operations ---------------------------------------------------
# Everything below is administrator-only, enforced centrally by `auth/policy.py`
# through the `^/api/admin/` rule — no per-route decision to forget.

@router.get("/api/admin/metrics")
def metrics(window_hours: int = 24):
    """Requests, latencies, failure rate, active principals, cache ratio."""
    from ..observability import metrics as obs_metrics
    return {"ok": True, **obs_metrics.summary(window_hours)}


@router.get("/api/admin/requests")
def requests_list(limit: int = 100, actor: str = "", tool: str = "",
                  equipment: str = "", failed_only: bool = False):
    """Recent engineering requests: the agent execution timeline."""
    from ..observability import store as obs_store
    return {"ok": True, "requests": obs_store.list_requests(
        limit=limit, actor=actor, tool=tool, equipment=equipment,
        failed_only=failed_only)}


@router.get("/api/admin/trace/{request_id}")
def trace_view(request_id: str):
    """Reconstruct one request end to end: requirement -> retrieval -> rules ->
    specification -> drawing -> BOM -> quotation -> package."""
    from ..observability.middleware import reconstruct
    return {"ok": True, **reconstruct(request_id)}


@router.get("/api/admin/jobs")
def jobs_list(limit: int = 100, kind: str = "", status: str = "",
              actor: str = "", equipment: str = ""):
    """Job history. Permanent — this is the engineering record."""
    from ..observability import jobs as obs_jobs
    return {"ok": True, "jobs": obs_jobs.listing(
        limit=limit, kind=kind, status=status, actor=actor, equipment=equipment)}


@router.get("/api/admin/jobs/{job_id}")
def job_detail(job_id: str):
    """One job, its requirement, its outcome and its stored artifacts."""
    from ..observability import artifacts as obs_artifacts, jobs as obs_jobs
    job = obs_jobs.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "no such job"}, status_code=404)
    job["artifact_integrity"] = obs_artifacts.verify(job_id)
    return {"ok": True, "job": job}


@router.get("/api/admin/jobs/{job_id}/artifact/{name}")
def job_artifact(job_id: str, name: str):
    """Download a stored artifact. The checksum is verified before it is served —
    a file that no longer matches its digest is not the document that was issued,
    so it is reported missing rather than handed over as though it were."""
    from ..observability import artifacts as obs_artifacts
    found = obs_artifacts.read(job_id, name)
    if not found:
        return JSONResponse(
            {"ok": False, "error": "artifact not found, or its checksum no longer matches"},
            status_code=404)
    data, row = found
    media = {"pdf": "application/pdf", "svg": "image/svg+xml", "zip": "application/zip",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "json": "application/json"}.get(row.get("kind"), "text/plain; charset=utf-8")
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{row["name"]}"',
        "X-Checksum-SHA256": row.get("sha256") or "",
    })


@router.get("/api/admin/logs")
def logs_tail(limit: int = 200, level: str = "", request_id: str = "",
              contains: str = ""):
    """Structured logs, newest first. Customer requirements never appear here —
    they live on the job record, behind a role."""
    from ..observability import logs as obs_logs
    return {"ok": True, "entries": obs_logs.tail(
        limit, level=level, request_id=request_id, contains=contains),
        "files": obs_logs.file_stats()}


@router.get("/api/admin/cache")
def cache_stats():
    """Retrieval cache statistics."""
    from ..observability import metrics as obs_metrics
    return {"ok": True, **obs_metrics.cache_stats()}


@router.post("/api/admin/retention/purge")
def retention_purge(days: int = 0):
    """Apply the retention policy to request traces.

    Jobs, artifacts and the audit trail are PERMANENT by decision and are never
    touched here.
    """
    from ..observability import store as obs_store
    result = obs_store.purge(days or obs_store.REQUEST_RETENTION_DAYS)
    return {"ok": True, **result,
            "note": "Jobs, artifacts and audit are permanent and were not touched."}
