"""Structured JSON logging.

One JSON object per line in `logs/app.jsonl`, every line carrying the request id
so a log line and a trace are joinable.

TWO RULES, both enforced here rather than left to callers:

1. **Customer requirement text never enters a log.** It is engineering data and
   belongs on the job record behind a role. A log file gets tailed, copied and
   shipped; a requirement in one is customer content in a place nobody is
   guarding. `_SENSITIVE_KEYS` drops it at the point of writing.

2. **Secrets are redacted when WRITTEN, not when displayed.** A secret that
   never enters the file cannot leak from it — filtering at read time protects
   only the reader who uses the filter.
"""
import json
import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import Any

from .. import config
from . import context

LOG_DIR = Path(os.getenv("LOG_DIR", str(config.BASE_DIR / "logs")))
LOG_FILE = LOG_DIR / "app.jsonl"
MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(50 * 1024 * 1024)))
BACKUPS = int(os.getenv("LOG_BACKUPS", "5"))

# Dropped entirely. `question`/`requirement` are the customer's words; the rest
# are credentials.
_SENSITIVE_KEYS = {
    "question", "requirement", "requirement_text", "spec", "prompt", "messages",
    "password", "current_password", "new_password", "token", "api_key",
    "x-api-key", "authorization", "key", "secret", "credential", "encrypteddata",
}

_logger: logging.Logger | None = None


def _redact(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "<deep>"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).strip().lower() in _SENSITIVE_KEYS:
                out[k] = "<redacted>"
            else:
                out[k] = _redact(v, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v, depth + 1) for v in value[:20]]
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:500] + "…"
    return value


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(record.created, 3),
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "") or context.request_id(),
        }
        actor = getattr(record, "actor", "") or context.actor()
        if actor:
            payload["actor"] = actor
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(_redact(extra))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)[:4000]
        return json.dumps(payload, default=str, ensure_ascii=False)


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("vitech")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    _logger = logger
    return logger


def log(level: str, msg: str, **fields: Any) -> None:
    """Write one structured line. Never raises — logging must not break a request."""
    try:
        get_logger().log(getattr(logging, level.upper(), logging.INFO), msg,
                         extra={"fields": fields})
    except Exception:
        pass


def info(msg: str, **fields: Any) -> None:
    log("INFO", msg, **fields)


def warning(msg: str, **fields: Any) -> None:
    log("WARNING", msg, **fields)


def error(msg: str, exc: BaseException | None = None, **fields: Any) -> None:
    try:
        get_logger().error(msg, exc_info=exc, extra={"fields": fields})
    except Exception:
        pass


# --- reading, for the admin console -----------------------------------------

def tail(limit: int = 200, *, level: str = "", request_id: str = "",
         contains: str = "") -> list[dict]:
    """Most recent lines first, filtered. Reads the rotating file backwards."""
    files = [LOG_FILE] + [Path(f"{LOG_FILE}.{i}") for i in range(1, BACKUPS + 1)]
    out: list[dict] = []
    for path in files:
        if not path.exists() or len(out) >= limit:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if len(out) >= limit:
                break
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if level and entry.get("level") != level.upper():
                continue
            if request_id and entry.get("request_id") != request_id:
                continue
            if contains and contains.lower() not in line.lower():
                continue
            out.append(entry)
    return out


def file_stats() -> dict:
    files = []
    for path in [LOG_FILE] + [Path(f"{LOG_FILE}.{i}") for i in range(1, BACKUPS + 1)]:
        if path.exists():
            files.append({"file": path.name, "bytes": path.stat().st_size,
                          "modified": path.stat().st_mtime})
    return {"dir": str(LOG_DIR), "rotate_at_bytes": MAX_BYTES,
            "backups": BACKUPS, "files": files,
            "total_bytes": sum(f["bytes"] for f in files)}
