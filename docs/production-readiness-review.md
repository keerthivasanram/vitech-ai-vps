# Production readiness review — 2026-08-05

A review of the repository as it stands, and the checklist that has to be
cleared before this is a Version 1.0 production release.

Every finding below was verified against the code or the running system. Where
an earlier assumption turned out to be wrong it is corrected here rather than
repeated — `/api/query`, for instance, looked like dead code and is not.

Severity: **S** blocks release · **H** high · **M** medium · **L** low.

---

## 1. Security

The platform currently has **no server-side authentication of any kind**. This
is one finding, not five, but it has several faces:

| # | Sev | Finding |
| --- | --- | --- |
| S1 | **S** | `VITECH_API_KEY` is unset, so the `_api_key_guard` middleware in `main.py` never engages. **All 36 endpoints are open** to anyone who can reach port 8000 — including `POST /api/admin/reload-index` and `POST /api/uploads`. |
| S2 | **S** | `frontend/src/auth/AuthProvider.jsx` matches credentials **in the browser**; `vitech@123` ships in the JS bundle. `role` is decorative — nothing server-side reads it, so `sales` and `admin` have identical power. |
| S3 | **S** | `CORS_ORIGINS` defaults to `*`. |
| S4 | **H** | The retrieval permission filter takes its role from the **client-supplied `X-Role` header**. Anyone can set it, so `RESTRICTED_DOC_CATEGORIES` cannot be relied on the moment it is populated. |
| S5 | **H** | `/api/query`, `/api/query/stream` and all nine `/api/tools/*` routes run the LLM with **no auth and no rate limiting**. On a GPU box this is an unbounded compute-cost and denial-of-service surface: a loop against `/api/query` saturates Ollama and every other user stalls. |
| S6 | **H** | `POST /api/uploads` has no auth, **no size limit and no type allow-list**. Path traversal *is* handled correctly (`Path(filename).name`), but the disk can be filled and arbitrary file types stored. |
| S7 | **M** | 15 endpoints accept a raw `dict = Body(...)` with no schema — exactly one Pydantic model exists in the whole API. Malformed payloads reach engine code before anything validates them. |
| S8 | **M** | No HTTPS, no security headers (HSTS/CSP/X-Frame-Options), no login rate limiting or lockout. |

**Verified NOT vulnerable** (checked, so nobody re-audits them): `.env` is not
tracked — only `.env.example`; `GET /api/offers/by-source/{file}` matches on
basename against stored metadata and never touches the filesystem; the upload
path strips directory components.

---

## 2. Performance and scale

| # | Sev | Finding |
| --- | --- | --- |
| P1 | **H** | **Nine separate full-collection scans.** `col.get(include=["metadatas"])` appears in `main.py` (×5), `retriever.py`, `analytics.py` and `pricing.py`. Each loads every offer's metadata and JSON-parses `_raw` **per request**, with no caching. At 33 offers this is invisible; the README targets "thousands of extracted CAD/PDF documents", and at that size these become the dominant cost of nearly every endpoint. |
| P2 | **H** | **34 of 36 endpoints are sync `def`**, so they run in FastAPI's default 40-thread pool. With ~10 s LLM calls, roughly 40 concurrent requests exhaust it and the **entire API stalls, including `/api/health`** — which is also what a monitor would be polling. |
| P3 | **M** | `LLM_TIMEOUT` is 300 s. One stuck generation holds a pool thread for five minutes. |
| P4 | **L** | `_build_package` calls `understand(q)` a second time to obtain parameters for the quotation, duplicating work already done inside `_prepare` (and potentially a second LLM call when the requirement is not a clear spec). |

---

## 3. Maintainability and technical debt

| # | Sev | Finding |
| --- | --- | --- |
| M1 | **H** | **`main.py` is 1,415 lines carrying 36 endpoints.** It mixes routing, response assembly, geometry helpers, PDF endpoints and the package orchestrator. This is the single biggest obstacle to safe change. |
| M2 | **H** | **Duplicated value parsers.** `_num` is defined **4 times** (`bom.py`, `drawing/spec_parser.py`, `drawing/envelope.py`, `engineering_planner.py`), `_row` 3 times, `_nos` and `_clip` twice each. These parse engineering values out of spec strings — a class of code this project has already had real bugs in. A fix must currently be made in four places, and they are free to drift apart silently. |
| M3 | **H** | **10 of 12 Python dependencies are unpinned** (`fastapi`, `pydantic`, `httpx`, `fpdf2`, `pdfplumber`, …). A rebuild resolves whatever is newest. This is precisely the version-drift trap that already broke the Flowise install — guarded there with an `overrides` block, unguarded here. `fpdf2` is a live example: the project has already been bitten twice by its API changing between versions. |
| M4 | **M** | `docs/developer_handbook.md` is substantially wrong: it describes Gemini/Supabase, a monolithic `App.jsx`, and `/api/query/stream` as "the primary chat endpoint". A new engineer following it would build the wrong mental model. |
| M5 | **L** | `README.md` still documents `/api/query` as the API and `python -m app.ingest` as the setup path; both predate the Flowise architecture. |
| M6 | **M** | 24 `except Exception` blocks. With no logging layer, anything they swallow is invisible. |

---

## 4. Testing gaps

Nine suites and ~1,800 lines of tests exist, and the deterministic engine is
genuinely well covered (goldens, engineering, drawing, review, BOM, package).
The gaps are concentrated in two places:

