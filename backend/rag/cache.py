"""Retrieval cache — Redis-backed, with a bounded in-process fallback.

Retrieval is deterministic for a given (query, filters, k) against a fixed
corpus, so repeated questions (and the agent re-asking mid-conversation) can be
served from cache instead of re-embedding + re-searching + re-ranking. Same
Redis instance as session memory; if Redis is down we fall back to a small
in-process LRU so the pipeline still short-circuits within a session.

Cache is invalidated by version: `bump_version()` is called after an ingest so
every prior key becomes unreachable (no need to scan/delete).
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

from app import config

try:                                   # optional dependency, same as session.py
    import redis
except Exception:                      # pragma: no cover
    redis = None

_client = None                         # cached redis client, or False once known down
_local: "OrderedDict[str, str]" = OrderedDict()   # in-process LRU fallback
_LOCAL_MAX = 256
_VERSION_KEY = "vitech:retrieval:version"


def _get_client():
    global _client
    if _client is False:
        return None
    if _client is None:
        if redis is None:
            _client = False
            return None
        try:
            c = redis.from_url(config.REDIS_URL, socket_connect_timeout=0.5,
                               decode_responses=True)
            c.ping()
            _client = c
        except Exception:
            _client = False
            return None
    return _client


def _version() -> str:
    c = _get_client()
    if c:
        try:
            return c.get(_VERSION_KEY) or "0"
        except Exception:
            pass
    return str(_local.get(_VERSION_KEY, "0"))


def bump_version() -> None:
    """Invalidate the whole retrieval cache — call after ingesting documents."""
    c = _get_client()
    if c:
        try:
            c.incr(_VERSION_KEY)
            return
        except Exception:
            pass
    _local[_VERSION_KEY] = str(int(_local.get(_VERSION_KEY, "0")) + 1)


def _key(question: str, filters: dict, top_k: int) -> str:
    payload = json.dumps({"q": question, "f": filters or {}, "k": top_k},
                         sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"vitech:retrieval:{_version()}:{digest}"


def get(question: str, filters: dict, top_k: int):
    """Return cached hits list for this query, or None on a miss."""
    if not config.RETRIEVE_CACHE_ENABLED:
        return None
    key = _key(question, filters, top_k)
    c = _get_client()
    if c:
        try:
            raw = c.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    raw = _local.get(key)
    if raw is not None:
        _local.move_to_end(key)
        return json.loads(raw)
    return None


def put(question: str, filters: dict, top_k: int, hits: list) -> None:
    if not config.RETRIEVE_CACHE_ENABLED:
        return
    key = _key(question, filters, top_k)
    raw = json.dumps(hits, ensure_ascii=False)
    c = _get_client()
    if c:
        try:
            c.setex(key, config.RETRIEVE_CACHE_TTL, raw)
            return
        except Exception:
            pass
    _local[key] = raw
    _local.move_to_end(key)
    while len(_local) > _LOCAL_MAX + 1:      # +1 for the version entry
        k, _ = _local.popitem(last=False)
        if k == _VERSION_KEY:                # never evict the version marker
            _local[k] = _
            break


def backend() -> str:
    return "redis" if _get_client() else "memory"
