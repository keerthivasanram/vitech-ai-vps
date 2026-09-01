"""Chat session history for the backend's own chat engine."""
from fastapi import APIRouter
from .. import session

router = APIRouter()


@router.get("/api/session/{session_id}", include_in_schema=False)
def session_history(session_id: str):
    return {"session_id": session_id, "messages": session.get_history(session_id, 100)}


@router.delete("/api/session/{session_id}", include_in_schema=False)
def session_clear(session_id: str):
    session.clear(session_id)
    return {"cleared": session_id}
