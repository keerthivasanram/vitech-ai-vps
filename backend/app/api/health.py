"""Liveness.

The public response is deliberately almost empty. It used to return the LLM
model, the Ollama host URL and the indexed-document count — a free reconnaissance
report for anyone who could reach the port, naming the internal services worth
attacking and how much data was worth taking. A probe needs to know the process
is answering; it does not need any of that.

The detailed diagnostics moved to `GET /api/admin/health/detail`, behind the
administrator role.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """Public liveness. Status only — no infrastructure details."""
    return {"status": "ok"}
