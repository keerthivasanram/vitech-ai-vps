"""Rate and concurrency limits for the expensive routes.

WHAT THIS PROTECTS, and what it deliberately does not.

The production-readiness review recorded two findings that share one cause —
the LLM routes were reachable with no ceiling of any kind:

  S5  `/api/query` and `/api/tools/*` run the model with no throttle. On a GPU
      box that is an unbounded compute-cost and denial-of-service surface: a
      loop saturates Ollama and every other user stalls behind it.
  P2  34 of 36 endpoints are sync, so they run in FastAPI's ~40-thread pool.
      With ~10 s LLM calls, roughly 40 concurrent requests exhaust it and the
      WHOLE API stalls — **including `/api/health`**, which is also what a
      monitor polls. The platform then looks dead rather than busy.

So there are two different ceilings here, because they are two different
failures:

  * a RATE limit stops one caller looping — the cost and DoS surface;
  * a CONCURRENCY limit stops many callers arriving at once from consuming
    every thread in the pool, which is what takes `/api/health` down with it.

THE RULE THAT SHAPES THE DEFAULTS: this must never throttle real engineering.
An engineer generating a package, or three agents answering a chat, must not
meet a 429. The limits are therefore set well above any plausible human or
agent workload — they are runaway guards, not quotas. A caller who trips one is
looping, not working.

`/api/health` is NEVER limited. That is the point of P2: the probe has to stay
answerable precisely when everything else is saturated.

SCOPE, stated honestly: the counters are IN-PROCESS. With the single uvicorn
worker this platform runs, that is exact. Behind multiple workers each would
hold its own budget, so the effective limit multiplies by the worker count —
raise nothing and assume less protection, or move the counters to Redis (which
is already a dependency) if the deployment ever grows workers.
"""
import re
import threading
import time
from collections import deque

from . import config

# The expensive surface: anything that can reach the LLM, run a full
# resolution, or do heavy vector/image work. Listed explicitly rather than
# inferred, so adding a cheap route never silently acquires a limit and adding
# an expensive one is a deliberate line in this file.
_EXPENSIVE = re.compile(
    r"^/api/("
    r"query"                       # the legacy chat engine (LLM)
    r"|tools/"                     # every agent tool: spec, quote, drawing, ...
    r"|package"                    # the heaviest: spec + drawing + quote + retrieval
    r"|bom"
    r"|siting/"                    # homography + image work
    r"|drawing/(render|export|from-spec)"
    r"|(specification|quotation|datasheet)/pdf"
    r")")


class _Bucket:
    """A sliding window of request timestamps for one principal."""

    __slots__ = ("hits",)

    def __init__(self) -> None:
        self.hits: deque = deque()


_lock = threading.Lock()
_buckets: dict[str, _Bucket] = {}
_in_flight = 0
_rejected_rate = 0
_rejected_concurrency = 0


def is_expensive(path: str) -> bool:
    return bool(_EXPENSIVE.match(path))


def _key(principal) -> str:
    """Limit per PRINCIPAL, not per IP.

    Every expensive route is authenticated, and the agents all reach the
    backend from localhost — so an IP-based limit would put three chatflows and
    any engineer on the same machine into one bucket, throttling legitimate
    work while doing nothing about a credentialed loop.
    """
    kind = getattr(principal, "kind", "anon") or "anon"
    name = getattr(principal, "name", "") or "-"
    return f"{kind}:{name}"


def check(principal, path: str) -> tuple[bool, str, int]:
    """(allowed, reason, retry_after_seconds) for an expensive request.

    Never raises: a limiter that can 500 is worse than no limiter, because it
    would take out the engineering routes it exists to protect.
    """
    global _rejected_rate
    if not config.RATE_LIMIT_ENABLED or not is_expensive(path):
        return True, "", 0
    try:
        limit = config.RATE_LIMIT_PER_MINUTE
        now = time.monotonic()
        with _lock:
            bucket = _buckets.get(_key(principal))
            if bucket is None:
                bucket = _buckets[_key(principal)] = _Bucket()
            hits = bucket.hits
            while hits and now - hits[0] > 60.0:
                hits.popleft()
            if len(hits) >= limit:
                _rejected_rate += 1
                retry = max(1, int(60.0 - (now - hits[0])) + 1)
                return False, f"{len(hits)} requests in the last minute (limit {limit})", retry
            hits.append(now)
        return True, "", 0
    except Exception:
        return True, "", 0


class slot:
    """Context manager holding one of the concurrent expensive-request slots.

    `acquired` is False ONLY when an expensive route found the platform at its
    ceiling. The caller turns that into a 429 with Retry-After rather than
    queueing, because queueing inside the request is precisely what exhausts
    the thread pool.

    IT MUST BE GIVEN THE PATH. An earlier version took no argument and so
    counted every request, cheap ones included — which would have put
    `/api/health` behind the same ceiling as a package build and 429'd the
    monitor under load. That is the exact failure P2 describes, reintroduced by
    the guard meant to prevent it. Caught by reading `in_flight` in the metrics
    while only cheap requests were in flight, not by reading this code.
    """

    __slots__ = ("acquired", "counted", "path")

    def __init__(self, path: str = "") -> None:
        self.acquired = False
        self.counted = False
        self.path = path

    def __enter__(self) -> "slot":
        global _in_flight, _rejected_concurrency
        # A cheap route never takes a slot and is never refused one.
        if not config.RATE_LIMIT_ENABLED or not is_expensive(self.path):
            self.acquired = True
            return self
        with _lock:
            if _in_flight >= config.MAX_CONCURRENT_EXPENSIVE:
                _rejected_concurrency += 1
                return self
            _in_flight += 1
            self.acquired = True
            self.counted = True
        return self

    def __exit__(self, *exc) -> None:
        global _in_flight
        if self.counted:
            with _lock:
                _in_flight = max(0, _in_flight - 1)
        return None


def stats() -> dict:
    """For `/api/admin/metrics` — a limit nobody can see is a limit nobody tunes."""
    with _lock:
        return {
            "enabled": config.RATE_LIMIT_ENABLED,
            "per_minute_per_principal": config.RATE_LIMIT_PER_MINUTE,
            "max_concurrent_expensive": config.MAX_CONCURRENT_EXPENSIVE,
            "in_flight": _in_flight,
            "tracked_principals": len(_buckets),
            "rejected_rate": _rejected_rate,
            "rejected_concurrency": _rejected_concurrency,
            "note": "counters are per-process; exact for the single worker this runs",
        }


def reset() -> None:
    """Test hook. Never called by application code."""
    global _in_flight, _rejected_rate, _rejected_concurrency
    with _lock:
        _buckets.clear()
        _in_flight = 0
        _rejected_rate = 0
        _rejected_concurrency = 0
