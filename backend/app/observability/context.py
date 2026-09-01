"""Per-request state, carried without touching a single function signature.

`contextvars` is the reason Phase C is additive: the retrieval layer can record
how many offers it returned without `retrieve()` gaining a `request_id`
parameter, and the engineering functions stay exactly as the golden tests found
them.

Context is per-task and per-thread, which is what FastAPI needs — sync endpoints
run in a thread pool, and each gets its own copy.
"""
import secrets
import time
from contextvars import ContextVar
from typing import Any, Optional

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_actor: ContextVar[str] = ContextVar("actor", default="")
_actor_kind: ContextVar[str] = ContextVar("actor_kind", default="")
_role: ContextVar[str] = ContextVar("role", default="")
# Facts the engineering layers discover as they run, collected for the request
# summary row: equipment, retrieval count, rules applied, warnings, latencies.
_facts: ContextVar[Optional[dict]] = ContextVar("facts", default=None)


def new_request_id() -> str:
    """Time-sortable, unique, and short enough to paste into a support ticket.

    Sortable matters: `ORDER BY request_id` is chronological, so the trace list
    needs no extra index to read newest-first.
    """
    return f"{int(time.time() * 1000):011x}{secrets.token_hex(6)}"


def begin(request_id: str, *, actor: str = "", actor_kind: str = "",
          role: str = "") -> None:
    _request_id.set(request_id)
    _actor.set(actor)
    _actor_kind.set(actor_kind)
    _role.set(role)
    _facts.set({"retrieval_count": 0, "rule_count": 0, "warning_count": 0,
                "llm_ms": 0, "retrieval_ms": 0, "spans": 0, "seq": 0})


def identify(actor_name: str, kind: str, user_role: str = "") -> None:
    """Attach the principal once authentication has resolved it.

    The trace middleware runs OUTSIDE the auth middleware so it can time the
    whole request including the authorization decision — which means the
    principal does not exist yet when `begin()` runs. Without this the actor
    column was empty on every trace, and "who ran this?" is most of the value of
    having traces at all.
    """
    _actor.set(actor_name or "")
    _actor_kind.set(kind or "anonymous")
    _role.set(user_role or "")
    # ALSO written into the fact bag, and that is not redundant. Starlette's
    # BaseHTTPMiddleware runs the downstream app in a separate task, so a
    # ContextVar REBOUND inside `call_next` is invisible to the middleware that
    # wrapped it — the identity was reaching the job record and never the
    # request row. The fact bag is a mutable dict shared by reference, so
    # mutating it crosses the task boundary where `.set()` does not.
    facts().update({"actor": actor_name or "", "actor_kind": kind or "anonymous",
                    "role": user_role or ""})


def request_id() -> str:
    return _request_id.get()


def actor() -> str:
    return _actor.get()


def actor_kind() -> str:
    return _actor_kind.get()


def role() -> str:
    return _role.get()


def facts() -> dict:
    """The mutable per-request fact bag. Always a dict, even outside a request,
    so instrumentation never has to guard against being called from a script."""
    f = _facts.get()
    if f is None:
        f = {"retrieval_count": 0, "rule_count": 0, "warning_count": 0,
             "llm_ms": 0, "retrieval_ms": 0, "spans": 0, "seq": 0}
        _facts.set(f)
    return f


def record(**kwargs: Any) -> None:
    """Set facts about this request (equipment, agent, tool, job id)."""
    facts().update(kwargs)


def add(key: str, amount: int = 1) -> None:
    """Accumulate a counter (retrieval hits, rules applied, milliseconds)."""
    f = facts()
    f[key] = int(f.get(key) or 0) + amount


def next_seq() -> int:
    """Monotonic span ordering within the request."""
    f = facts()
    f["seq"] = int(f.get("seq") or 0) + 1
    return f["seq"]
