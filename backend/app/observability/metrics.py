"""Metrics, computed from the request table rather than kept as counters.

One source of truth. A pre-aggregated rollup is faster but becomes a second
place for a number to live, and two places is how numbers drift. At this scale
the indexed queries are trivial; a rollup can be added if the request table ever
outgrows them.

The exception is the retrieval cache, which is in-process — so its counters are
in-process too, and reset on restart. Saying so in the response is the point:
a "94% hit rate" that silently means "since 06:12 this morning" is misleading.
"""
import time
from typing import Any

from . import logs, store, writer

# In-process counters. The cache they describe is in-process, so persisting
# these would describe a cache that no longer exists.
_cache = {"hits": 0, "misses": 0, "since": time.time()}


def cache_hit() -> None:
    _cache["hits"] += 1


def cache_miss() -> None:
    _cache["misses"] += 1


def cache_stats() -> dict:
    hits, misses = _cache["hits"], _cache["misses"]
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "lookups": total,
        "hit_ratio": round(hits / total, 4) if total else None,
        "since": _cache["since"],
        "note": ("In-process counters: the retrieval cache is per-process, so "
                 "these reset when the backend restarts."),
    }


def _percentile(values: list[int], pct: float):
    if not values:
        return None
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


def summary(window_hours: int = 24) -> dict[str, Any]:
    """Everything the metrics panel needs, for one time window."""
    since = time.time() - window_hours * 3600
    conn = store.connect()

    row = conn.execute(
        "SELECT count(*) n, sum(CASE WHEN ok=0 THEN 1 ELSE 0 END) failures,"
        "       avg(duration_ms) avg_ms, sum(llm_ms) llm_ms,"
        "       sum(retrieval_ms) retrieval_ms"
        "  FROM vitech_request WHERE at >= ?", (since,)).fetchone()
    n = int(row["n"] or 0)
    failures = int(row["failures"] or 0)

    durations = [int(r["duration_ms"] or 0) for r in conn.execute(
        "SELECT duration_ms FROM vitech_request WHERE at >= ? AND duration_ms IS NOT NULL",
        (since,)).fetchall()]

    def _latency(where: str, args: tuple) -> dict:
        vals = [int(r["duration_ms"] or 0) for r in conn.execute(
            f"SELECT duration_ms FROM vitech_span WHERE {where}", args).fetchall()]
        return {"count": len(vals),
                "avg_ms": round(sum(vals) / len(vals)) if vals else None,
                "p95_ms": _percentile(vals, 95)}

    package = [int(r["duration_ms"] or 0) for r in conn.execute(
        "SELECT duration_ms FROM vitech_request"
        " WHERE at >= ? AND path LIKE '/api/package%' AND duration_ms IS NOT NULL",
        (since,)).fetchall()]

    actors = conn.execute(
        "SELECT actor_kind, count(DISTINCT actor) n FROM vitech_request"
        " WHERE at >= ? AND actor != '' AND actor IS NOT NULL GROUP BY actor_kind",
        (since,)).fetchall()
    active = {r["actor_kind"]: int(r["n"]) for r in actors}

    by_tool = [dict(r) for r in conn.execute(
        "SELECT tool, count(*) n, avg(duration_ms) avg_ms FROM vitech_request"
        " WHERE at >= ? AND tool IS NOT NULL AND tool != ''"
        " GROUP BY tool ORDER BY n DESC", (since,)).fetchall()]

    by_equipment = [dict(r) for r in conn.execute(
        "SELECT equipment, count(*) n FROM vitech_request"
        " WHERE at >= ? AND equipment IS NOT NULL AND equipment != ''"
        " GROUP BY equipment ORDER BY n DESC LIMIT 20", (since,)).fetchall()]

    return {
        "window_hours": window_hours,
        "requests": n,
        "failures": failures,
        "failure_rate": round(failures / n, 4) if n else 0.0,
        "response_time": {
            "avg_ms": round(row["avg_ms"]) if row["avg_ms"] else None,
            "p50_ms": _percentile(durations, 50),
            "p95_ms": _percentile(durations, 95),
        },
        "llm": _latency("kind='llm' AND started_at >= ?", (since,)),
        "retrieval": _latency("kind='retrieval' AND started_at >= ?", (since,)),
        "package_generation": {
            "count": len(package),
            "avg_ms": round(sum(package) / len(package)) if package else None,
            "p95_ms": _percentile(package, 95),
        },
        "active_users": active.get("user", 0),
        "active_service_principals": active.get("service", 0),
        "by_tool": by_tool,
        "by_equipment": by_equipment,
        "cache": cache_stats(),
        "telemetry_writer": writer.stats(),
        "store": store.stats(),
        "logs": logs.file_stats(),
    }
