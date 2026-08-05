# Developer / Admin Console — plan

Objective: give a developer an operator's view of the running platform — logs,
errors, service health, the file/ingestion pipeline and the database — without
turning the application into a remote shell.

Decisions taken with the product owner (2026-08-05):

| Decision | Choice |
| --- | --- |
| Admin power | **Read-only observability first.** Write/execute actions are added later, individually. |
| Exposure | **Office LAN only** (deployment Phase 1). Built so exposure stays a config choice. |
| Database scope | **Application data + Flowise config, secrets masked server-side.** |

---

## 0. Why authentication comes first, and is not a parallel task

Verified on 2026-08-05 by reading the code and the running config, not assumed:

1. `frontend/src/auth/AuthProvider.jsx` matches credentials **in the browser**
   against a hard-coded list (`admin` / `vitech@123`). The JS bundle ships the
   password to every visitor. `role` is decorative — nothing server-side reads it.
2. **`VITECH_API_KEY` is unset**, so the `_api_key_guard` middleware in
   `app/main.py` is inactive. Every `/api/*` route is open to anyone who can
   reach port 8000.
3. `CORS_ORIGINS` defaults to `*`.
4. The retrieval permission hook takes its role from the **client-supplied
   `X-Role` header**, which anyone can set, and `RESTRICTED_DOC_CATEGORIES` is
   empty (allow-all).
5. The one existing admin route, `POST /api/admin/reload-index`, has no auth.

Today that exposes engineering data on a trusted LAN. That is the tolerable,
already-documented Phase-2 blocker. **An admin console changes the blast radius,
not just the surface**: logs carry paths and connection details, the database
reaches Flowise's `credential` table, and file-process visibility reaches the
server's filesystem. Shipping the console on today's gate would hand a full
operator seat to anyone who opens the login page — and because `role` is
decorative, nothing would separate `sales` from a developer.

So Phase 0 is a precondition. Nothing in Phase 1+ is reachable without it.

---

## 1. Two findings that shape the design

**The database is SHARED with Flowise.** `public` already contains Flowise's own
`user`, `role`, `login_activity`, `login_sessions`, `apikey`, `workspace_user`
and `credential` tables. Our auth tables must therefore be **namespaced
(`vitech_*`)** — creating a table called `user` would collide with Flowise's
schema and could break the agents, which are the one thing not reproducible from
git. This also means the DB browser must treat Flowise's tables as read-only
foreign territory.

**There is no logging layer at all.** No `logging.basicConfig`, no `getLogger`
anywhere in `app/`. "Inspecting logs" today means reading uvicorn's stdout as
redirected to `/workspace/persistent/logs/backend.log` — unstructured, no request
ids, no error capture, no correlation between a failed request and its trace.
The console cannot surface what the application never records, so **structured
logging is the first build in Phase 1**, not a later refinement.

Related: `app/jobs.py` keeps jobs in an **in-process dict**, so ingestion history
vanishes on restart. File-process visibility needs that persisted to be useful.

---

## 2. Phase 0 — Authentication backend (precondition)

New package `app/auth/`. Deliberately **no new dependencies**:

- **Password hashing** — `hashlib.scrypt` from the standard library. Strong, and
  it avoids adding `passlib`/`bcrypt` to a stack that currently installs clean
  with prebuilt wheels.
- **Sessions** — opaque random tokens (`secrets.token_urlsafe`) stored in
  `vitech_session`, not JWTs. A stored session can be **revoked instantly**,
  which matters far more for an admin console than statelessness does.

Schema (namespaced, additive, no existing table touched):

```
vitech_user      id, username, password_hash, salt, name, role, active,
                 created_at, last_login_at, must_change_password
vitech_session   token_hash, user_id, created_at, expires_at, ip, user_agent
vitech_audit     id, at, user_id, action, target, detail, ip
```

Endpoints: `POST /api/auth/login`, `POST /api/auth/logout`,
`GET /api/auth/me`, `POST /api/auth/password`.

Roles, server-side and authoritative: `viewer` < `engineer` < `admin` <
`developer`. A FastAPI dependency `require_role("developer")` gates every
`/api/admin/*` route; the existing `reload-index` route is moved behind it.

