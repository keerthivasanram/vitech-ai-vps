"""All auth SQL, in one module.

Isolated deliberately: if auth ever moves to Postgres, this is the file that
changes and nothing else. Every other module works with `Principal` objects.

Concurrency: SQLite in WAL mode with a short busy timeout. The API serves sync
endpoints from a thread pool, so connections are per-thread and never shared.
"""
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .. import config
from . import passwords

ROLE_ENGINEER = "engineer"
ROLE_ADMIN = "admin"
ROLE_SERVICE = "service"

HUMAN_ROLES = (ROLE_ENGINEER, ROLE_ADMIN)
# Administrators inherit everything an engineer may do. A service principal is
# NOT in this ladder — it is a separate kind with its own route allow-list.
_RANK = {ROLE_ENGINEER: 1, ROLE_ADMIN: 2}

SESSION_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 900


@dataclass(frozen=True)
class Principal:
    """Who is making this request."""
    kind: str                      # "user" | "service" | "anonymous"
    id: Optional[int] = None
    name: str = ""
    role: str = ""
    session_token_hash: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self.kind in ("user", "service")

    @property
    def is_service(self) -> bool:
        return self.kind == "service"

    def has_role(self, required: str) -> bool:
        """Human role ladder only. A service principal never satisfies a human
        role: its access is decided by the route allow-list, not by rank."""
        if self.kind != "user":
            return False
        return _RANK.get(self.role, 0) >= _RANK.get(required, 99)


ANONYMOUS = Principal(kind="anonymous")

