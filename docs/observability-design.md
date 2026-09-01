# Phase C — DevOps backend: schema and trace model, for review

Proposed design for persistent jobs, execution tracing, metrics and the admin
backend. **Nothing here is implemented yet.**

Guiding constraint: observability is **additive**. No engineering calculation,
document generation, quotation logic, retrieval behaviour or package generation
changes, and `tests_api_contract.py` must still show all 28 endpoints
byte-identical afterwards.

---

## 1. The decision that shapes everything: request IDs must not touch responses

The contract suite hashes response **bodies**. Adding `request_id` to a response
body would change all 28 fingerprints and destroy the very proof that Phase C
changed nothing.

So the request id travels as an **`X-Request-ID` response header**, never in the
body, and in-process via a `contextvar` so no engineering function signature
changes. If a caller supplies `X-Request-ID`, it is honoured (the frontend can
then correlate a failed page with a server trace); otherwise one is generated.

Consequence: the contract suite stays green with no re-record, and a green run
is real evidence rather than a re-baselined one.

---

## 2. Where the data lives, and why it is not one database

| Store | Contents | Why separate |
| --- | --- | --- |
| `data/auth.db` | users, sessions, service keys, **audit** | Small, precious, rarely written. Must never be at risk from ops churn. Losing it locks everyone out. |
| `data/ops.db` | requests, spans, jobs, artifacts | High-volume, purgeable, retained ~30 days. A corrupted or truncated ops database must never affect the ability to log in. |
| `logs/app.jsonl` | structured log lines | Append-heavy and greppable. Rotating files handle this well; a million log rows in SQLite would not. |
| `data/jobs/<job_id>/` | artifact files | Binary; belongs on the filesystem, not in a row. |

The audit trail stays in `auth.db` (it is a security record with a different
retention obligation), and the trace viewer joins the two **in Python** rather
than coupling the databases with `ATTACH`.

---

## 3. Persistent job schema — `data/ops.db`

```sql
-- One row per HTTP request. This is the "engineering request record" and
-- carries exactly the fields specified for Phase C.
CREATE TABLE vitech_request (
    request_id       TEXT PRIMARY KEY,   -- time-sortable id (ULID-style)
    at               REAL NOT NULL,      -- start, epoch seconds
    method           TEXT NOT NULL,
    path             TEXT NOT NULL,
    status           INTEGER,
    duration_ms      INTEGER,
    ok               INTEGER NOT NULL DEFAULT 1,
    -- who
    actor_kind       TEXT,               -- user | service | anonymous
    actor            TEXT,               -- username, or service principal name
    role             TEXT,
    ip               TEXT,
    -- what engineering happened
    agent            TEXT,               -- Engineering | Quotation | Drawing | NULL
    tool             TEXT,               -- generate_specification | generate_drawing | ...
    equipment        TEXT,               -- resolved category (paint_booth, ...)
    retrieval_count  INTEGER DEFAULT 0,  -- historical records retrieved
    rule_count       INTEGER DEFAULT 0,  -- engineering rules/standards applied
    warning_count    INTEGER DEFAULT 0,
    llm_ms           INTEGER DEFAULT 0,  -- summed, for the latency metric
    retrieval_ms     INTEGER DEFAULT 0,
    error            TEXT
);
CREATE INDEX ix_request_at        ON vitech_request(at DESC);
CREATE INDEX ix_request_actor     ON vitech_request(actor, at DESC);
CREATE INDEX ix_request_equipment ON vitech_request(equipment, at DESC);
CREATE INDEX ix_request_tool      ON vitech_request(tool, at DESC);

-- The execution path inside one request. Nesting via parent_id.
CREATE TABLE vitech_span (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    parent_id   INTEGER,
    seq         INTEGER NOT NULL,     -- order within the request
    name        TEXT NOT NULL,        -- 'retrieve.offers', 'llm.chat', 'package.drawing'
    kind        TEXT NOT NULL,        -- retrieval | llm | rules | resolve | package_stage | document | db
    started_at  REAL NOT NULL,
    duration_ms INTEGER,
    ok          INTEGER NOT NULL DEFAULT 1,
    detail      TEXT                  -- JSON: counts, model, cache_hit, scores, stage
);
CREATE INDEX ix_span_request ON vitech_span(request_id, seq);

-- A persisted engineering job. One per specification / drawing / BOM /
-- quotation / package generated.
CREATE TABLE vitech_job (
    job_id         TEXT PRIMARY KEY,
    request_id     TEXT,               -- links the job to its trace
    kind           TEXT NOT NULL,      -- specification | drawing | bom | quotation | package | ingest
    status         TEXT NOT NULL,      -- queued | running | succeeded | failed
    equipment      TEXT,
    requirement    TEXT,               -- the customer requirement, verbatim
    project        TEXT,
    client         TEXT,
    revision       TEXT DEFAULT '0',
    actor          TEXT,
    actor_kind     TEXT,
    created_at     REAL NOT NULL,
    started_at     REAL,
    finished_at    REAL,
    duration_ms    INTEGER,
    -- engineering outcome, denormalised so job history is one query
    confidence_pct INTEGER,
    release_status TEXT,               -- Engineering Draft | Customer Review Draft | ...
    warning_count  INTEGER DEFAULT 0,
    tbd_count      INTEGER DEFAULT 0,
    error          TEXT,
    summary        TEXT                -- small JSON summary for the list view
);
CREATE INDEX ix_job_created ON vitech_job(created_at DESC);
CREATE INDEX ix_job_kind    ON vitech_job(kind, created_at DESC);
CREATE INDEX ix_job_actor   ON vitech_job(actor, created_at DESC);

-- Downloadable outputs belonging to a job.
CREATE TABLE vitech_artifact (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL,
    name       TEXT NOT NULL,          -- Specification.pdf, Drawing_GA.svg, ...
    kind       TEXT NOT NULL,          -- pdf | svg | dxf | xlsx | md | json | zip
    path       TEXT,                   -- data/jobs/<job_id>/<name>; NULL if regenerable
    bytes      INTEGER,
    sha256     TEXT,                   -- integrity, and proves determinism on regeneration
    created_at REAL NOT NULL
);
CREATE INDEX ix_artifact_job ON vitech_artifact(job_id);
```

