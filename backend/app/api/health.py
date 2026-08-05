"""Liveness and index size."""
from fastapi import APIRouter
from .. import config
from .. import session
from ..store import get_collection

router = APIRouter()


@router.get("/api/health")
def health():
    try:
        count = get_collection().count()
    except Exception:
        count = 0
    return {
        "status": "ok",
        "documents_indexed": count,
        "llm_model": config.OLLAMA_MODEL,
        "ollama_host": config.OLLAMA_HOST,
        "memory": session.backend(),
    }
