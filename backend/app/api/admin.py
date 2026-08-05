"""Administrative operations."""
from fastapi import APIRouter

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
