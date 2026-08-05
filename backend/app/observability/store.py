"""All operations SQL, in one module — `data/ops.db`.

Separate from `auth.db` on purpose: this database is high-volume and purgeable,
that one is small and precious. A truncated or corrupted ops database must never
cost anyone the ability to log in.

Retention (V1.0, agreed):
    requests + spans .... 90 days
    jobs ................ permanent
    artifacts ........... permanent
    audit (auth.db) ..... permanent
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .. import config

REQUEST_RETENTION_DAYS = int(os.getenv("REQUEST_RETENTION_DAYS", "90"))

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vitech_request (
    request_id      TEXT PRIMARY KEY,
    at              REAL NOT NULL,
    method          TEXT NOT NULL,
    path            TEXT NOT NULL,
    status          INTEGER,
    duration_ms     INTEGER,
    ok              INTEGER NOT NULL DEFAULT 1,
    actor_kind      TEXT,
    actor           TEXT,
    role            TEXT,
    ip              TEXT,
    agent           TEXT,
    tool            TEXT,
    equipment       TEXT,
    retrieval_count INTEGER DEFAULT 0,
    rule_count      INTEGER DEFAULT 0,
    warning_count   INTEGER DEFAULT 0,
    llm_ms          INTEGER DEFAULT 0,
    retrieval_ms    INTEGER DEFAULT 0,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_request_at        ON vitech_request(at DESC);
CREATE INDEX IF NOT EXISTS ix_request_actor     ON vitech_request(actor, at DESC);
CREATE INDEX IF NOT EXISTS ix_request_equipment ON vitech_request(equipment, at DESC);
CREATE INDEX IF NOT EXISTS ix_request_tool      ON vitech_request(tool, at DESC);

CREATE TABLE IF NOT EXISTS vitech_span (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    started_at  REAL NOT NULL,
    duration_ms INTEGER,
    ok          INTEGER NOT NULL DEFAULT 1,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS ix_span_request ON vitech_span(request_id, seq);

CREATE TABLE IF NOT EXISTS vitech_job (
    job_id         TEXT PRIMARY KEY,
    request_id     TEXT,
    kind           TEXT NOT NULL,
    status         TEXT NOT NULL,
    equipment      TEXT,
    requirement    TEXT,
    project        TEXT,
    client         TEXT,
    revision       TEXT DEFAULT '0',
    actor          TEXT,
    actor_kind     TEXT,
    created_at     REAL NOT NULL,
    started_at     REAL,
    finished_at    REAL,
    duration_ms    INTEGER,
    confidence_pct INTEGER,
    release_status TEXT,
    warning_count  INTEGER DEFAULT 0,
    tbd_count      INTEGER DEFAULT 0,
    processed      INTEGER DEFAULT 0,
    error          TEXT,
    summary        TEXT
);
CREATE INDEX IF NOT EXISTS ix_job_created ON vitech_job(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_job_kind    ON vitech_job(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_job_actor   ON vitech_job(actor, created_at DESC);

CREATE TABLE IF NOT EXISTS vitech_artifact (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    path       TEXT,
    bytes      INTEGER,
    sha256     TEXT,
    created_at REAL NOT NULL,
    UNIQUE(job_id, name)
);
CREATE INDEX IF NOT EXISTS ix_artifact_job ON vitech_artifact(job_id);
"""


def db_path() -> Path:
    override = os.getenv("OPS_DB")
    return Path(override) if override else (config.BASE_DIR / "data" / "ops.db")


def connect() -> sqlite3.Connection:
    global _initialised
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        # Observability is not worth an fsync per row on the engineering path.
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    if not _initialised:
        with _init_lock:
            if not _initialised:
                conn.executescript(_SCHEMA)
                conn.commit()
                _initialised = True
    return conn


# --- writes (called only from the background writer) ------------------------

def insert_request(row: dict) -> None:
    cols = ("request_id", "at", "method", "path", "status", "duration_ms", "ok",
            "actor_kind", "actor", "role", "ip", "agent", "tool", "equipment",
            "retrieval_count", "rule_count", "warning_count", "llm_ms",
            "retrieval_ms", "error")
    conn = connect()
    conn.execute(
        f"INSERT OR REPLACE INTO vitech_request ({','.join(cols)})"
        f" VALUES ({','.join('?' * len(cols))})",
        tuple(row.get(c) for c in cols))
    conn.commit()


def insert_span(row: dict) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO vitech_span (request_id, seq, name, kind, started_at,"
        " duration_ms, ok, detail) VALUES (?,?,?,?,?,?,?,?)",
        (row.get("request_id"), row.get("seq"), row.get("name"), row.get("kind"),
         row.get("started_at"), row.get("duration_ms"), row.get("ok", 1),
         json.dumps(row.get("detail") or {}, default=str)))
    conn.commit()


# --- jobs (written synchronously: a job is a record, not telemetry) ---------

