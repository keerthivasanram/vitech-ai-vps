"""Per-request tracing: assign the id, time the request, record the summary.

THE CONSTRAINT THAT SHAPES THIS: the request id goes in the `X-Request-ID`
RESPONSE HEADER and never into a response body. `tests_api_contract.py`
fingerprints bodies, so putting the id in a payload would change all 28
fingerprints and destroy the evidence that Phase C changed nothing.

An id supplied by the caller is honoured, so the frontend can correlate a failed
page with the server trace, but it is sanitised first — it ends up in a
database, a log file and a header.
"""
import re
import time

from . import context, logs, store, trace, writer

_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

# Paths whose traces would be pure noise. They are still logged on failure.
_QUIET = ("/api/health",)


def _incoming_id(request) -> str:
    supplied = (request.headers.get("x-request-id") or "").strip()
    return supplied if _ID_OK.match(supplied) else context.new_request_id()


async def trace_middleware(request, call_next):
    request_id = _incoming_id(request)
    principal = getattr(request.state, "principal", None)
    context.begin(
        request_id,
        actor=getattr(principal, "name", "") or "",
        actor_kind=getattr(principal, "kind", "") or "anonymous",
        role=getattr(principal, "role", "") or "",
    )

    path, method = request.url.path, request.method
    started = time.perf_counter()
    status, error = 500, ""
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:400]
        logs.error("request failed", exc=exc, path=path, method=method,
                   request_id=request_id)
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        quiet = path in _QUIET and status < 400 and not error
        if not quiet:
            f = context.facts()
            writer.submit("request", {
                "request_id": request_id,
                "at": time.time() - duration_ms / 1000.0,
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": duration_ms,
                "ok": 0 if (status >= 400 or error) else 1,
                # Read from the fact bag, not the ContextVars: see
                # `context.identify` for why a rebind does not reach here.
                "actor_kind": f.get("actor_kind") or context.actor_kind(),
                "actor": f.get("actor") or context.actor(),
                "role": f.get("role") or context.role(),
                "ip": (request.client.host if request.client else ""),
                "agent": f.get("agent"),
                "tool": f.get("tool"),
                "equipment": f.get("equipment"),
                "retrieval_count": int(f.get("retrieval_count") or 0),
                "rule_count": int(f.get("rule_count") or 0),
                "warning_count": int(f.get("warning_count") or 0),
                "llm_ms": int(f.get("llm_ms") or 0),
                "retrieval_ms": int(f.get("retrieval_ms") or 0),
                "error": error or None,
            })
            # The requirement text is deliberately NOT here — it lives on the
            # job record, behind a role. The request id is the join.
            logs.info("request", method=method, path=path, status=status,
                      ms=duration_ms, tool=f.get("tool"),
                      equipment=f.get("equipment"),
                      retrieval=f.get("retrieval_count"),
                      rules=f.get("rule_count"))

    response.headers["X-Request-ID"] = request_id
    # A job id also travels as a header, for the same reason: adding it to the
    # payload would change that endpoint's fingerprint.
    job_id = context.facts().get("job_id")
    if job_id:
        response.headers["X-Job-ID"] = str(job_id)
    return response


def reconstruct(request_id: str) -> dict:
    """The full execution path for one request — the trace viewer's answer.

    Joins the ops database to the audit trail in `auth.db` in PYTHON rather than
    coupling the two databases, so either can be purged, rotated or moved
    without the other noticing.
    """
    req = store.get_request(request_id)
    spans = store.request_spans(request_id)
    jobs = store.request_jobs(request_id)

    audit: list[dict] = []
    try:
        from ..auth import store as auth_store
        conn = auth_store.connect()
        audit = [dict(r) for r in conn.execute(
            "SELECT at, actor, actor_kind, role, action, status, detail"
            "  FROM vitech_audit WHERE detail LIKE ? OR action LIKE ?"
            " ORDER BY at LIMIT 50",
            (f"%{request_id}%", f"%{request_id}%")).fetchall()]
    except Exception:
        audit = []

    for job in jobs:
        job["artifacts"] = store.job_artifacts(job["job_id"])

    return {
        "request_id": request_id,
        "found": bool(req),
        "request": req,
        "spans": spans,
        "jobs": jobs,
        "audit": audit,
        "log_lines": logs.tail(100, request_id=request_id),
    }