_local = threading.local()
_init_lock = threading.Lock()
_initialised = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vitech_user (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT NOT NULL UNIQUE,
    password_hash        TEXT NOT NULL,
    salt                 TEXT NOT NULL,
    name                 TEXT NOT NULL DEFAULT '',
    role                 TEXT NOT NULL DEFAULT 'engineer',
    active               INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts      INTEGER NOT NULL DEFAULT 0,
    locked_until         REAL,
    created_at           REAL NOT NULL,
    last_login_at        REAL
);
CREATE TABLE IF NOT EXISTS vitech_session (
    token_hash   TEXT PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    created_at   REAL NOT NULL,
    expires_at   REAL NOT NULL,
    last_seen_at REAL,
    ip           TEXT,
    user_agent   TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_session_user ON vitech_session(user_id);
CREATE TABLE IF NOT EXISTS vitech_service (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    key_hash     TEXT NOT NULL,
    key_prefix   TEXT NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   REAL NOT NULL,
    rotated_at   REAL,
    last_used_at REAL
);
CREATE TABLE IF NOT EXISTS vitech_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          REAL NOT NULL,
    actor_kind  TEXT NOT NULL,
    actor       TEXT NOT NULL,
    role        TEXT,
    action      TEXT NOT NULL,
    target      TEXT,
    status      INTEGER,
    ip          TEXT,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_at ON vitech_audit(at);
"""


def db_path():
    """Where the auth database lives.

    Under `data/` beside the other persisted state, and overridable so a
    production deployment can put it on the persistent volume rather than the
    container disk — the accounts must survive a rebuild.
    """
    import os
    override = os.getenv("AUTH_DB")
    return Path(override) if override else (config.BASE_DIR / "data" / "auth.db")


def connect() -> sqlite3.Connection:
    """A per-thread connection. Schema is created once per process."""
    global _initialised
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10.0,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    if not _initialised:
        with _init_lock:
            if not _initialised:
                conn.executescript(_SCHEMA)
                conn.commit()
                _initialised = True
    return conn


# --- users ------------------------------------------------------------------

def create_user(username: str, password: str, *, name: str = "",
                role: str = ROLE_ENGINEER, must_change: bool = False) -> int:
    if role not in HUMAN_ROLES:
        raise ValueError(f"role must be one of {HUMAN_ROLES}")
    salt = passwords.new_salt()
    conn = connect()
    cur = conn.execute(
        "INSERT INTO vitech_user (username, password_hash, salt, name, role,"
        " must_change_password, created_at) VALUES (?,?,?,?,?,?,?)",
        (username.strip().lower(), passwords.hash_password(password, salt), salt,
         name or username, role, 1 if must_change else 0, time.time()))
    conn.commit()
    return int(cur.lastrowid)


def get_user(username: str) -> Optional[sqlite3.Row]:
    return connect().execute(
        "SELECT * FROM vitech_user WHERE username = ?",
        (username.strip().lower(),)).fetchone()


def list_users() -> list[dict]:
    rows = connect().execute(
        "SELECT id, username, name, role, active, must_change_password,"
        " created_at, last_login_at FROM vitech_user ORDER BY username").fetchall()
    return [dict(r) for r in rows]


def user_count() -> int:
    return int(connect().execute("SELECT count(*) c FROM vitech_user").fetchone()["c"])


def set_password(user_id: int, password: str, *, must_change: bool = False) -> None:
    salt = passwords.new_salt()
    conn = connect()
    conn.execute(
        "UPDATE vitech_user SET password_hash=?, salt=?, must_change_password=?"
        " WHERE id=?",
        (passwords.hash_password(password, salt), salt, 1 if must_change else 0, user_id))
    conn.commit()


def authenticate(username: str, password: str) -> tuple[Optional[sqlite3.Row], str]:
    """(user, reason). `reason` is for the audit log, never for the client —
    telling a caller whether the USERNAME or the PASSWORD was wrong hands them
    a user-enumeration oracle."""
    row = get_user(username)
    if row is None:
        # Hash anyway: returning instantly for an unknown user is a timing
        # oracle that enumerates valid usernames.
        passwords.hash_password(password, passwords.new_salt())
        return None, "no such user"
    if not row["active"]:
        return None, "account disabled"
    locked = row["locked_until"] or 0
    if locked > time.time():
        return None, f"locked for {int(locked - time.time())}s"
    if not passwords.verify_password(password, row["salt"], row["password_hash"]):
        _record_failure(row)
        return None, "bad password"
    conn = connect()
    conn.execute("UPDATE vitech_user SET failed_attempts=0, locked_until=NULL,"
                 " last_login_at=? WHERE id=?", (time.time(), row["id"]))
    conn.commit()
    return row, "ok"


def _record_failure(row: sqlite3.Row) -> None:
    attempts = int(row["failed_attempts"] or 0) + 1
    locked = time.time() + LOCKOUT_SECONDS if attempts >= MAX_FAILED_ATTEMPTS else None
    conn = connect()
    conn.execute("UPDATE vitech_user SET failed_attempts=?, locked_until=? WHERE id=?",
                 (attempts, locked, row["id"]))
    conn.commit()


# --- sessions ---------------------------------------------------------------

def create_session(user_id: int, *, ip: str = "", user_agent: str = "",
                   days: int = SESSION_DAYS) -> str:
    token = passwords.new_token()
    now = time.time()
    conn = connect()
    conn.execute(
        "INSERT INTO vitech_session (token_hash, user_id, created_at, expires_at,"
        " last_seen_at, ip, user_agent) VALUES (?,?,?,?,?,?,?)",
        (passwords.token_hash(token), user_id, now, now + days * 86400, now,
         ip[:64], user_agent[:200]))
    conn.commit()
    return token


def resolve_session(token: str) -> Optional[Principal]:
    """Token -> Principal, or None if unknown/expired/revoked."""
    if not token:
        return None
    conn = connect()
    row = conn.execute(
        "SELECT s.token_hash, s.expires_at, s.revoked, u.id, u.username, u.name,"
        "       u.role, u.active"
        "  FROM vitech_session s JOIN vitech_user u ON u.id = s.user_id"
        " WHERE s.token_hash = ?", (passwords.token_hash(token),)).fetchone()
    if row is None or row["revoked"] or not row["active"]:
        return None
    if row["expires_at"] < time.time():
        return None
    conn.execute("UPDATE vitech_session SET last_seen_at=? WHERE token_hash=?",
                 (time.time(), row["token_hash"]))
    conn.commit()
    return Principal(kind="user", id=row["id"], name=row["username"],
                     role=row["role"], session_token_hash=row["token_hash"])


def revoke_session(token: str) -> None:
    conn = connect()
    conn.execute("UPDATE vitech_session SET revoked=1 WHERE token_hash=?",
                 (passwords.token_hash(token),))
    conn.commit()


def revoke_user_sessions(user_id: int) -> int:
    conn = connect()
    cur = conn.execute("UPDATE vitech_session SET revoked=1 WHERE user_id=? AND revoked=0",
                       (user_id,))
    conn.commit()
    return cur.rowcount


def purge_expired_sessions() -> int:
    conn = connect()
    cur = conn.execute("DELETE FROM vitech_session WHERE expires_at < ?", (time.time(),))
    conn.commit()
    return cur.rowcount


# --- service principals -----------------------------------------------------

def create_service(name: str) -> str:
    """Create (or rotate) a service principal and return its ONE-TIME key.

    The plaintext key is returned once and never stored, so a database read
    cannot recover a working credential.
    """
    token = passwords.new_token(32)
    prefix = token[:8]
    now = time.time()
    conn = connect()
    existing = conn.execute("SELECT id FROM vitech_service WHERE name=?", (name,)).fetchone()
    if existing:
        conn.execute("UPDATE vitech_service SET key_hash=?, key_prefix=?, active=1,"
                     " rotated_at=? WHERE id=?",
                     (passwords.token_hash(token), prefix, now, existing["id"]))
    else:
        conn.execute("INSERT INTO vitech_service (name, key_hash, key_prefix, created_at)"
                     " VALUES (?,?,?,?)", (name, passwords.token_hash(token), prefix, now))
    conn.commit()
    return token


def resolve_service(key: str) -> Optional[Principal]:
    if not key:
        return None
    conn = connect()
    row = conn.execute(
        "SELECT id, name, active FROM vitech_service WHERE key_hash=?",
        (passwords.token_hash(key),)).fetchone()
    if row is None or not row["active"]:
        return None
    conn.execute("UPDATE vitech_service SET last_used_at=? WHERE id=?",
                 (time.time(), row["id"]))
    conn.commit()
    return Principal(kind="service", id=row["id"], name=row["name"], role=ROLE_SERVICE)


def list_services() -> list[dict]:
    rows = connect().execute(
        "SELECT id, name, key_prefix, active, created_at, rotated_at, last_used_at"
        " FROM vitech_service ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def deactivate_service(name: str) -> None:
    conn = connect()
    conn.execute("UPDATE vitech_service SET active=0 WHERE name=?", (name,))
    conn.commit()


# --- audit ------------------------------------------------------------------

def write_audit(*, actor_kind: str, actor: str, role: str = "", action: str,
                target: str = "", status: Optional[int] = None, ip: str = "",
                detail: str = "") -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO vitech_audit (at, actor_kind, actor, role, action, target,"
        " status, ip, detail) VALUES (?,?,?,?,?,?,?,?,?)",
        (time.time(), actor_kind, actor, role, action, target[:400], status,
         ip[:64], detail[:600]))
    conn.commit()


def read_audit(limit: int = 200, *, actor: str = "", action: str = "") -> list[dict]:
    sql = "SELECT * FROM vitech_audit WHERE 1=1"
    args: list[Any] = []
    if actor:
        sql += " AND actor = ?"
        args.append(actor)
    if action:
        sql += " AND action LIKE ?"
        args.append(f"%{action}%")
    sql += " ORDER BY at DESC LIMIT ?"
    args.append(max(1, min(int(limit), 1000)))
    return [dict(r) for r in connect().execute(sql, args).fetchall()]