Also in Phase 0, because they are one-line changes that close open holes:

- set `VITECH_API_KEY` and lock `CORS_ORIGINS` to the real frontend origin;
- stop trusting `X-Role` — derive the principal's role from the session;
- seed the first developer account from env vars with `must_change_password`.

Frontend: swap the body of `AuthProvider.login()` for a `fetch`. That function
is already written and commented as the single seam for exactly this; the gate,
session handling, logout and UI stay identical.

**Acceptance:** with a valid session absent, every `/api/*` except `/api/health`
returns 401; a `sales` account receives 403 from every `/api/admin/*` route; the
password never appears in the JS bundle (`grep` the built asset).

---

## 3. Phase 1 — Observability (read-only)

New package `app/observability/`.

- **Structured logging** — JSON lines to `logs/app.jsonl`, one record per
  request: timestamp, request id, method, path, status, duration, user, error.
  A `X-Request-ID` middleware generates and propagates the id so a UI error and
  a server trace can be joined.
- **Redaction at the point of writing**, never at the point of display: password
  fields, `X-API-Key`, `Authorization` and anything from `credential` are
  replaced before the line is written. A secret that never enters the log cannot
  leak from it.
- **Error capture** — unhandled exceptions recorded with traceback, request id
  and the sanitised request, into a bounded ring buffer plus `logs/errors.jsonl`.
- **Service health detail** — Postgres, Redis, Ollama, Flowise, ChromaDB: up/down,
  latency, version, and for Ollama the loaded model. This is the panel that
  answers the single most common failure in this project — CLAUDE.md's own note
  that "the agent says it cannot call tools" *always* means the backend is down.

Endpoints (all `require_role("developer")`):
`GET /api/admin/logs` (tail, level filter, text search, by request id),
`GET /api/admin/errors`, `GET /api/admin/health/detail`,
`GET /api/admin/metrics` (request counts, p50/p95 latency, LLM + retrieval timings).

---

## 4. Phase 2 — Inspection (read-only, allow-listed)

**Database browser.** No arbitrary SQL. A server-side allow-list of tables and
columns, parameterised queries only, fixed page size:

- *Application data*: offers, uploads, jobs, packages, `vitech_user`
  (never `password_hash`/`salt`).
- *Flowise config*, because prompts live there and agent debugging genuinely
  needs it: `chat_flow`, `tool`, `chat_message`.
- *Masked server-side*: `credential` values, `apikey`, any `encryptedData` — the
  values are redacted **before leaving the process**, so a UI bug cannot disclose
  what the browser was never sent.
- Flowise's tables are surfaced **read-only**; the agents are the one asset not
  reproducible from git.

**File process visibility.** The upload → extract → chunk → embed → index
pipeline: what was ingested, when, by whom, how many chunks, what failed and why.
Requires persisting `app/jobs.py` to a table (it is in-memory today). Directory
views for `data/bulk`, `data/offers`, `data/packages` are **read-only listings
with a path-traversal guard** (resolve the path, then assert it is inside the
allowed root — a prefix check on the unresolved string is the classic bypass).

---

## 5. Phase 3 — Deep file-process and extraction architecture

Planned separately, and it lands naturally on Phase 1's logging and Phase 2's
persisted jobs: per-stage timing and failure reporting for the extraction
pipeline is only meaningful once each stage records what it did.

---

## 6. Explicit non-goals

These are refused by design, not merely unscheduled. Each turns a browser
session into server compromise, and none is needed for the stated objective:

- arbitrary SQL execution;
- shell / command execution;
- file writes, deletes or uploads through the admin console;
- exposing decrypted credential values, ever;
- an admin console reachable from the internet without MFA (out of scope while
  the target is LAN-only — revisit at deployment Phase 2/VPN).

## 7. Cross-cutting rules

- Every admin action, **including reads**, writes a `vitech_audit` row. The point
  of an audit trail is answering "who looked at that", not only "who changed it".
- Secure defaults: absent config denies rather than allows. Auth on by default,
  CORS closed by default, admin routes closed by default.
- Deterministic principles are untouched — this layer observes the platform and
  never participates in producing an engineering number.
