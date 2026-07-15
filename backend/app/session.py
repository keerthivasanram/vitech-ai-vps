"""Session memory backed by Redis, with a graceful in-process fallback.

Each session keeps a rolling list of chat turns ({role, content, ts}) so the
assistant can answer follow-up questions with conversational context. If Redis
is not reachable, an in-memory dict is used so the app still runs (and you can
start Redis any time to get real, shared, persistent session memory).
"""
import json
import time

from . import config

try:
    import redis
except ImportError:
    redis = None

_client = None          # cached redis client (or False once we know it's down)
_mem: dict[str, list] = {}


def _get_client():
    global _client
    if _client is not None:
        return _client or None
    if redis is None:
        _client = False
        return None
    try:
        c = redis.from_url(config.REDIS_URL, socket_connect_timeout=0.5,
                           decode_responses=True)
        c.ping()
        _client = c
        return c
    except Exception:
        _client = False
        return None


def backend() -> str:
    return "redis" if _get_client() else "memory"


def _key(session_id: str) -> str:
    return f"chat:{session_id}"


def get_history(session_id: str, limit: int | None = None) -> list[dict]:
    limit = limit or config.SESSION_HISTORY
    c = _get_client()
    if c:
        items = c.lrange(_key(session_id), -limit, -1)
        return [json.loads(x) for x in items]
    return _mem.get(session_id, [])[-limit:]


def append(session_id: str, role: str, content: str) -> None:
    msg = json.dumps({"role": role, "content": content, "ts": time.time()})
    c = _get_client()
    if c:
        key = _key(session_id)
        c.rpush(key, msg)
        c.ltrim(key, -100, -1)
        c.expire(key, config.SESSION_TTL)
    else:
        _mem.setdefault(session_id, []).append(json.loads(msg))
        _mem[session_id] = _mem[session_id][-100:]


def clear(session_id: str) -> None:
    c = _get_client()
    if c:
        c.delete(_key(session_id))
    else:
        _mem.pop(session_id, None)