def upsert_job(job: dict) -> None:
    cols = ("job_id", "request_id", "kind", "status", "equipment", "requirement",
            "project", "client", "revision", "actor", "actor_kind", "created_at",
            "started_at", "finished_at", "duration_ms", "confidence_pct",
            "release_status", "warning_count", "tbd_count", "processed", "error",
            "summary")
    conn = connect()
    existing = conn.execute("SELECT job_id FROM vitech_job WHERE job_id=?",
                            (job["job_id"],)).fetchone()
    if existing:
        sets = [c for c in cols if c in job and c != "job_id"]
        conn.execute(f"UPDATE vitech_job SET {','.join(f'{c}=?' for c in sets)}"
                     " WHERE job_id=?",
                     tuple(job[c] for c in sets) + (job["job_id"],))
    else:
        conn.execute(
            f"INSERT INTO vitech_job ({','.join(cols)})"
            f" VALUES ({','.join('?' * len(cols))})",
            tuple(job.get(c) for c in cols))
    conn.commit()


def get_job(job_id: str) -> Optional[dict]:
    row = connect().execute("SELECT * FROM vitech_job WHERE job_id=?",
                            (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(*, limit: int = 100, kind: str = "", status: str = "",
              actor: str = "", equipment: str = "") -> list[dict]:
    sql = "SELECT * FROM vitech_job WHERE 1=1"
    args: list[Any] = []
    for col, val in (("kind", kind), ("status", status), ("actor", actor),
                     ("equipment", equipment)):
        if val:
            sql += f" AND {col} = ?"
            args.append(val)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(int(limit), 1000)))
    return [dict(r) for r in connect().execute(sql, args).fetchall()]


def insert_artifact(row: dict) -> None:
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO vitech_artifact (job_id, name, kind, path, bytes,"
        " sha256, created_at) VALUES (?,?,?,?,?,?,?)",
        (row["job_id"], row["name"], row.get("kind", ""), row.get("path"),
         row.get("bytes"), row.get("sha256"), row.get("created_at", time.time())))
    conn.commit()


def job_artifacts(job_id: str) -> list[dict]:
    return [dict(r) for r in connect().execute(
        "SELECT * FROM vitech_artifact WHERE job_id=? ORDER BY name",
        (job_id,)).fetchall()]


def find_artifact(job_id: str, name: str) -> Optional[dict]:
    row = connect().execute(
        "SELECT * FROM vitech_artifact WHERE job_id=? AND name=?",
        (job_id, name)).fetchone()
    return dict(row) if row else None


# --- reads ------------------------------------------------------------------

def get_request(request_id: str) -> Optional[dict]:
    row = connect().execute("SELECT * FROM vitech_request WHERE request_id=?",
                            (request_id,)).fetchone()
    return dict(row) if row else None


def list_requests(*, limit: int = 100, actor: str = "", tool: str = "",
                  equipment: str = "", failed_only: bool = False,
                  since: Optional[float] = None) -> list[dict]:
    sql = "SELECT * FROM vitech_request WHERE 1=1"
    args: list[Any] = []
    for col, val in (("actor", actor), ("tool", tool), ("equipment", equipment)):
        if val:
            sql += f" AND {col} = ?"
            args.append(val)
    if failed_only:
        sql += " AND ok = 0"
    if since:
        sql += " AND at >= ?"
        args.append(since)
    sql += " ORDER BY at DESC LIMIT ?"
    args.append(max(1, min(int(limit), 1000)))
    return [dict(r) for r in connect().execute(sql, args).fetchall()]


def request_spans(request_id: str) -> list[dict]:
    rows = connect().execute(
        "SELECT * FROM vitech_span WHERE request_id=? ORDER BY seq",
        (request_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d.get("detail") or "{}")
        except ValueError:
            d["detail"] = {}
        out.append(d)
    return out


def request_jobs(request_id: str) -> list[dict]:
    return [dict(r) for r in connect().execute(
        "SELECT * FROM vitech_job WHERE request_id=? ORDER BY created_at",
        (request_id,)).fetchall()]


# --- retention --------------------------------------------------------------

def purge(days: int = REQUEST_RETENTION_DAYS) -> dict:
    """Drop requests and spans past the retention horizon.

    Jobs, artifacts and the audit trail are PERMANENT by decision and are never
    touched here — they are the engineering and security record, and deleting
    them should be a deliberate act, not a scheduled one.
    """
    cutoff = time.time() - days * 86400
    conn = connect()
    old = [r["request_id"] for r in conn.execute(
        "SELECT request_id FROM vitech_request WHERE at < ?", (cutoff,)).fetchall()]
    spans = 0
    for i in range(0, len(old), 500):
        chunk = old[i:i + 500]
        cur = conn.execute(
            f"DELETE FROM vitech_span WHERE request_id IN ({','.join('?' * len(chunk))})",
            chunk)
        spans += cur.rowcount
    cur = conn.execute("DELETE FROM vitech_request WHERE at < ?", (cutoff,))
    conn.commit()
    return {"requests_removed": cur.rowcount, "spans_removed": spans,
            "older_than_days": days}


def stats() -> dict:
    conn = connect()
    def one(sql, *a):
        return conn.execute(sql, a).fetchone()[0]
    return {
        "requests": one("SELECT count(*) FROM vitech_request"),
        "spans": one("SELECT count(*) FROM vitech_span"),
        "jobs": one("SELECT count(*) FROM vitech_job"),
        "artifacts": one("SELECT count(*) FROM vitech_artifact"),
        "db_bytes": db_path().stat().st_size if db_path().exists() else 0,
        "retention_days_requests": REQUEST_RETENTION_DAYS,
    }
