"""Administrative operations. Every route here is administrator-only, enforced
centrally by `auth/policy.py` rather than per-function."""
import time

from fastapi import APIRouter, Request

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
