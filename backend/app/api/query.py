"""The backend's own chat engine (the Flowise agents do not use these)."""
from fastapi import APIRouter
from .. import session
from ..agent_router import build_meta as _meta
from ..agent_router import prepare as _prepare
from ..llm import generate_answer
from ..llm import stream_answer
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uuid

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    top_k: int | None = None
    session_id: str | None = None

@router.post("/api/query", include_in_schema=False)
def query(req: QueryRequest):
    sid = req.session_id or uuid.uuid4().hex[:12]
    history = session.get_history(sid)
    hits, analysis, grounded = _prepare(req.question, req.top_k, history)

    result = generate_answer(req.question, hits, analysis, history)
    session.append(sid, "user", req.question)
    session.append(sid, "assistant", result["answer"])
    return {**_meta(req.question, sid, hits, analysis, grounded), **result}

@router.post("/api/query/stream", include_in_schema=False)
def query_stream(req: QueryRequest):
    """Same pipeline, but streams the answer token-by-token (Server-Sent Events).
    Emits {type:'token',v:...} chunks, then a {type:'done', payload:{...}} event
    with the full analysis/sources/flags once generation finishes."""
    sid = req.session_id or uuid.uuid4().hex[:12]
    history = session.get_history(sid)
    hits, analysis, grounded = _prepare(req.question, req.top_k, history)
    meta = _meta(req.question, sid, hits, analysis, grounded)

    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def gen():
        final = {"answer": ""}
        for ev in stream_answer(req.question, hits, analysis, history):
            if ev["type"] == "token":
                yield sse(ev)
            else:                                   # type == "final"
                final = {k: v for k, v in ev.items() if k != "type"}
        session.append(sid, "user", req.question)
        session.append(sid, "assistant", final.get("answer", ""))
        yield sse({"type": "done", "payload": {**meta, **final}})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no",
                                      "Cache-Control": "no-cache"})