**Metrics are computed from `vitech_request`**, not stored in a rollup table. At
this scale the indexed queries are trivial, and a second source of truth for
numbers is exactly the kind of thing that drifts. A rollup table can be added
later if the request table grows past comfort.

---

## 4. Execution trace model

A trace is a **request id** and everything hanging off it:

```
request_id  ──  vitech_request      1   the summary record
            ──  vitech_span         N   the execution path, ordered and nestable
            ──  vitech_job          0..N what engineering artifact it produced
            ──  vitech_artifact     0..N downloadable outputs
            ──  vitech_audit        1..N (auth.db) who, and whether allowed
            ──  logs/app.jsonl      N   log lines carrying the same id
```

Span kinds, and the six seams that emit them — each is **one added line**, no
logic change:

| Seam | Span | Captured |
| --- | --- | --- |
| `retriever.retrieve` | `retrieve.offers` | hit count, top score, cache hit |
| `rag.retrieve.retrieve_documents` | `retrieve.documents` | count, filters, rerank |
| `ollama_client._ollama_chat` / `_stream` | `llm.chat` | model, ms, streamed |
| `resolver.resolve` | `resolve.spec` | policy (Consulting/ATS), row count |
| `engineering_planner.generate_spec` | `rules.apply` | rules applied, origins |
| `package.builder.build` | `package.<stage>` | per-document stage timing |

A reconstructed trace reads as the engineering story:

```
REQ 01JC…  POST /api/package   engineer1   paint_booth   2,431 ms   OK
├─ resolve.spec        412 ms   policy=ATS  rows=26
│  ├─ retrieve.offers   38 ms   hits=8  top=0.643  cache=miss
│  └─ rules.apply      131 ms   rules=8  standards=5
├─ package.drawing     684 ms   views=3  scale=1:50
├─ package.bom         102 ms   lines=11  priced=6
├─ package.quotation   298 ms   basis=OFF-CRI-PB-082406R4
└─ package.review       31 ms   FAIL=0 WARN=1 QUESTION=1
   job pkg_01JC…  succeeded  Customer Review Draft  13 artifacts
```

`GET /api/admin/trace/{request_id}` returns that as data.

---

## 5. Writing traces without slowing engineering down

A background writer thread drains a bounded `queue.Queue` and commits in
batches. The request path only enqueues.

**If the queue is full, the record is DROPPED and a counter incremented.**
Observability must never block or fail an engineering request — a dropped span
is an acceptable loss, a 5-second stall on a quotation is not. The drop counter
is surfaced in metrics so silent loss is visible.