| # | Sev | Finding |
| --- | --- | --- |
| T1 | **H** | **No tests at all for the customer-facing document renderers** — `datasheet_pdf.py` (510), `quotation_pdf.py` (269), `specification_pdf.py` (177), `vitech_letterhead.py` (163). That is **1,119 lines generating exactly what the customer receives**, and the known failure mode is silent (fpdf2 API drift produced a mis-sized sheet and doubled circles before). |
| T2 | **H** | **No HTTP-level tests.** Every suite calls Python functions directly, so endpoint wiring, the `_named_requirement` guards, status codes and the auth middleware are entirely untested. A guard could be removed and every suite would stay green. |
| T3 | **M** | No tests for `agent_router.py` — the routing brain choosing Consulting vs ATS mode, and the source of several past bugs. |
| T4 | **L** | No tests for `jobs.py` or `ingest.py`. |

---

## 5. Observability

Confirmed by inspection: **there is no logging layer** — no `basicConfig`, no
`getLogger` anywhere under `app/`. Jobs live in an in-process dict and are lost
on restart. There are no request IDs, no metrics and no error capture. This is
already planned in `docs/admin-console-plan.md`; it is repeated here because it
is a release blocker in its own right, not merely an admin-console feature.

---

## 6. Architectural improvements — for discussion, not yet implemented

Four changes would materially improve robustness. None changes engineering
behaviour, and each is verifiable against the existing goldens.

1. **Split `main.py` into routers** (`routers/tools.py`, `drawing.py`,
   `package.py`, `admin.py`, `data.py`). Mechanical, low risk, and it makes
   applying an auth dependency to a whole group a one-line change instead of 36.
2. **One value-parsing module** (`app/values.py`) for `_num` / `_nos` / `_row` /
   `_clip`. Removes the 4× duplication. Must be proven byte-identical against
   goldens, since these helpers feed the spec, the BOM and the drawing.
3. **Cache the parsed offer record set**, invalidated on ingest, and read the
   nine full scans through it. Removes the dominant per-request cost at scale.
4. **Persist jobs to Postgres** (`vitech_job`), which priority 3 requires anyway.

My recommendation is 1 → 2 → 3 → 4, taking 1 and 2 before the auth work, because
both make the auth change smaller and safer to apply. **I have not implemented
any of them.**

---

# Version 1.0 release checklist

Ordered by the priorities set for this phase. Nothing here adds engineering
capability; it all serves robustness, maintainability and observability.

### A. Authentication and access control — *blocks release*
- [ ] `vitech_user` / `vitech_session` / `vitech_audit` tables, **namespaced** (the database is shared with Flowise, which already owns `user`, `role`, `credential`, `apikey`)
- [ ] Password hashing (`hashlib.scrypt`) and server-side sessions; no new dependencies
- [ ] `POST /api/auth/login|logout|password`, `GET /api/auth/me`
- [ ] Server-side roles `viewer < engineer < admin < developer`; `require_role` dependency
- [ ] Replace `AuthProvider.login()` with a real call; **verify the password is absent from the built bundle**
- [ ] Stop trusting `X-Role`; derive the principal from the session
- [ ] Set `VITECH_API_KEY`; lock `CORS_ORIGINS` to the real origin
- [ ] Rate limiting + lockout on login and on the LLM routes
- [ ] Upload: auth, size cap, extension allow-list
- [ ] Pydantic request models on the 15 raw-`dict` endpoints

### B. Observability — *blocks release*
- [ ] Structured JSON logging with request IDs; secrets redacted **at write time**
- [ ] Error capture with traceback, request ID and sanitised request
- [ ] Agent execution traces (tool called, duration, tokens, retrieval hits)
- [ ] Performance metrics: request counts, p50/p95, LLM and retrieval timings
- [ ] Service health detail for Postgres, Redis, Ollama, Flowise, ChromaDB

### C. Persistent job tracking — *blocks release*
- [ ] `vitech_job` table replacing the in-memory dict
- [ ] A row per specification, quotation, drawing and package, surviving restart
- [ ] Linked to the requesting user and to the request ID

### D. Admin console — *per `docs/admin-console-plan.md`*
- [ ] Read-only: health, service status, job history, agent timeline, logs
- [ ] Database browser: allow-listed tables, parameterised queries, **credentials masked server-side**
- [ ] Flowise inspection: chatflows and tools visible, secret values never sent to the browser
- [ ] Every admin action — including reads — audited

### E. End-to-end traceability
- [ ] A single `trace_id` from requirement → retrieval → rules → calculation → spec → drawing → BOM → quotation → package
- [ ] Retrieval hits and scores recorded per request, not only per value
- [ ] The package's existing `VT-nn` cross-reference joined to the trace
- [ ] One endpoint returning the full provenance of any delivered document

### F. Technical debt
- [ ] Split `main.py` into routers
- [ ] Consolidate the duplicated value parsers
- [ ] **Pin every dependency** and record the resolved set
- [ ] Rewrite `docs/developer_handbook.md`; correct `README.md`
- [ ] Review the 24 broad `except` blocks once logging exists

### G. Testing
- [ ] Tests for all four PDF renderers (page count, size, letterhead, latin-1 safety)
- [ ] HTTP-level tests: status codes, guards, auth, error shapes
- [ ] `agent_router` routing tests (Consulting vs ATS)
- [ ] Auth tests: 401 without a session, 403 for insufficient role
- [ ] CI running all suites on every push

### H. Operations
- [ ] HTTPS with security headers
- [ ] Backup **and a rehearsed restore** (`ops/verify-agents.sh` gating deploys)
- [ ] Log rotation and retention
- [ ] Documented rollback
- [ ] Resource limits so one heavy package request cannot starve the API

### Explicitly out of scope for 1.0
Multi-tenancy, internet exposure without MFA, arbitrary SQL or shell access from
the console, and replacing any deterministic logic with prompting.
