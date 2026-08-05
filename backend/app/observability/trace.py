"""Spans: the execution path inside one request.

Used as a context manager at the six instrumentation seams, which is ONE added
line each and no change to what any of them computes:

    with trace.span("retrieve.offers", "retrieval") as s:
        hits = ...
        s.detail(count=len(hits))

Outside a request (a golden test, a CLI) `request_id()` is empty and the span
becomes a no-op that still runs the body — so the engineering code paths behave
identically whether or not anything is watching. That property is what lets the
golden tests stay a valid check of the engine rather than of the tracing.
"""
import time
from typing import Any, Optional

from . import context, writer

# Spans are cheap, but a pathological loop should not fill the queue with a
# million rows for one request. Beyond this, the request is still recorded and
# the overflow is counted in the summary.
_MAX_SPANS_PER_REQUEST = 200


class Span:
    __slots__ = ("name", "kind", "_detail", "_started", "ok", "_live")

    def __init__(self, name: str, kind: str, live: bool):
        self.name = name
        self.kind = kind
        self._detail: dict[str, Any] = {}
        self._started = 0.0
        self.ok = True
        self._live = live

    def detail(self, **kwargs: Any) -> "Span":
        """Attach facts. Never customer requirement text — that belongs on the
        job record, behind a role, not in a trace that gets browsed."""
        if self._live:
            self._detail.update(kwargs)
        return self

    def __enter__(self) -> "Span":
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed_ms = int((time.perf_counter() - self._started) * 1000)
        if exc_type is not None:
            self.ok = False
            self._detail.setdefault("error", f"{exc_type.__name__}: {exc}"[:200])
        if self._live:
            # Roll the timings the request summary reports.
            if self.kind == "llm":
                context.add("llm_ms", elapsed_ms)
            elif self.kind == "retrieval":
                context.add("retrieval_ms", elapsed_ms)
            writer.submit("span", {
                "request_id": context.request_id(),
                "seq": context.next_seq(),
                "name": self.name,
                "kind": self.kind,
                "started_at": time.time() - elapsed_ms / 1000.0,
                "duration_ms": elapsed_ms,
                "ok": 1 if self.ok else 0,
                "detail": self._detail,
            })
        return False        # never swallow the exception


def span(name: str, kind: str = "step") -> Span:
    """Open a span. A no-op outside a request, but the body always runs."""
    live = bool(context.request_id())
    if live:
        facts = context.facts()
        n = int(facts.get("spans") or 0) + 1
        facts["spans"] = n
        if n > _MAX_SPANS_PER_REQUEST:
            live = False
    return Span(name, kind, live)


def note(**kwargs: Any) -> None:
    """Record a fact about the request itself (equipment, agent, tool)."""
    if context.request_id():
        context.record(**kwargs)


def count(key: str, amount: int = 1) -> None:
    """Accumulate one of the request summary counters."""
    if context.request_id():
        context.add(key, amount)