---

## 6. Metrics (computed, plus in-process counters)

| Metric | Source |
| --- | --- |
| Requests, failure rate | `vitech_request` counts by status |
| Average / p50 / p95 response time | `duration_ms` |
| LLM latency | `llm_ms`, and `vitech_span` where kind='llm' |
| Retrieval latency | `retrieval_ms` |
| Package generation latency | requests where `path='/api/package'` |
| Active users / service principals | distinct `actor` in a window |
| **Cache hit ratio** | **new in-process counters in `rag/cache.py`** |

Cache counters are in-process and reset on restart — the cache itself is
in-process, so a persisted counter would describe a cache that no longer exists.
Stated in the response so nobody reads it as lifetime.

---

## 7. Retention (nothing grows without bound)

| Data | Default | Why |
| --- | --- | --- |
| requests + spans | 30 days | Debugging horizon |
| jobs | 365 days | Engineering record; outlives debugging |
| artifacts | 90 days or 5 GB, whichever first | Disk is finite |
| `app.jsonl` | rotate at 50 MB, keep 5 | Standard |
| audit (`auth.db`) | **never auto-purged** | Security record; deletion should be a deliberate act |

Purge runs from `POST /api/admin/retention/purge` and optionally on startup.

---

## 8. Artifacts: store, or regenerate?

Worth a decision, because **this platform is deterministic** — a specification,
drawing or package can be regenerated byte-identically from the stored
requirement. That makes storing every artifact arguably redundant.

But only *arguably*: regeneration reproduces the artifact **only while the offer
corpus and the rules are unchanged**. After a re-ingest, regenerating a
six-month-old quotation may legitimately produce a different document — and an
engineering record that changes when you re-open it is not a record.

**Recommendation — store, don't regenerate, for anything customer-facing:**

- **Package exports** (the `.zip` and its documents): **stored**. This is the
  deliverable; it must be immutable and reproducible for audit.
- **Specification / drawing / BOM / quotation generated interactively**: job row
  **always** recorded, artifact stored **on export/download only**. The
  interactive preview is regenerable and storing every keystroke-driven redraw
  would fill the disk with drafts nobody opened.
- Every stored artifact carries a **sha256**, so a later regeneration can be
  compared against it — which turns "is the platform still deterministic?" into
  a check we can actually run.

*This is open question 1 below.*

---

## 9. New admin endpoints (all Administrator-class)

```
GET  /api/admin/health/detail        (exists)
GET  /api/admin/metrics              counters, latencies, cache ratio
GET  /api/admin/requests             recent requests, filterable
GET  /api/admin/trace/{request_id}   the full reconstructed execution path
GET  /api/admin/jobs                 job history, filterable by kind/actor/status
GET  /api/admin/jobs/{job_id}        one job + its artifacts
GET  /api/admin/jobs/{job_id}/artifact/{name}   download
GET  /api/admin/logs                 tail/filter/search app.jsonl
GET  /api/admin/audit                (exists)
GET  /api/admin/cache                cache statistics
POST /api/admin/retention/purge      apply the retention policy
```

They slot into `auth/policy.py` under the existing `^/api/admin/` rule, so they
are administrator-only the moment they exist — no per-route decision.

---

## 10. What this does NOT do

- No engineering behaviour changes. The 28 contract fingerprints must be
  byte-identical **without re-recording**; that is the acceptance test.
- No sampling. At LAN scale everything is recorded; sampling would only add a
  way to miss the request someone is asking about.
- No log shipping, no external APM, no new dependency — `sqlite3`, `json`,
  `logging`, `queue`, `contextvars` are all standard library.
- Request bodies are **not** logged. A requirement is stored on the job (it is
  the engineering record); arbitrary bodies are not.

---

## Open questions before implementation

1. **Artifact storage** — accept §8 (store customer-facing exports, regenerate
   interactive previews), or store every generated artifact regardless of disk?
2. **Requirement text on jobs** — it is customer data, stored in a second place
   and readable by administrators. Fine, or store a hash plus a truncated
   summary?
3. **Retention defaults** — 30 days requests / 365 days jobs / 90 days
   artifacts. Right for the client's record-keeping obligations?
4. **Legacy `app/jobs.py`** — the in-memory ingest job manager. Fold it into
   `vitech_job` (one job model), or leave it and only persist engineering jobs?
   Folding is tidier and gives ingest history that survives restart.
