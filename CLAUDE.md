# Vitech AI Engineering Platform — Project Guide

> This file is auto-loaded by Claude Code every session. It carries the project
> context so a fresh session (e.g. on the VPS) understands the project without
> re-explaining. Update it as the project evolves.

## What this is
An enterprise **AI engineering assistant** for **Vitech Enviro Systems** (industrial
air-pollution-control & surface-finishing equipment: wet scrubbers, paint/powder
booths, dust collectors, ovens, conveyors, pretreatment, ducting). It turns a
client requirement into a **technical specification** and a **budgetary quotation**,
grounded in historical offers + engineering knowledge. **Not** a general chatbot.

## Golden rules (do not break)
1. **Never use the word "Copilot"** anywhere (code, UI, docs, prompts).
2. **Numbers are DETERMINISTIC** — engineering rules + historical data + code produce
   every number. The LLM only writes prose/narrative. Never let the model invent a
   dimension, price, capacity, count, or material.
3. **Human-in-the-loop** — every output is an engineer-reviewed *draft*, not auto-sent.

## Working mode — WHO does what (local dev vs VPS)
The VPS/RunPod pod was **UP for the 2026-07-24 session and is being STOPPED at end of it**
(bootstrapped from a wiped container disk, all services verified 200, extensive work done —
see the 2026-07-24 queue entry). Everything is committed+pushed and PG is backed up
(`vitech.sql`, 2026-07-24 08:40, hardened agent prompt confirmed in the dump). **On next
start:** `bash /workspace/persistent/start-all.sh`; if psql/node/ollama are gone (container
wiped) run `bootstrap-pod.sh` FIRST. Development happens in two places:
- **Local sessions (Windows, this machine)**: work on **frontend + backend code only**
  — anything that is just source edits and can be validated without a running pod
  (React/CSS/JS, FastAPI Python logic, golden tests where the venv is present).
  **Push to git at the end of each session** so the pod can `git pull` the changes.
  Do NOT try to start Flowise / Ollama / Postgres / ingestion here.
- **VPS session ("VPS Claude", runs on the pod when it's back up)**: does everything
  that needs the live stack — Flowise agent rebuilds/prompt tuning, Ollama model
  changes, ChromaDB/Qdrant ingestion, service restarts, end-to-end agent verification.
- **Handoff channel = this file (committed, auto-loaded on the pod).** When a local
  session produces work that still needs something done *on the pod*, append it to the
  **VPS Action Queue** below. That is how VPS Claude finds out what to run. Keep the
  queue current: add when you defer pod-side work, tick/remove when it's confirmed done.

## VPS Action Queue (VPS Claude: run these when the pod is back up)
> Local sessions append here; the VPS session executes + then checks items off.
> Cross-reference "KNOWN ISSUES" and "Immediate next steps" below for full detail.

### ▶ 2026-08-05 (Phase B) — PRODUCTION AUTHENTICATION IS LIVE. Read this before touching the API.
**Every route except `/api/health` now requires a credential.** Eleven suites green, and
`tests_api_contract.py` proves **all 28 engineering endpoints are byte-identical** to the
pre-auth baseline — the only two responses that moved are the two that were meant to.
- **HOW TO GET IN.** Accounts live in **SQLite at `backend/data/auth.db`** (override with
  `AUTH_DB`), gitignored. Create them with `.venv/bin/python -m app.auth.bootstrap
  admin|user|service|list|password`. A generated password prints ONCE. **There is no default
  account and no seeded password** — an empty user table locks everyone out, which is the
  correct failure, and the bootstrap command is the way in.
- **WHY SQLITE, NOT THE FLOWISE POSTGRES** (this reverses `docs/admin-console-plan.md`): the
  backend has **no Postgres client at all** — no psycopg, no SQLAlchemy — so Postgres would have
  meant a new dependency in a stack the review already flagged as under-pinned, AND writing into
  the database where the three agents live, the one asset not reproducible from git. All SQL is
  in `auth/store.py`, so moving later is one module.
- **THREE PRINCIPAL KINDS.** `engineer` < `admin` are humans; **`service` is NOT in that ladder**
  — it has its own route allow-list. That is the important property: **a leaked agent key can
  call `/api/tools/*` and NOTHING else** (403 on the offer corpus, ingest, uploads, audit).
  Pinned by tests.
- **`auth/policy.py` IS the security matrix, executable.** One central table, not per-route
  decorators, because deny-by-default only means something for the route nobody remembered to
  decorate: **an unclassified path defaults to administrator**. `docs/endpoint-security-matrix.md`
  is the same policy in prose.
- **THE FLOWISE AGENTS WOULD HAVE BROKEN** — they send `X-API-Key` now, written into all six
  tool rows by `ops/flowise/set-service-key.sh`. All three verified calling their tools after
  the change. **Rotation runbook: `ops/rotate-service-key.md`.** If an agent ever says "I don't
  have the ability to call external tools", that is the SAME signature as the backend being
  down — run `bash ops/flowise/set-service-key.sh --check` before anything else.
- **`X-Role` IS NO LONGER TRUSTED.** It was client-supplied and decided the retrieval permission
  filter; the role now comes from the credential and nowhere else.
- **`/api/health` is status-only.** It used to hand out `llm_model`, `ollama_host` and the
  document count to anyone who could reach the port. Diagnostics moved to
  `GET /api/admin/health/detail`.
- **The frontend password is GONE from the JS bundle** (verified by grepping the built asset).
  `lib/api.js` attaches the token in ONE interceptor rather than at 23 `fetch` call sites —
  a missed call site would be a page that silently 401s. A 401 clears the session and drops to
  the login screen.
- **Sessions are stored, not JWTs**, so logout revokes immediately (pinned by a test). Login
  never reveals whether the USERNAME or the PASSWORD was wrong, and hashes even for an unknown
  user so response time is not an enumeration oracle. 5 failures = 15-minute lockout.
- **Every non-public request is audited, reads included** (`GET /api/admin/audit`).
- **`/api/query*` and `/api/session/*` are administrator-only and hidden from the OpenAPI
  schema** (`include_in_schema=False`) — still reachable, decision on deleting them deferred
  past 1.0. **The seven agent `operation_id`s are unchanged**, verified in the schema fingerprint.

### ▶ 2026-08-05 (Phase A) — REFACTOR ONLY, byte-identical: routers, shared value readers, cache
Production-readiness Phase A, agreed as pure refactoring ahead of authentication. **All nine
suites green, goldens byte-identical, and 28 HTTP fingerprints unchanged** (see below).
- **`tests_api_contract.py` (NEW) is the safety net** — a status code + SHA-256 of each
  canonicalised response for 28 endpoints, **including `/openapi.json`**, because `operation_id`
  IS the Flowise tool name and a silently regenerated id would rename a live agent tool.
  Volatile values (refs, dates, index counts) are normalised; engineering values are NOT.
  Verified stable across two runs BEFORE recording, so a later diff means the code changed.
  This also closes the "no HTTP-level tests" gap — a guard could previously have been deleted
  with every suite still green. Re-record with `--record` only when a change is intended.
- **A1: `main.py` 1,415 -> 64 lines**, 34 endpoints into 12 routers under `app/api/`. Moved
  VERBATIM by line range, not retyped. Two collisions the contract test caught: `app/api/bom.py`
  doing `from .bom import ...` imports ITSELF rather than `app/bom.py` (same for drawing and
  package — all function-level relative imports moved one package deeper), and
  `_offers_overview` is shared by the data views AND the `list_projects` tool so it belongs in
  `support.py`. **Registration order is part of the contract**: `/api/offers/by-source/{path}`
  must stay ahead of `/api/offers/{offer_id}`.
- **A2: `app/values.py` (NEW)** owns the readers that decide whether "12 nos 600 x 600" means
  twelve filters or six hundred. **CORRECTING THE EARLIER REVIEW**: the four `_num` definitions
  are NOT four copies — `drawing/envelope._num` is a row LOOKUP filtered on provenance,
  `engineering_planner._num` is a type coercion that deliberately rejects strings, and
  `specification_pdf._row` draws a PDF table row. Merging those would have been a behaviour
  change. Where the two REAL copies disagreed (the BOM strips commas from "1,240 kg", the
  drawing's spec parser does not) it is a parameter, so neither caller's reading moves.
- **A3: parsed-offer cache** (`store.offer_records`) — `/api/records` **24.5ms -> 1.4ms**,
  `/api/offers` 23.5 -> 0.8ms. **The first version was WRONG and measurement caught it**: it
  called `col.count()` on every read to detect out-of-process writes, and that check cost ~20ms
  against ~6ms for the whole scan it guarded — three times SLOWER than no cache. Invalidation is
  now explicit (`invalidate_records()` from ingest and `reload_collection`), so the already-
  required `POST /api/admin/reload-index` after an out-of-process ingest stays the single step.
  **Two things deliberately NOT converted:** `knowledge_overview` reads flattened metadata, not
  parsed `_raw`, and converting it would have dropped rag-ingested documents that carry no
  `_raw`; and `/api/records` copies before sorting, because the cache is handed out by reference
  and sorting it in place would corrupt every other reader (both pinned by tests).

### ▶ ENDPOINT SECURITY MATRIX — `docs/endpoint-security-matrix.md` (agreed before Phase B)
All 34 routes classified Public / Authenticated User / Engineer / Administrator / Internal Only
(1 / 8 / 17 / 4 / 4). **Two things to know before switching auth on:**
- **The three Flowise agents will BREAK** unless they get a service principal first. They call
  `/api/tools/*` from localhost and cannot present a user session, so they need a long-lived
  API key — which lives in Flowise's `credential` table, the same table the admin console must
  never expose. The failure signature is the documented "agent says it cannot call tools",
  identical to the backend being down.
- **`/api/health` currently leaks** `llm_model`, `ollama_host` and `documents_indexed`. Public
  health must return status only; the detailed form belongs behind the admin role.

### ▶ PRODUCTION READINESS — `docs/production-readiness-review.md` + the V1.0 CHECKLIST
Full audit done 2026-08-05 (security, performance, tech debt, tests, observability) with the
**Version 1.0 release checklist** at the end. Read it before production work. Headlines:
- **No server-side auth at all** — `VITECH_API_KEY` unset means the middleware never engages, so
  all 36 endpoints are open; the frontend password ships in the JS bundle; CORS is `*`; the
  permission filter trusts a forgeable `X-Role` header. The LLM routes are unauthenticated and
  unthrottled, which on a GPU box is an unbounded cost + DoS surface.
- **Verified NOT vulnerable, so nobody re-audits them:** `.env` is untracked (only
  `.env.example`); `GET /api/offers/by-source/{file}` matches on basename against stored
  metadata and never touches the filesystem; the upload path strips directory components.
- **`/api/query` + `llm.py` + `session.py` are LIVE, not dead code** — an earlier reading of this
  file suggested otherwise. They are a real unauthenticated LLM surface.
- **Nine full-collection scans** (`col.get(include=["metadatas"])` in main ×5, retriever,
  analytics, pricing) parse every offer per request with no cache — invisible at 33 offers, the
  dominant cost at the "thousands of documents" the README targets.
- **34 of 36 endpoints are sync**, so ~40 concurrent 10-second LLM calls exhaust FastAPI's
  threadpool and stall the whole API *including `/api/health`*.
- **1,119 lines of customer-facing PDF renderers have ZERO tests**, and there are **no
  HTTP-level tests at all** — a guard could be deleted and all nine suites would stay green.
- **10 of 12 dependencies are unpinned** — the same version-drift trap already guarded on the
  Flowise side with an `overrides` block, unguarded on the Python side (fpdf2 has bitten twice).
- **`main.py` is 1,415 lines / 36 endpoints**; `_num` is defined 4x, `_row` 3x.
- **`docs/developer_handbook.md` is substantially WRONG** (Gemini/Supabase/monolithic App.jsx);
  it would give a new engineer the wrong mental model. Rewrite it before onboarding anyone.

### ▶ STATE AS OF 2026-08-05 (end of session) — and the NEXT objective
**Done this session** (all committed + pushed on `fix/list-projects-category-filter`, PG backed
up, **nine suites green, goldens byte-identical**): the two drawing categories completed, the
correction pipeline made deterministic, a client-stated value no longer printed as a gap, and
the **engineering package layer** built (see the two entries below for the detail).
**Next objective: a DEVELOPER / ADMIN console** — log + error inspection, file-process
visibility, database access, and the security work that has to come with it.
**PLAN: `docs/admin-console-plan.md`** (read it before starting). Decisions taken with the
product owner: **read-only observability first**, **office LAN only**, and **application data +
Flowise config with secrets masked server-side**. Two findings in there shape everything:
(a) the database is **SHARED with Flowise** — it already owns `user`, `role`, `credential`,
`apikey`, so our auth tables must be namespaced `vitech_*` or a rebuild could break the agents,
which are the one asset not reproducible from git; (b) **there is no logging layer at all**
(no `basicConfig`, no `getLogger` anywhere in `app/`), so structured logging is the first build,
not a refinement — the console cannot surface what the application never recorded. Also
`app/jobs.py` is in-memory, so ingestion history dies on restart.

> **READ THIS BEFORE BUILDING ANY ADMIN FEATURE.** The platform has **no backend
> authentication at all** today. Verified 2026-08-05, not assumed:
> 1. `frontend/src/auth/AuthProvider.jsx` matches credentials **in the browser** against a
>    hard-coded list (`admin` / `vitech@123`). The JS bundle ships the password to every
>    visitor. `role` is decorative — nothing server-side reads it.
> 2. **`VITECH_API_KEY` is NOT set**, so the `_api_key_guard` middleware in `main.py` is
>    INACTIVE. Every `/api/*` route is open to anyone who can reach port 8000.
> 3. `CORS_ORIGINS` defaults to `*`.
> 4. The permission hook reads its role from the **client-supplied `X-Role` header**, which
>    anyone can forge, and `RESTRICTED_DOC_CATEGORIES` is empty (allow-all).
> 5. The one existing admin route, `POST /api/admin/reload-index`, has no auth of its own.
>
> Today that exposes engineering data on a trusted LAN — tolerable, and the documented Phase-2
> VPN blocker. An admin console changes the blast radius entirely: logs carry paths and
> connection details, database access reaches Flowise's `credential` table and every offer, and
> file-process access reaches the server itself. **A real auth backend is therefore not a
> parallel task, it is the precondition** — building the console first would hand a full
> operator seat to anyone who loads the login page.

### ▶ 2026-08-05 (later) — ENGINEERING PACKAGE LAYER (`app/package/`): artifacts -> a reviewable set
Purely ADDITIVE — no existing engine was changed, and the nine suites (new `tests_package.py`,
**60 checks**) are green with goldens byte-identical. The platform produced four correct
documents that had nothing to do with each other; this layer makes them one package.
- **ONE resolution, seven documents.** `main._build_package` calls `_prepare` ONCE and every
  document is composed from that single analysis — specification, GA drawing, BOM, quotation,
  requirement summary, assumptions and review. That is what makes the package internally
  consistent: there is no second resolution that could disagree with the first. **If a module
  under `app/package/` ever computes an engineering number it is in the wrong place** — this
  layer only composes, classifies and cross-references.
- **`review.py` — the first document an engineer reads.** FAIL / WARNING / QUESTION / PASS,
  worst first, from checks the engines ALREADY ran (`cross_validate`, `release_gate`, geometry,
  provenance). **PASS entries are printed, not omitted** — a sheet showing only problems makes
  "no warnings" and "never checked" look identical. An untraceable value is a **FAIL**, and the
  verdict says what happens next ("NOT FOR ISSUE" / "ENGINEERING REVIEW REQUIRED" / "AWAITING
  CUSTOMER"). `Released Design` stays unreachable from code.
- **`assumptions.py` — a PARTITION, never a sample.** Five buckets (customer supplied /
  engineering calculated / historical reused / customer confirmation / engineering review), and
  a test asserts every row lands in exactly one. **Kept deliberately OUT of the specification**:
  the spec says what the equipment IS, this says what that statement rests on — a caveat folded
  into a spec table gets read as part of the design and quoted back. An **unrecognised origin is
  sent to engineering review, not assumed sound**.
- **`traceability.py` — joins resolved rows to the retrieval that produced them.** The resolver
  always recorded origin/source/reason; what was missing is that "reused from OFF-CRI-PB-082406R4"
  never said which DOCUMENT that is or how close the match was. Now every reused value carries
  **source project + source drawing (`record.source_file`) + similarity score (`hit.score`)**,
  and every calculated value its rule/standard. A value with no provenance is REPORTED.
- **`identifiers.py` — a cross-reference schedule, NOT a renumbering.** Spec rows are the spine
  (`VT-01`...); every other document keeps its own numbering. Forcing one scheme would mean
  rewriting the balloon allocator, and a GA whose balloons skip numbers is worse than one reading
  1, 2, 3. **Matching rule that matters:** the drawing legend is prose so it is matched on
  contained words, but the BOM and quotation scope take their names FROM the spec labels, so
  those match on EXACT slug — a near-match there ("Construction" vs "Construction material") is a
  different line, not a loose spelling. First attempt used token-subset everywhere and produced
  false links.
  **Gotcha:** the first run reported "26 of 26 cross-linked", which looked like a bug and was
  not — this quotation carries the whole machine as ONE scope list, so every row genuinely
  appears in it. A single "linked" count read as a quality score when it was really a statement
  about how the quotation is structured, so **per-document `coverage` is reported instead**.
- **`export.py` — the project folder, and the same folder as one download.** `Review.md`
  (read first), `Specification.pdf`, `Drawing_GA.pdf`/`.svg`, `Quotation.pdf`, `BOM.xlsx`,
  `Assumptions.md`, `Project_Summary.md`, `Traceability.md`, `Cross_Reference.md`,
  `package.json`. Every renderer is one that already exists, and the drawing PDF re-composes
  from the carried `_source` through the SAME `compose()` the studio uses — **an export is never
  a second rendering path**. `openpyxl` was already a declared dependency (the RAG loader reads
  XLSX), so `BOM.xlsx` added nothing to the install; BOM rows carry their `VT-nn` id.
- **A missing artifact is DECLARED, never faked.** No priced history -> no quotation, and the
  manifest says why; the package still builds. Writing an empty PDF so the folder looks complete
  would be the worst outcome. Verified: a wet scrubber with no derived envelope produces
  `dimensioned: false` and a sheet reading "NO DIMENSIONED VIEWS" — and the package matches
  `/api/tools/drawing` exactly for the same requirement (checked, because a divergence there
  would have meant the package had its own resolution path).
- **Endpoints:** `POST /api/package` (structured; `include_svg` opt-in) and
  `POST /api/package/export` (zip, or `write: true` -> `PACKAGE_DIR`, default `data/packages`).
  `_source` never leaves the process. The `generate_engineering_package` operation_id exists but
  **is not wired into any chatflow** — the endpoint is heavy (spec + drawing + quote + retrieval)
  and no agent calls it today.
- **`completion` is document completeness, explicitly NOT a delivery date** — the platform has no
  basis for manufacturing lead time, and a fabricated date is exactly the kind of number golden
  rule #2 forbids.

### ▶ 2026-08-05 — DUST COLLECTOR + POWDER PLANT DRAWINGS, and CORRECTIONS THAT ACTUALLY CORRECT
Reported as "we only have the paint booth; complete the other two categories" and "when I
mention a correction it needs to correct". All eight suites green throughout, **goldens
byte-identical**, and every claim below was checked by RENDERING the sheet, not by reading SVG.
- **THE GLYPHS WERE NOT THE PROBLEM.** All 14 categories already had glyph functions. The two
  named categories drew nearly EMPTY sheets (powder plant = three empty boxes) because neither
  is *adaptable* (`rules`/`field_rules`/`scale_driver`+`scalable` all absent), so the router
  resolved them in **knowledge mode with ZERO technical rows** — and a glyph handed an empty row
  list can only draw the casing. Both are now **`case_based: True`** in `catalog.py`, the same
  fix ovens got in 2026-07-24. Rows went **0 -> 19 (collector)** and **0 -> 13 (plant)**; the
  spec itself was equally empty before, so this fixes the specification too, not just the GA.
- **A composite field leaked a raw Python dict into the customer-facing spec.** A powder plant
  records a module as a nested object, and `engineering_planner._fmt` fell through to `str(v)`,
  printing `{'booth_type': 'downside draft', ...}` — braces, quotes and all — into the spec table
  AND the drawing legend. `_fmt` now flattens it to engineering text, `_sub_label` brackets the
  unit and keeps trade acronyms (`MOC`, `Inner size (m)`, `Blower motor (HP)`), and `_item`
  keeps the ORIGINAL mapping on the row as **`parts`** so the drawing reads a module's real size
  from the same resolved value the table prints (no second, drifting parser).
- **Both glyphs rebuilt.** Collector: tube sheet, pulse-jet header + real solenoid count, DP
  gauge, dirty-air inlet, clean-air outlet, filter access door, inlet/outlet sides on plan
  (legend 3 -> 12, BOM 0 -> 9). Plant: a real **PROCESS SEQUENCE** band (only stations that
  actually resolved — a TBD pretreatment is never drawn), the module schedule with real values,
  and a **true-scale BOOTH INNER OPENING overlay** using `View.model_w/model_h`. That overlay
  earns its place: on the test case it **caught a genuine clash** — a 2.0 m component against the
  reused 1.9 m booth opening — reported as `CHECK: ... confirm booth size`, never silently fixed.
- **`sheet._wrap` (NEW)**: the legend hard-sliced at 72 chars, printing "confirm booth s" and
  "Inner size (m): 3L x 1" — *a truncated engineering value looks like a wrong one*. Rows now
  wrap at spaces (2-line cap so notes cannot be pushed off the sheet). Benefits every category.
- **CORRECTIONS — the real bug was NOT what it looked like.** A correction reaches the engine as
  ONE restated requirement ("...5m x 3m x 4m ... changed to 6m x 3m x 4m") because the agent
  folds the follow-up in. **Every extractor uses `.search()`, which takes the FIRST match**, so
  the correction was parsed away and the sheet came back unchanged. Fixed **deterministically**
  (`understand._apply_correction`), not by prompting — a prompt cannot make an 8B model reliably
  rewrite a requirement, and the same words must always give the same drawing (the same reasoning
  that made `lookup_markdown` a code-rendered field). Handles "changed to", "now", "make it",
  "set/increase/reduce to", plus `_field_corrections` for **"change the HEIGHT to 6m"** where the
  field name sits *inside* the marker and only a bare number follows. A correction to one unit
  **drops its partner so it is recomputed** (1200 CFM -> 2039 CMH), instead of leaving a spec
  carrying the new CFM beside the old m3/h. **Proof: a corrected requirement now produces a
  BYTE-IDENTICAL drawing to stating it cleanly.**
  **Gotcha worth keeping:** an early live test appeared to pass because *the LLM* happened to
  parse "8m long" — the deterministic path still returned 5.0. A green end-to-end agent run does
  NOT prove the deterministic layer works; test `understand()` directly.
- **A CLIENT-STATED VALUE WAS BEING PRINTED AS A GAP.** Found while chasing the above: asked for
  a 9000 m3/h collector, the spec printed **"Air volume (m3/h): To be determined"** while showing
  a *derived* "Air volume cfm: 5297" as client-given. `apply_template` matches by LABEL, so when
  the nearest offer records the duty under another key the template fell straight through to
  history and then TBD — **never once consulting the requirement that started the whole thing**.
  `spec_template._field_from_requirement` adds the missing rung: **requirement -> history -> TBD**
  (and it applies to a `customer_decision` too — a decision the customer has already made is an
  answer, not a question). This was a platform-wide defect, not a drawing one.
- **Studio: 2 presets -> all 14**, each carrying that category's REQUIRED inputs, and **all 14
  verified to render**. **Gotcha:** the first attempt left 3 viewless — `dust_collector`,
  `conveyor` and `fume_extraction` are duty-specified (no L/W/H in their profile), so a preset
  must also carry the studio's optional overall-size inputs. Suggestions now demonstrate
  corrections, which were the least discoverable capability in the product.
- **Still open (deliberately):** component *positions* stay schematic and undimensioned — that
  remains blocked on the client's setting-out rules, and the powder plant's front elevation is
  legitimately sparse because its envelope is the max COMPONENT, not a plant footprint. Only ONE
  powder-plant offer is on file, so its reuse is a copy of that single plant; it improves the
  moment more are filed.

### ▶ 2026-08-02 (BOM) — BILL OF MATERIALS from the engineering model (`app/bom.py`)
Roadmap Phase 3, purely additive — no architecture change. `POST /api/bom` (operation_id
`generate_bom`) accepts a requirement, a studio `category`+`values`, OR a pasted specification;
the resolved spec also carries a structured `bom` block. **Eight suites green** (`tests_bom.py`,
26 checks). Deliberately NOT folded into `spec_markdown` — the agent already prints that at its
truncation limit (see the review-layer entry).
- **One engineering model, two documents.** BOM lines are derived from the SPEC's own rows —
  sheet weight, selected blower, filter count and size, luminaire count, duct bore — so the
  spec, the drawing and the BOM describe the same machine by construction.
- **Quantities and weights are engineering; MONEY is not.** A line is priced ONLY where the
  client's own `rate_card` reaches it. Everything else is listed with the cost left open and a
  reason. **Nothing is extrapolated and nothing is dropped**: the client priced exactly one
  blower model, so `CLP-4-15-14500` is listed UNPRICED rather than scaled from `CLP-4-10-9000`;
  a 13 kW panel is not priced from their 10 HP booth panel; MS structure is listed even though
  no rule computes its weight yet.
- **The total declares itself partial** and the printed BOM says "not a quotation" at the TOP.
  This is the direct consequence of the client's cost sheet having its first row cut off
  (Rs 5,68,534 visible vs Rs 6,49,264 stated) — no total built here can be validated against
  theirs, and a confident-looking grand total would be the most dangerous number we could print.
  **The uncosted list IS the answer to "what else do we need from you"** — on a 5x3x4 booth it
  names 6 gaps against 5 priced lines (Rs 2,73,966, 1240 kg).

### ▶ 2026-08-02 (drawing polish) — item list, revisions, duty, airflow, drawing types
Acting on a review of a real generated wet-scrubber GA. **Taken selectively** — the suggestions
to dimension component POSITIONS (nozzle height, pump position) were REJECTED: those have no
engineered setting-out rules, so dimensioning them would be fabrication, which is exactly what
golden rule #2 forbids. Line weights were already implemented (`LW_THICK/MED/THIN` + dash
patterns). All seven suites green (`tests_drawing` 122 -> 133 checks); browser checks all pass.
- **Item list on the sheet** — a printed or emailed GA should not need the studio panel beside
  it to tell you what the balloons refer to. Rows come from the resolved spec.
- **Revision block** above the title block, fed from the studio's own revision history, so a
  re-issued drawing states what changed and when. Absent when there is no history (no empty box).
- **Duty in the title block** — a GA titled only "Wet Scrubber" does not say WHICH wet scrubber.
  `_duty()` takes the rating off the spec's own rows (e.g. "Exhaust airflow: 10000 m3/h").
- **Airflow arrows** on scrubber + booth. Flow direction is how the machine WORKS, not a position
  we invented, so it is drawn as direction only and never dimensioned.
- **`drawing_type` was a DEAD CONTROL** — the studio has offered "Plan only" / "Elevations only"
  since it was built and nothing consumed it; every choice silently produced the full three-view
  GA. `views.VIEW_SETS` now drives it, with an unknown type falling back to the full GA.
- **Visible defect fixed:** the wet scrubber's circulation pump was drawn OUTSIDE the envelope
  (`x - pr - 5.0`), reading as a stray circle floating beside the drawing with a balloon attached
  to nothing. It now sits on the tank with its delivery riser. Two further collisions (tank
  balloon on the pump, "AIR OUT" clipping the height dimension) were found the same way —
  **by cropping and zooming the render, never by reading the SVG.**

### ▶ 2026-08-02 (later) — ENGINEERING REVIEW LAYER: cross-validation, scale-or-refuse, release gate
Phase 1 + 11 of the roadmap. **Most of this was already written and merely never wired** —
`check_historical` existed but was never called, the `STATUS_*` ladder was defined but nothing
computed it, and `validation` was calculated but never left the process. Seven suites green
(**new `tests_review.py`, 34 checks**); goldens moved in only 3 of 7 ATS cases, wording only,
**confidence unchanged in every case**; all knowledge cases byte-identical.
- **`cross_validate` now runs for EVERY category**, not just wet scrubbers — reuse across a size
  gap is a platform-wide failure mode and the client's reviewer found it on a paint booth. It
  uses their own ±20% tolerance via `check_historical`, comparing booths on floor area and
  duty-sized equipment on airflow.
- **`app/release_gate.py` (NEW)** answers what confidence cannot: *may this leave the building?*
  Engineering Draft / Customer Review Draft / Customer Ready, from the client's own criteria.
  A **customer decision is a question, not a gap**, so it does not hold the document back.
  **`Released Design` is deliberately unreachable from code** — release is an engineer's
  signature, and a program that could award it to itself defeats the human-in-the-loop rule.
  Verified on the reviewer's own case: a 10x10x10 booth built from a 7.5x4x3.5 offer is held
  back; a clean wet scrubber reaches Customer Ready.
- **A4 scale-or-refuse DONE** (`validate.demote_unscalable`, called in `analysis.py` BEFORE
  `apply_template`). Warning was not enough: the spec still PRINTED "20 W x 10 LED" as the
  lighting for a booth 7x the size of its source, and a reader takes a stated value as
  engineered. Beyond ±20% a size-dependent reused value is now demoted to an honest TBD with a
  reason naming what to re-size and from which offer. Scaling would be better, but that needs a
  per-field rule the client has not supplied.
- **THREE bugs in this new code, all found by checking OUTPUT rather than logic:**
  (a) the requirement carries CFM while an offer may record only m3/h — comparing 6100 m3/h with
  3000 CFM as one unit reported a **103% size gap where the true gap is 20%**. A basis is now
  used only when BOTH sides have it. (b) "Blower MOC = MS" and "Air intake filter = 10 micron
  velcro type" were called size-dependent because their labels named a component; a value must
  now carry an actual scaling quantity, and descriptors (MOC/material/type/finish/grade) are
  excluded. **A warning an engineer knows is wrong is worse than no warning.**
  (c) **the review section was APPENDED to `spec_markdown` and llama3.1:8b truncated the tail**
  (1997 chars in, 1781 out) — the warning existed in the JSON and never reached the reader. It
  now sits ABOVE the tables it qualifies. **Position is the structural fix; a prompt rule would
  be the fragile one.** Verified 4/4 with warning + status shown.
- **C1 field-level retrieval DONE** (`spec_template::_field_from_history`, called from
  `apply_template`, which now receives `offers` + `params`). The nearest offer decides most of a
  spec but it is ONE document: a field it leaves blank may be answered by the next-closest
  design. **TBD is now the last resort, not the first answer.** The same size guard applies
  (`validate.fits_size`) so retrieval cannot reintroduce the mismatch `demote_unscalable` exists
  to remove, and a **customer decision is never looked up** — it is theirs to make, not ours to
  find. Goldens: only the 2 paint-booth cases move (Blower MOC + Air intake filter tbd ->
  reused); all wet-scrubber and all knowledge cases byte-identical.
  **Honest limit on review defect #6:** only ONE booth on file (OFF-DMN-PB-180624R3, 9 m2)
  records a `dry_scrubber`, and its value is size-dependent — so it fills a comparable 9-9.6 m2
  booth and is correctly REFUSED for a 12 m2 one. The defect closes properly only when the
  client supplies more booths carrying that field.
- **Phase 1 is now complete.** Deliberately NOT doing, after review: the multi-agent split
  (would turn deterministic Python into LLM agents, and 8 prompts to stabilise instead of 3),
  the knowledge graph (a relational schema at 33 offers), the client portal (auth is still
  frontend-only), the coordinate GA layout engine (blocked on client setting-out rules), and
  **YAML rule files** (adds a parser, a schema and a new failure mode to load-bearing code for a
  benefit that assumes the client edits config — they send PDFs).

### ▶ 2026-08-02 — DRAWING AGENT COMPLETE: all 14 glyphs, DXF/PDF export, spec→drawing, revisions
Everything in `docs/drawing-agent-plan.md` §13 that is not blocked on the client is now built.
All six suites green throughout (`tests_drawing.py` **37 → 122 checks**), goldens byte-identical,
three agents verified reproducible from git (`ops/verify-agents.sh`), and every claim below was
checked in a real browser or by rendering the output.
- **EVERY catalog category now draws** (glyphs 2 → **14**): hot_air_oven, dust_collector,
  powder_coating_plant, conveyor, ducting, cleaning_room, buffing_booth, flash_off_zone,
  paint_drying_oven, blast_booth, pretreatment_plant, fume_extraction. Shared enclosure furniture
  (`_lights`/`_filter_bank`/`_fan`/`_door`) holds the common vocabulary. **Legend tags allocate
  themselves** (`item()`), because conditional rows left holes in the numbering (1, 2, 3, **5**);
  `note_item()` adds a LETTERED row for a real value with no engineered position to draw.
  **powder_coating_plant deliberately annotates its envelope as the MAXIMUM COMPONENT envelope** —
  the catalog's geometry inputs are the largest component's L/W/H, NOT a plant footprint, so
  drawing plant machinery inside it would be a lie.
- **P2 EXPORTS DONE** — `app/drawing/export.py`: **DXF R12** (hand-rolled; the primitives are only
  lines/circles/polylines/text, so `ezdxf` would buy nothing) and a **true-size vector PDF** via
  fpdf2. Both consume the SAME `Canvas` the SVG comes from, through the new `compose()` — an
  export can never drift from the approved sheet. `POST /api/drawing/export` (svg/dxf/pdf) serves
  the studio form, a chat requirement, or a pasted spec. DXF validated by reading it back with
  ezdxf (AC1009, correct extents, layers, linetypes) and round-tripping it to an image.
- **SPECIFICATION → DRAWING** (`app/drawing/spec_parser.py`, `POST /api/drawing/from-spec`; the
  agent tool auto-detects a pasted spec). It **parses rather than re-resolves ON PURPOSE**:
  re-running the resolver draws a spec that *resembles* the reviewed one, parsing draws the
  document the engineer is holding — every value they reviewed and every TBD they accepted. Only
  safe because the document is ours (`main._spec_markdown` emits it); anything off-contract
  returns None and the caller falls back to resolving a requirement.
- **STUDIO REVISIONS** — a new drawing is APPENDED, never substituted. A strip of numbered
  thumbnails sits top-left of the canvas; click one to go back. Each revision keeps its own
  `source`, so an OLD revision still exports to DXF/PDF exactly as drawn, and the title block is
  stamped with the revision number so a printed sheet is self-describing. Chat-driven changes are
  revisions too — "alter it" never discards the sheet it started from.
- **PARAMETER PANEL rebuilt** into collapsible sections: required inputs / process & options /
  additional specification (hand-entered lines, carried as **stated** values, never dressed up as
  calculated, and always kept in the BOM) / from-a-specification / title block (project, client,
  drawing no., drawn by, checked by).
- **Duty-specified categories can now be drawn from the studio.** dust_collector, conveyor and
  ducting have no L/W/H in their profiles, so the form could only ever make an undrawable sheet —
  even though the resolver accepts those dimensions fine from a chat requirement.
  `fields.size_fields()` offers optional overall-size inputs as **DRAWING inputs that never enter
  the catalog profile**, so completeness, required-input prompting and the goldens are untouched.
- **Derived envelopes**: dust_collector (client-stated casing ONLY — there is deliberately **no
  airflow→casing fallback**, that needs an air-to-cloth ratio and hopper proportions the client
  has not supplied) and ducting (given run length × the diameter `select_duct` computes from the
  client's own transport-velocity standard).
- **FIVE bugs that were invisible in the source and only appeared when RENDERED** — this is why
  the screenshot rule exists: (a) views hugged the left edge leaving a dead band, now centred;
  (b) glyph geometry escaped the sheet frame; (c) **fpdf2 SWAPS an explicit `(w,h)` format when
  told orientation `"L"`** — a 420×297 landscape sheet came out 297×420 portrait; (d) **fpdf2 ≥
  2.5.6 `circle()` takes centre+radius**, not the legacy bounding box + diameter, so every balloon
  drew at twice size offset up-left; (e) the paint_booth glyph read only the plural "Filters", so
  every STANDARDS-resolved booth (label "Paint arresting filter") drew a bank with no elements.
- **Also fixed: a silent dimension-extraction bug.** `_labelled_dims` matched "long" in
  "3.9 m long 4 m wide 8.3 m high", scanned FORWARD and took the NEXT dimension's number →
  length 4.0, width 8.3, no height. Phrasing is now decided once per string (whichever layout
  appears first wins). A wrong envelope draws a wrong GA, and `_exact_dimension_hit` uses this
  same parser for project lookups.
- **`ezdxf` is installed in the pod venv for VERIFICATION only** — it is not in
  `requirements.txt` and no app code imports it; the DXF writer is dependency-free by design.

### ▶ 2026-08-01 (studio UX) — canvas navigation, right-hand chat rail, status bar
User feedback after the live review: "mouse is too sensitive", "chat needs to be on the right
when we click expand", "needs to work properly for enterprise-level design". All verified in a
real browser at both layouts, six suites green.
- **Canvas navigation reworked.** Zoom is now **exponential, normalised and cursor-anchored**:
  the wheel delta is normalised across `deltaMode` (pixels / lines / pages) so a notch means the
  same on every device and a trackpad's small deltas do not accelerate away, and the point under
  the cursor stays fixed while the scale changes. **Sensitivity: 15.5% -> 4.0% per notch** — the
  arithmetic matters, `exp(120 * k)`: the first attempt used k=0.0012 which was *worse* than the
  10% it replaced (twelve notches reached **563%**); k=0.00033 lands twelve notches at **161%**.
  Zoom + pan now live in **one `view` state object** — zoom-to-cursor needs the new pan computed
  from the new zoom, and two separate setState calls read a stale partner value.
  The `%` badge is a button that resets to 100%.
- **Chat becomes a RIGHT-HAND RAIL in expanded view** (`.studio-dock.is-rail`), so expanded mode
  is a three-pane workspace: controls | canvas | conversation. The canvas reserves the rail's
  width so the sheet centres in what is left instead of hiding underneath it. Below 1180px the
  rail falls back to the bottom dock. Same markup in both places, positioned entirely by CSS.
- **Status bar added** — category, scale, sheet size, envelope in mm, view count and TBD count,
  always legible without reading the drawing. **Gotcha:** it first overlapped the command dock;
  it now sits at `bottom: 68px` in the normal layout and drops to `14px` in expanded view where
  the dock is a rail (and back to 68px in the narrow-screen fallback).

### ▶ 2026-08-01 (fixes) — studio 500 + console flood fixed, focus mode added
Found by the user reviewing the app live; all three verified in a real browser, six suites green.
- **500 on Generate drawing — FIXED.** `/api/drawing/render` coerced ANY numeric-looking value
  to a float, so a TEXT field given digits (paint process "10") reached the material engine as
  `10.0` and crashed it: `'float' object has no attribute 'lower'`. Root cause was two
  definitions of "is this field numeric?" — the catalog endpoint typed fields from the key's
  unit suffix while render guessed from the value. **New `app/drawing/fields.py` is the single
  contract** (`unit_for` / `is_number` / `describe` / `coerce`) used by BOTH endpoints, so they
  cannot drift again. A numeric field holding junk is now dropped rather than passed through as
  text, and blanks are omitted so they surface as TBD instead of zero.
- **Console flood — FIXED.** The canvas used React's `onWheel` prop with `preventDefault()`;
  React attaches wheel handlers **passively**, so every wheel notch logged "Unable to
  preventDefault inside passive event listener". The listener is now registered natively with
  `{ passive: false }` via a ref — the only way to zoom the sheet without scrolling the page.
  Verified: 0 such errors after 12 wheel events.
- **Focus mode ADDED** (studio canvas toolbar, expand/shrink icon, **Esc** to exit). Hides the
  sidebar and top header and gives the sheet the whole window. Driven by a `studio-focus` class
  on `<body>` so the studio owns the behaviour instead of lifting layout state into `App.jsx`.
  **Gotcha:** the header's class is `.topheader`, NOT `.top-header` — the first CSS attempt
  silently left it on screen.

### ▶ 2026-08-01 (final) — DRAWING AGENT LIVE + paint-shop categories wired (commit d4b7d5d)
Everything buildable from the data on hand is now done. **THREE agents are live**; PG backed up
2026-08-01 08:38 with all three inside. All **six** suites green.
- **Flowise "Drawing Agent" BUILT** — `/workspace/persistent/drawing-agent-build.py` (clone the
  Engineering Agent, same pattern as the Quotation Agent). Chatflow id
  **`f486d388-d032-44bb-acb5-db9dad3b950d`**; tools `generate_drawing` (new tool row) +
  `generate_specification` + `lookup_project` + `list_projects`; prompt **3,102 chars**.
  **CRITICAL DESIGN POINT — the tool function DELETES `svg` before returning.**
  `/api/tools/drawing` emits a ~16 KB sheet; giving that to llama3.1:8b swamps its context with
  vector data it cannot use. The CANVAS renders the drawing; the model gets the summary, scale,
  TBD schedule and BOM. If you ever rebuild that tool row, keep the `delete data.svg;` line.
  Verified 3/3 per case: correct tool, `drawing_markdown` verbatim, no vector leak; plus
  greetings / identity / confidentiality / spec-routing / list-routing all clean, and a bare
  "draw it" correctly ASKS instead of inventing.
- **Studio chat dock** — the agent decides, then the canvas is refreshed from the SAME
  requirement via the deterministic endpoint, so agent and canvas cannot disagree.
- **`app/drawing/envelope.py` (NEW)** — a wet scrubber never states L x W x H (it is specified by
  airflow + tower diameter, height computed by the rule engine), so every chat-driven scrubber
  drew as an unscaled, viewless sheet. The envelope is now composed from already-resolved
  numbers: tower diameter = footprint, computed tower height = height. **Only client-given or
  rule-computed values qualify** — a REUSED historical value is not a dimension of THIS machine —
  and a partial envelope is refused outright. Add a category by adding one function to `_DERIVERS`.
- **FOUR paint-shop categories live end to end**: `cleaning_room`, `buffing_booth`,
  `flash_off_zone`, `paint_drying_oven` — classify keywords, catalog profiles wired to the
  client's formulas via `_paint_shop_rules`, and spec templates. **Draft type flows through**:
  down draft -> plan area, side draft -> side face, cross draft -> end face, unstated -> the
  legacy default (verified 18 / 24 / 12 / 12 m² on a 6x3x4). The oven computes surface area and
  sheet weight but reports exhaust as **TBD until an ACH is supplied** — the honest-gap contract
  working as designed. The studio form picks all 14 categories up automatically (it is
  catalog-driven), including the oven's extra `ach` field.
- **Login for a live check** (`frontend/src/auth/AuthProvider.jsx`, no auth backend yet):
  `admin` / `vitech@123` or `sales` / `vitech@123`. Forward 5173 / 3000 / 8000.

### ▶ 2026-08-01 (later still) — DRAWING AGENT: engine + studio BUILT (P0 + most of P1)
Committed c46fd05 (backend) + da36ca2 (studio). `tests_drawing.py` (37 checks) added; all
**six** suites green (golden / engineering / drawing / lookup / pricing / retrieval).
Full detail in `docs/drawing-agent-plan.md` §12 "Built vs remaining".
- **`backend/app/drawing/`** — the deterministic geometry→vector engine, mirroring the
  `engineering/` package split: `primitives` (mm vector model, byte-stable SVG, one `<g>` per
  layer), `views` (third-angle plan/front/side + standard drafting scale), `symbols`
  (paint_booth + wet_scrubber glyphs — **the registry is the client-extension point**),
  `title_block` (shares `vitech_letterhead` constants), `sheet` (A4/A3/A2/A1 + legend + notes +
  TBD schedule), `drawing_service` (`build_drawing(spec)`).
- **Golden rule #2 in drafting terms**: dimensions come from `_spec_geometry`; an unknown axis
  prints **TBD**, never a line. With no dimensions at all the sheet says "NO DIMENSIONED VIEWS"
  and schedules every unknown instead of drawing a fabricated box. Component **positions** have
  no engineered setting-out rules yet, so glyphs are deliberately **schematic, undimensioned**,
  with a standing sheet note saying exactly that — but component **counts and models are real**,
  read from the resolved spec (e.g. 9 filters, blower CLP-4-15-14500).
- **Three endpoints**: `GET /api/drawing/catalog` (categories + per-category input fields +
  drawing types + sheet sizes **as DATA**, so the studio form hard-codes no equipment list),
  `POST /api/drawing/render` (studio structured-input path), `POST /api/tools/drawing` →
  `operation_id: generate_drawing` (agent tool, same no-requirement guard as spec/quote).
- **Drawing Studio UI rebuilt** on the real engine; the old client-side `lib/drawingSvg.js`
  preview is **DELETED** — geometry living in both Python and JS is exactly the drift golden
  rule #2 forbids. Verified in a live browser: 10 categories, drawing renders, 8 layer toggles,
  hiding "Dimensions" removes exactly that layer, zero console errors.
- **Gotcha — the studio feeds parameters STRAIGHT into the resolver**, it does not compose a
  sentence and re-parse it. The first attempt did, and every dimension was silently lost
  (unscaled, viewless sheet): the extractor does not recognise "5 m long 3 m wide". One
  resolution path, two input routes.
- **Two bugs that only surfaced by RENDERING the output**, not by reading the SVG: (a) the
  document `<g>` sets `fill="none"` so outlines stay hollow, and `Text` did not override it —
  every label, dimension and title-block entry was **invisible** while the markup looked
  perfect; (b) component counts used a bare integer match, so "flame proof LED 700-800 LUX"
  became **700 luminaires**. Counts now need an explicit `nos`/`set` marker. Both are pinned by
  tests. **Lesson: screenshot generated graphics before believing them.**
- **REMAINING**: the **Flowise "Drawing Agent" chatflow is NOT built** — today the studio drives
  the engine through its form, not through chat. Clone the Engineering Agent
  (`drawing-agent-build.py`), tools `generate_drawing` + `generate_specification` +
  `lookup_project` + `list_projects`; the tool already returns `drawing_markdown` for the chat
  plus the SVG for the canvas. **Heed the prompt-length lesson below.** Then P2 (DXF/PDF export)
  and more category glyphs (oven, dust collector, powder coating, conveyor — one function each).

### ▶ 2026-08-01 (later) — CLIENT ENGINEERING CALCULATIONS LANDED (queue item 6 UNBLOCKED)
The client delivered three things at once. All are now executable engineering, committed
(854b042, 86373cf), with `tests_engineering.py` (45 checks) guarding them and all five suites
green. **What arrived:**
1. **Engineering-calculation document** ("New Microsoft Word Document.pdf") — the doc that had
   blocked queue item 6 since 2026-07-30. Covers **Paint shop Plant only**; powder coating and
   pollution-control equipment are explicitly "will give later" (chase them).
2. **Vendor blower chart** (Continental Thermal Engineers, DIRECT DRIVE) — 203 models across
   21 pressure classes.
3. **A real costed BOM** — Vitech's own paint spray booth cost sheet dated 24.07.2026.

**What was built:**
- **`app/engineering/blower_service.py`** — the chart as data + catalogue-only selection. It
  returns a REAL model or None, never an interpolated machine. **Validated against the client's
  own BOM**: their booth line reads 'CLP-4" WC-10 HP-9000Cfm-Direct Drive' and `select_booth_
  blower(9000)` reproduces `CLP-4-10-9000` exactly. That assertion is the anchor test — keep it.
  **Design note worth not re-litigating**: booth selection pins the **CLP-4 pressure class**
  (the family the client actually builds) rather than a flat static-pressure floor, because
  static pressure *within* a series is the FAN CURVE — it falls from 95 mmwc at 1600 CFM to 54
  at 61000. A fixed floor pushed larger booths out of CLP-4 into costlier high-pressure series
  and broke monotonic scaling. `select_booth_blower_set()` splits across N machines when a duty
  exceeds the largest model.
- **`app/engineering/paint_shop_service.py`** — the client's formulas transcribed literally:
  exhaust = area x velocity (area chosen by draft direction: down=plan LxW, cross=end WxH,
  side=side LxH), inlet air +10% for rooms/zones and −10% for booths (nil for side draft, so
  booths stay under suction), 5-side surface area with the floor excluded, oven heat load
  100 ft3 = 12 kW then kW x 860 = kCal. **The two values the document does NOT give are not
  invented**: face velocity falls back to the existing NFPA 33 constant (0.45 m/s), and with no
  ACH the oven exhaust is simply not returned so the caller shows a TBD. **When the draft type
  is unstated the legacy default (WxH) is preserved** — that is what kept the goldens honest.
- **Booth spec now emits catalogue-backed rows**: exhaust blower model, its rated CFM, motor HP,
  drive, plus inlet air volume and enclosure sheet weight. This **replaced the invented
  `FAN_CAPACITY = 13000 m3/h per fan` constant** with real vendor data (and removed the
  "Exhaust fans" row; `rule_covers`/`rule_value_map`/`spec_template` updated to match).
  **Gotcha hit and fixed**: `engineering_planner._match_rule` matches a value label to a rule by
  SUBSTRING, so "Exhaust blower (nos)" matched the "Exhaust blower" rule but "Blower airflow
  (CFM)" did not — and the fallback silently stamps origin **"given"**, i.e. it would have
  attributed vendor catalogue data to the customer. Every emitted value now carries its OWN
  RuleResult with formula + standard. A test asserts only "Dimensions"/"Paint process" lack one.
- **`app/engineering/rate_card.py`** — the client's real rates: MS sheet/plate Rs 85/kg + Rs 45/kg
  fabrication, sections Rs 75/kg + Rs 50/kg, painting Rs 35/sq.ft, motors Rs 3,500/HP, and 21
  named bought-outs at unit price. Three are wired into `pricing_intelligence`, closing that
  part of the standing CLIENT ACTION. The seeded fabrication rate had been Rs 85/kg against an
  actual **Rs 45/kg** (nearly double) and motors Rs 4,500/HP against **Rs 3,500/HP**.
- **Goldens recaptured** (documented, as on 2026-07-26): **only the 3 paint_booth cases move**
  (confidence 81->86%, TBD fields 10->8, rule-backed decisions 4->8); all 4 wet-scrubber and all
  3 knowledge cases byte-identical — that is the proof the change is scoped to the booth path.

**THE KEY UNFINISHED FINDING — read before touching cost-plus.** With the real rates in, the
cost-plus vs history divergence on a paint booth got *worse* (−41% -> −57%). The rates were not
the problem. Breaking down the client's own BOM shows why:
  structural steel 696 kg -> Rs 93,968 (16.5%) | **bought-outs Rs 4,34,876 (76.5%)** | painting Rs 39,690 (7%)
Bought-outs *dominate* a booth (blower 65k, control panel 95k, field wiring 1.15L, LED 38k, view
glass 24k...), and our model represents them as **a flat 15% allowance on works cost**. That —
not the rates — is the divergence, exactly as this file predicted ("cost-plus diverges for
bought-out-heavy gear"). Separately, **two parts of the system now disagree on booth weight**:
the engineering engine computes **1,240 kg** from the client's own formula, the pricing model
guesses **3,645 kg** (SEED 180 kg/m2 x 1.35), and the client's actual BOM shows **696 kg**.
**Deliberately NOT half-fixed**: correcting the weight alone makes the divergence worse, and a
proper booth BOM cost model **cannot be validated** because the supplied BOM image has its first
row cut off (visible lines sum to Rs 5,68,534 vs a stated Rs 6,49,264 — Rs 80,730 unexplained).
**So: ask the client for the COMPLETE cost sheet**, then build a booth BOM cost model off
`rate_card` + the engineering outputs (sheet weight, blower model, motor HP, filter area,
painting area) and validate it against their total before trusting it.

**Still to do from this delivery:** the four remaining paint-shop units (cleaning_room,
buffing_booth, flash_off_zone, paint_drying_oven) have working formulas in
`paint_shop_service` but are **not yet wired as catalog categories** (no `classify.py` keywords,
no profile, no `spec_template`) — that is the natural next increment and is purely additive.

### ▶ 2026-08-01 (standards) — CLIENT STANDARDS PACKAGE IMPLEMENTED (8 of 10 review defects closed)
The client supplied the full engineering-standards package; it is now executable in
**`app/engineering/design_standards.py`** (DATA then SELECTION functions). Six suites green;
goldens recaptured — **only the 3 paint_booth cases moved**, all wet-scrubber + knowledge cases
byte-identical.
**On the reviewed spec (`paint booth 10x10x10 water based side draft`): confidence 87% -> 94%,
TBD fields 6 -> 1 (+1 customer question), zero duplicate rows.**
- **#1 booth vocabulary** — 7 canonical types + synonyms; "side down draft" resolves to Dry
  Filter Side Draft and is flagged as non-standard archive wording.
- **#2 velocity contradiction GONE** — face velocity now comes FROM the booth type, so the
  velocity stated and the velocity that computed the airflow are the same number by construction.
- **#3 material is ADVISORY** — "Recommended GI panels on MS structure ... subject to customer
  approval", origin `advisory`, never asserted.
- **#4 filters** from media velocity (1.0 m/s) + filter area: 125 nos 600x600 (was 60 from the
  `FILTERS_PER_M2 = 0.6` placeholder, now deleted).
- **#5 illumination** lux-based: 18 nos 40 W @ 750 lux (was "20w x 10" copied verbatim from a
  **7x smaller** booth).
- **#7 duct** 1800 mm dia @ 17.7 m/s from transport velocity. **#8 electrical** 103.8 kW MCC,
  Soft Starter/VFD from connected load + 15% spare. **#9 fire** by paint process (NFPA 33 for
  solvent). **#10 material handling** is now a `customer_decision` question, not a blank.
- **New provenance tags** (`standard`, `advisory`, `customer_decision`) in `schema.Origin` +
  `catalog.ORIGIN_LABELS`; the planner keeps a value's own tag instead of forcing "rule".
- **Gotcha:** adding a computed field means adding its historical key to `rule_covers`, or the
  spec emits the row TWICE (once computed, once reused) — hit on booth_type/illumination/filter.
- **STILL OPEN:** #6 dry scrubber (needs Phase C1 field-level retrieval) and Phase E1 validation
  gate / release status. `check_historical()` (±20%) exists but is not yet wired into
  `cross_validate`.

### ▶ CLIENT SPEC REVIEW 8.3/10 — READ `docs/spec-quality-plan.md` BEFORE SPEC WORK
The client engineering-reviewed a generated paint-booth spec (2026-08-01) and scored it
**8.3/10 — "a good engineering draft, NOT ready for customer release"**. Airflow and blower
selection rated **excellent** (5/5); component selection 2/5, engineering consistency 3/5,
customer-ready quality 3/5. **Full findings, root-cause evidence and the phased plan are in
`docs/spec-quality-plan.md`** — read it before touching the spec engine.

**The single root cause** (traced to code + data, not guessed): the engine has only three ways
to produce a field — an engineering rule, a VERBATIM copy from the nearest offer, or a template
TBD. There is no component-selection layer, no cross-validation layer, no standards inference,
and it never re-queries history for a field the template blanked. Two concrete proofs:
- **One reused string caused two of the ten defects.** Offer `OFF-SYNERGY-PB-209R3` stores
  `booth_type = "dry type side down draft, non-pressurized, 0.6 m/s cross velocity"` — one blob
  packing filtration + draft + pressurisation + design velocity. So the spec printed a
  non-standard booth type (which is what the client's OWN archive says — a data-quality issue as
  much as ours) AND asserted 0.6 m/s while `FACE_VELOCITY = 0.45` actually computed the airflow.
  Nothing reconciles them because the velocity sits in prose no code parses. **This is exactly
  the B0b item logged below**, now with a reproducible instance.
- **Reuse is verbatim and UNSCALED.** The 10x10x10 m booth (100 m² face) reused fields from a
  **7.5 x 4.0 x 3.5 m** booth (14 m² face — a **7x** gap), and from a `liquid` booth when the
  requirement said `water-based`. `illumination = "20w x 10 LED"` was sized for the small booth
  and restated as fact for the large one.
- **TBD became the answer, not the last resort.** `dry_scrubber` / `exhaust_duct` /
  `control_panel` are `None` in the source offer, so the template blanked them and stopped —
  even though duct size follows from the 162,000 m³/h we already computed, panel scope follows
  from the 2x60 HP load, and fire protection follows from the paint type. The TBD guardrail
  correctly stops hallucination; it must not stop engineering.

**Plan (phases in `docs/spec-quality-plan.md`):** **A** stop self-contradiction (decompose
compound fields, booth-type vocabulary, `cross_validate` reconciliation, scale-or-refuse reused
values) — **needs no client data, do this first**; **C1** field-level retrieval before TBD;
**D1** customer-decision fields become questions not blanks; **B** a component-selection package
(filters by media velocity, lighting by lux, duct by transport velocity, electrical by connected
load, fire by paint type, material advisory not asserted) — each item lands as its client
standard arrives; **E1** a validation gate reporting "customer-ready vs engineering draft".
**Seven client inputs are listed at the end of the plan doc — chase them alongside the ones
already outstanding.**

### ▶ 2026-08-01 (studio redesign) — premium CAD workspace
`DrawingStudio.jsx` rebuilt as a three-column engineering shell and all its styling moved to a
new **`frontend/src/styles/studio.css`** (`ds-` prefix). The 263 lines of old `.studio-*` rules
are DELETED from `pages.css` — grep there returns 0. React + Vite + vanilla CSS only, no UI
library. Layout: top toolbar (identity, live scale/sheet/TBD chips, export, expand) / left
parameter panel with grouped sections (Quick start, Equipment, Geometry, Title block, Layers,
Legend, TBD, BOM) / **viewport as the primary surface** with a floating tool cluster and status
strip / right AI assistant rail with avatars, typing indicator and suggestion chips. The sheet
renders as lit white "paper" on a dark dotted CAD field with a drop shadow, in both themes.
Studio-local tokens sit on `.ds` so the workspace can be tuned without touching global
variables. Verified in a browser: 3-column grid, form generate, 8 layer toggles, assistant chat,
light + dark, expanded mode, **0 console errors**. Functionality unchanged — the canvas still
renders only backend-generated SVG.

### ▶ 2026-08-01 (lookup fix) — dimension queries answered "no match", then the wrong projects
User report: asking the Engineering Agent "is there any client we worked with Length: 0.9 /
Width: 0.92 / Height: 2" said NO MATCH; pushed again it returned several unrelated records
instead of the one exact project. **TWO independent root causes, both fixed, four regression
checks added to `tests_lookup.py`.**
1. **`retriever._exact_dimension_hit` was GATED on a confident equipment classification**
   (`if not cat or score < CONFIDENT: return []`). A dimensions-only question classifies to
   nothing, and "…0.9 x 0.92 x 2 booth for" classified paint_booth at only score 1 — so BOTH
   skipped the exact-match path and fell through to `_relevant_offer_hits`, which returns a
   relevance CLUSTER (Valv, Innotrans, Armstrong, NewSynergy). That cluster is the "some file
   data, not the exact match" symptom. **Fix: the equipment type now SCOPES the search instead of
   gating it** — a full L×W×H triple matching one offer on every axis is a stronger identifier
   than a category keyword. Without a confident category at least TWO attributes must match, so a
   lone "800" can never pick a project. It now collects ALL exact matches rather than returning
   the first record the store happened to yield.
2. **`understand._fallback` could only read "A x B x C"** — it had no pattern for LABELLED
   dimensions ("Length: 0.9 meters, Width: 0.92 m"). This matters because `_exact_dimension_hit`
   deliberately uses `_fallback` (deterministic, no LLM), so a shape the regex cannot read makes
   the lookup answer "no match" even though `understand()` itself parsed the numbers fine via the
   LLM path. **Fix: `_labelled_dims()`** handles `Length/Width/Height` (and long/wide/high/tall)
   with mm/cm/m units, requiring at least two labels so a stray "height 3" in prose cannot
   masquerade as a dimensioned requirement.
**Verified live end-to-end**: all four phrasings (labelled metres, labelled mm, weak "booth",
and the original "water wall paint booth") now return **Yonex alone**, and the agent answers
correctly on the FIRST ask. Six suites green.
**Lesson for similar reports:** when a lookup "finds nothing then finds the wrong things", check
whether the precise path is gated behind a classification, and whether the DETERMINISTIC parser
understands the user's phrasing — `understand()` passing does not mean `_fallback()` passes.

### ▶ TOTAL-LOSS RECOVERY — `docs/disaster-recovery.md` (audited 2026-08-02)
Answers "what if the VPS vanished". **Audited result: nothing is lost even if the downloaded
tarball is also gone** — GitHub alone rebuilds the platform, agents included. Every entry on
the 11 GB volume falls into exactly one of four buckets (in git / in the tarball / regenerable
/ disposable); the audit found **no uncovered item**. `flowise-package.json` looked uncovered
but is redundant — `flowise-reinstall.sh` (in git) writes the identical pins inline; only a
cosmetic `description` field differs. All 33 offer records are recoverable from the 6 tracked
JSON files, and all thirteen ops scripts were byte-identical to `ops/flowise/`.
**The one thing that changes on a git-only rebuild:** new chatflow IDs, so
`VITE_ENGINEERING_AGENT_ID` / `VITE_QUOTATION_AGENT_ID` / `VITE_DRAWING_AGENT_ID` must be set.
Restoring from the tarball keeps the existing IDs, the Flowise encryption key and the vector
store — minutes instead of hours.

### ▶ MIGRATION SAFETY — `docs/migration-safety-plan.md` (execute this to move off the pod)
The zero-data-loss plan, written to be executed top to bottom with a verification on every step.
**Nothing is deleted from the pod until the new server passes acceptance (§5), so rollback is
always available (§8).** Key points: the **three-copy rule** (GitHub + downloaded tarball + new
server; the pod does not count); of 10.2 GB only ~5 MB is irreplaceable; the agents live in
Postgres, which is the one thing not in git.
**`ops/verify-agents.sh` (NEW)** is what makes GitHub a trustworthy backup — it pulls each LIVE
prompt out of Postgres and diffs it against `ops/flowise/*.py`. If someone tunes a prompt on the
server without mirroring it into git, a rebuild would silently produce older behaviour and
nothing would flag it. **Currently all three match** (9894 / 5370 / 3102 chars). Run it before
migrating and after restoring. It exits non-zero on mismatch, so it can gate a deploy.

### ▶ LOCAL PRODUCTION MOVE — `docs/production-deployment.md` + `docker-compose.prod.yml`
Decided 2026-08-01: move off the RunPod pod to a **local server**. **Phase 1 = office LAN**,
**Phase 2 = LAN + remote staff over VPN**. Hardware will be high-spec with an NVIDIA GPU, so
**`llama3.1:8b` stays** and every prompt tuning session carries over unchanged (changing the
model would invalidate all of it and force re-verifying each agent 3-5x per case).
- **DO NOT deploy the old `docker-compose.yml`** — it is from 2026-07-16 and would fail:
  `flowiseai/flowise:latest` pulls the BROKEN 3.1.x (`@langchain/core@1.1.20`, missing
  `./utils/uuid`); it runs a separate `chroma` service the backend no longer uses (embedded via
  `CHROMA_DIR`) which also steals host port 8000; Ollama's GPU block is commented out; it lacks
  `HTTP_SECURITY_CHECK=false`, without which Flowise's SSRF deny-list blocks the Custom Tools
  from reaching the backend; and it publishes every service.
- **`docker-compose.prod.yml` (NEW)** fixes all of the above: Flowise pinned **3.0.13**, no
  chroma service, GPU passthrough enabled, SSRF settings, healthchecks, `${VAR:?}` on every
  credential so it refuses to start on a default password, and **only the frontend publishes a
  port** (nginx already proxies `/api` -> backend and `/flowise` -> flowise). Postgres and Redis
  bind to 127.0.0.1 only. **Written but NOT executed — there is no Docker on the pod**, so run
  `docker compose -f docker-compose.prod.yml config` on the target server first.
- **The agents live in Postgres**: a fresh `pgdata` volume has NONE and the app looks broken in
  a non-obvious way. Restore `vitech.sql` (drop it in `ops/restore/`, which is gitignored) or
  rebuild from `ops/flowise/*.py`. If a rebuild mints new chatflow ids, set
  `VITE_ENGINEERING_AGENT_ID` / `VITE_QUOTATION_AGENT_ID` / `VITE_DRAWING_AGENT_ID`.
- **BLOCKER FOR PHASE 2 (VPN):** authentication is **frontend-only** —
  `frontend/src/auth/AuthProvider.jsx` validates against a hard-coded list IN THE BROWSER, with
  no auth backend (queue item E1). Anyone who reaches the page can read the JS and sign in.
  Tolerable on a trusted LAN, NOT over a VPN. Also set `API_KEY` and put HTTPS in front.

### ▶ NEXT SESSION — Drawing Agent plan + BACKUP/RESTORE position
**Drawing Agent work plan: `docs/drawing-agent-plan.md` §13.** Ordered: (1) more category
glyphs in `symbols.py` — oven, dust collector, powder coating, conveyor; each is ONE function
plus a registry entry, everything else is inherited; (2) more derived envelopes in
`envelope.py` (dust_collector, ducting) — same one-function pattern; (3) P2 exports, DXF
(decide `ezdxf` vs hand-rolled — the primitives are only lines/text/circles so hand-rolling is
viable) and PDF; (4) BLOCKED on the client: component setting-out rules, until which glyph
positions stay schematic and undimensioned.

**BACKUP POSITION — what actually survives what.** `/workspace` is the persistent volume: it
survives a pod STOP but not a volume TERMINATE. Of the 10.2 GB there, only about **5 MB is
irreplaceable** — Ollama models (9.2 G) re-download, `flowise-app.tar.gz` (1.0 G) rebuilds from
npm, and `chroma/` (6 M) re-ingests from the 33 offers.
- **NOW IN GIT: `ops/flowise/`** — all five agent build scripts (the SOURCE OF TRUTH for all
  three agent prompts) plus `bootstrap-pod.sh` / `start-all.sh` / `pg-backup.sh` etc. They were
  previously only on the volume. They contain no secrets (credentials come from `.env` at
  runtime). With these in git, all three agents can be rebuilt from scratch after a total
  volume loss — see `ops/flowise/README.md` for the restore order.
- **NOT in git, must be downloaded manually:** a **1.5 MB** tarball is written to
  `/workspace/vitech-critical-backup-<date>.tar.gz` containing `postgres-backups/vitech.sql`
  (the live tuned agents), `flowise/secrets/` (the encryption key Flowise credentials are tied
  to — losing it invalidates stored credentials) and `ssh/` (the deploy key; regenerable, just
  re-add the pubkey to GitHub). Recreate it any time with the command in that README.
  **Download it before terminating the volume** (VS Code: right-click the file in the Explorer
  → Download).

### ▶ NEXT SESSION — spec-quality work remaining (2 of 10 review defects + the gate)
Eight of the client's ten review defects are closed (see the 2026-08-01 standards entry).
What is left, in order:
1. **Phase C1 — field-level retrieval before TBD** (closes review defect #6, dry scrubber).
   When `apply_template` is about to emit a TBD, first query history for THAT field scoped to a
   comparable design (nearest airflow for a scrubber, nearest floor area for a booth). Populate
   with the source offer attributed when the match is strong; otherwise keep the TBD. Seam:
   `app/spec_template.py::_tbd_row` is where the decision is made, and `app/retriever.py`
   already has the scoped-search primitives.
2. **Phase E1 — validation gate + release status** (the reviewer's own list). `check_historical()`
   (±20% tolerance) is ALREADY WRITTEN in `design_standards.py` but is **not yet wired into
   `analysis.py::cross_validate`**. Wire it, then add the release-status ladder the client
   specified — Engineering Draft / Customer Review Draft / Customer Ready / Released Design —
   computed from: no contradictory values, no size-dependent value reused across a large size
   gap, no TBD outside the customer-input set, every populated field carrying a source tag.
   Constants for it are in `design_standards.py` (`STATUS_*`, `HISTORICAL_TOLERANCE`).
3. **Phase A4 — scale-or-refuse reused values.** Still open: a size-dependent historical value is
   copied verbatim regardless of the size gap (the 7x illumination case). Mark catalog fields
   size-dependent, then scale via a rule or demote to TBD rather than asserting.
4. Apply the same standards treatment to the other categories (powder coating plant, dust
   collector) once the client sends their two remaining calculation documents.

### ▶ TOMORROW — start here (as of 2026-08-01, end of session; pod running)
State: pod rebuilt from a wiped container disk (`bootstrap-pod.sh` then `start-all.sh`), all 4
services verified 200, golden/lookup/pricing/retrieval ALL PASS throughout. Both carry-over items
from 2026-07-30 are now CLOSED — see the 2026-08-01 entry below for full detail: (1) the
spec_markdown verbatim flakiness is FIXED (verified 15/15 across multiple rounds, no regression)
and PG-backed-up; (2) the frontend chat-history fix is VERIFIED in an actual live browser
(Playwright), all 4 checks pass. **Two NEW pre-existing bugs surfaced** while regression-testing
today's fix (confirmed on the untouched baseline prompt too, so NOT caused by today's edit) —
see items 2 and 3 below; both need their own investigation session.
1. **First**: `bash /workspace/persistent/start-all.sh`; forward 5173/3000/8000. If psql/node
   /ollama are missing (the container disk has been wiped on most restarts), run
   `bootstrap-pod.sh` FIRST — it restores Flowise from the tarball and PG from `vitech.sql`.
2. **NEW: Engineering Agent leaks tool-call-shaped JSON on some general-conversation asks**
   (found 2026-08-01, confirmed PRE-EXISTING — reproduces on the untouched baseline prompt, not
   introduced by today's spec_markdown fix). "hi, who are you?" and "tell me a joke" sometimes
   return literal JSON like `{"name": "answer", "parameters": {...}}` or
   `{"name": "WHO YOU ARE", "parameters": {}}` instead of plain prose — a RULE 1 violation
   ("never write a tool name or JSON like {\"name\": ...}") that RULE 1 already explicitly
   forbids, yet it still happens. Neither "answer" nor "WHO YOU ARE" is a real tool — this looks
   like the Tool Agent scaffold itself occasionally wrapping a plain reply in a fake tool-call
   shape. Rate is non-trivial (seen on both baseline and edited prompts, roughly 1-in-5 to
   1-in-15 depending on test batch — see the note below on why single-batch rates aren't
   reliable). Mirrors the 2026-07-24 Quotation Agent "leaked `greet` tool-call JSON" fix in
   symptom but NOT in trigger (that one was compound greetings only, `hi, who are you?` was
   explicitly verified clean 3/3 on the Quotation Agent) — the Engineering Agent needs its own
   diagnosis. **Gotcha found while chasing this**: rapid-fire consecutive prediction calls
   against the SAME live Flowise process (dozens within a few minutes, even across many
   different fresh `chatId`s) appear to progressively destabilize output — a baseline prompt
   that tested 11/11 clean on this exact question later tested 15/15 FAILING in the same
   process lifetime, and recovered after simply restarting Flowise
   (`kill <pid>; bash /workspace/persistent/flowise-start.sh`). This is distinct from the
   documented per-chatId BufferMemory-poisoning gotcha (new chat rotates chatId; this persisted
   across chatIds). **Lesson for next session**: don't trust a single test batch's pass/fail
   rate, especially late in a long testing session — restart Flowise before a clean diagnostic
   run, and compare matched sample sizes (edited vs. baseline) in the same process lifetime
   before concluding a prompt change caused a regression.
3. **NEW: Engineering Agent's `generate_quotation` path doesn't print `quotation_markdown`
   verbatim** (found 2026-08-01, confirmed PRE-EXISTING on the untouched baseline too). Asking
   the Engineering Agent "quote wet scrubber 800 cfm 750mm tower 4 nos" correctly calls
   `generate_quotation` (right tool, right ₹25,50,000 price, verified via `usedTools` in the raw
   Flowise response) but then paraphrases its own narrative instead of printing the tool's
   ready-made `quotation_markdown` field verbatim the way the Quotation Agent's RULE 4 does — on
   one run it even mislabeled its hand-assembled output "**ENGINEERING SPECIFICATION**" (copying
   the spec template's look) instead of the quotation's own "### VITECH ENVIRO SYSTEMS PVT.
   LTD." heading. The Engineering Agent's prompt has never had a RULE-4-equivalent for its own
   `generate_quotation` tool (only the "PRICES: print ..._display strings verbatim" bullet,
   which is narrower). Fix would mirror RULE 4 on the Quotation Agent, but apply the
   in-place-fold lesson from item 2026-08-01 below rather than a new standalone rule block, and
   retest 3-5x + a Flowise restart between batches (see item 2's gotcha).
4. **Chase the client for a REAL ISSUED QUOTATION.** On 2026-07-26 the ask for "the company
   format" produced three **data sheets** (enquiry/input forms) — useful, and already built
   from, but they do NOT show the offer layout. Word the request as "a quotation you actually
   sent a customer", not "the company format". Then make `quotation_pdf.py`'s section order
   exact (the house *style* is already applied).
5. **Client documents → `retrieve_knowledge` (still the #1 value item, still `count:0`)**:
   `backend/data/bulk/` is STILL EMPTY. When files land: `cd backend && .venv/bin/python -m
   rag.ingest data/bulk --equipment-type X --customer Y`, then `curl -X POST
   localhost:8000/api/admin/reload-index`, then verify the agent grounds + cites.
6. **Engineering calculations — PAINT SHOP DELIVERED 2026-08-01 (see the entry above); two
   categories still owed by the client.** The calculation doc covers **Paint shop Plant only**;
   it states plainly that **Powder coating plant** and **Pollution control Equipment's** will
   follow. **Chase those two.** Also still owed: (a) the **COMPLETE costed BOM** — the supplied
   image has its first row cut off, which is what blocks a validated booth cost model (see the
   KEY UNFINISHED FINDING above); (b) confirmation of the two constants the calc doc omits —
   **face velocity** (we default to the NFPA 33 0.45 m/s already in the engine) and the **ACH**
   for a drying room / oven (no default at all today, so oven exhaust stays TBD by design).
   When the remaining docs land the pattern is established: transcribe into a service under
   `app/engineering/`, cite it in `standards_service`, wire into the catalog profile, and guard
   it in `tests_engineering.py`. **Template labels must match what the engine emits** (gotcha).
7. **No UI for the data-sheet generator yet** — `GET /api/datasheet/forms` +
   `POST /api/datasheet/pdf` work, but nothing in `frontend/` calls them. A picker + Download
   button is a small, high-visibility win.
8. **Drawing Agent is DONE (2026-08-01)** — engine, endpoints, studio UI and the Flowise
   chatflow are all live. What is left there, in value order: **(a) more category glyphs** in
   `app/drawing/symbols.py` — oven, dust collector, powder coating plant, conveyor; each is one
   function, everything else is inherited; **(b) more derived envelopes** in
   `app/drawing/envelope.py` for categories that do not state L x W x H (dust collector,
   ducting) — same one-function pattern; **(c) P2 exports**, DXF (decide on `ezdxf`) and PDF
   (the SVG stays the source of truth). Otherwise: platform upgrades (B1 reranker,
   D1 Qdrant+BGE-M3, D2 DeepSeek R1); B0 / B0b still open below.
9. Before stopping the pod: `bash /workspace/persistent/pg-backup.sh` (agent lives in PG on
   the container disk — the dump on the volume is its only lifeline), and push any commits.

### ▶ 2026-08-01 session: spec_markdown verbatim fix landed + frontend chat-history fix verified live (DONE)
Container disk had been wiped again → `bootstrap-pod.sh` then `start-all.sh`; all 4 services 200,
DB restored 2 chatflows + 5 tools, golden/lookup/pricing/retrieval ALL PASS throughout.
1. **spec_markdown verbatim flakiness FIXED** (Engineering Agent, `agent-harden-prompt.py`,
   applied live + PG-backed-up). **Correction to the 2026-07-30 plan**: `spec_markdown` does
   NOT start with `###` as assumed — it starts with `**ENGINEERING SPECIFICATION**` (verified
   both by reading `app/main.py::_spec_markdown()` and by calling `/api/tools/spec` directly).
   **The planned fix (a new standalone "RULE 3" mirroring the Quotation Agent's RULE 4) was
   tried first and EMPIRICALLY REJECTED**: it fixed the spec case 5/5, but broke a previously
   clean case — "hi, who are you?" started leaking tool-call JSON 5/5, even after trimming the
   new rule down to LESS total prompt length than the last known-stable version (9707 vs. 9754
   chars). That proves char-count alone isn't the safe metric here — inserting a new top-level
   "RULE" between RULE 2 and SMALL TALK destabilized unrelated routing regardless of length.
   Confirmed by reverting to the untouched original prompt and re-testing: clean. **Actual fix
   applied**: folded the same marker + self-check wording INTO the existing SPECIFICATIONS
   bullet under VITECH PROJECT WORK, in place — no new rule number, no repositioning, everything
   before that bullet byte-identical to the 2026-07-30 baseline. This fixed the sentinel case
   (`spec for a paint booth 5m x 3m x 4m`) 15/15 clean across multiple rounds with no new
   regression on greetings/confidentiality/conduct/routing. Net prompt length 9754 → 9894 chars.
   **Reconfirms the existing lesson** ("fold new guardrails into existing rules, never append a
   standalone rule block") — worth remembering that this holds even when the new rule is
   *shorter* than a previously-stable version; position/structure, not just character count, is
   what destabilizes this model.
2. **Frontend chat-history fix VERIFIED in an actual live browser** (queued since 2026-07-30,
   previously only `npm run build`-checked). Playwright + Chromium were not set up on this pod —
   installed fresh via `npx playwright install chromium` + `install-deps chromium` from
   `/opt/flowise-app` (its `node_modules` already had `playwright` as a Flowise dependency); the
   browser + system libs land on the CONTAINER DISK, so this will need reinstalling next time the
   container disk is wiped (not added to `bootstrap-pod.sh` — a small one-command addition if
   browser verification becomes routine). Login needed `admin` / `vitech@123` (the local dev
   account in `frontend/src/auth/AuthProvider.jsx` — there is no real auth backend yet, see
   `E1` below). All 4 checks from the 2026-07-30 queue item PASS: (a) switching Engineering →
   Quotation → Engineering mid-conversation leaves each agent's own transcript exactly as it was,
   not blank/reset; (b) the Chat History panel is correctly scoped per agent — Quotation's panel
   never lists an Engineering conversation and vice versa; (c) clicking a saved history item
   restores that exact transcript (not a new blank chat) — verified by starting a fresh "New
   Chat" (confirmed blank hero-card state) then clicking the earlier item back open; (d) zero
   browser console errors across the whole flow. Screenshots + driver scripts left in the
   session scratchpad, not committed (throwaway verification tooling, not app code).
3. **Two NEW pre-existing bugs found** while regression-testing item 1 above (confirmed on the
   UNTOUCHED baseline prompt too via careful A/B testing, so neither is caused by today's edit)
   — see TOMORROW items 2 and 3 for full detail: (a) Engineering Agent occasionally leaks
   tool-call-shaped JSON (a fake `"answer"` or `"WHO YOU ARE"` pseudo-tool) on general-
   conversation asks like "who are you" / "tell me a joke"; (b) Engineering Agent's
   `generate_quotation` calls the right tool with the right price but doesn't print
   `quotation_markdown` verbatim like the Quotation Agent does — it paraphrases instead. Neither
   is fixed this session (scope was the spec_markdown flakiness specifically); both are queued.
   Also surfaced a **process-level Flowise instability** distinct from the documented per-chatId
   BufferMemory gotcha: heavy rapid-fire testing within one Flowise process lifetime seems to
   degrade output reliability even across fresh chatIds, recovering after a plain restart — see
   TOMORROW item 2 for the lesson (don't trust a single long test batch; restart between batches;
   compare matched sample sizes).
4. PG backed up 2026-08-01 (spec_markdown fix confirmed inside via grep). This CLAUDE.md update
   is the only repo change this session (the frontend fix + its own CLAUDE.md entry were already
   committed 2026-07-30 — working tree was clean at session start); `agent-harden-prompt.py`
   stays outside the git repo by the established convention.

### ▶ 2026-07-30 session: frontend chat-history bugs fixed + agent conversation/confidentiality tuning (DONE)
Container disk had been wiped again → `bootstrap-pod.sh` then `start-all.sh`; all 4 services
200, DB restored 2 chatflows + 5 tools, golden/lookup/pricing/retrieval ALL PASS. Then two
pieces of work, both applied to the LIVE pod (PG dumped 2026-07-30 06:24 with both baked in):
1. **Frontend chat-history bugs FIXED** (`frontend/src/hooks/useAgentChat.js`,
   `frontend/src/App.jsx`). Reported: switching agents and coming back opens a blank new chat,
   history sometimes doesn't load, and Engineering/Quotation conversations look mingled
   together. Root causes, all in `useAgentChat`:
   - A single `sessionId`/`messages` pair was shared across ALL chat views. An effect wiped
     both to a fresh empty chat on EVERY switch between Engineering ↔ Quotation, even switching
     back to an agent you were mid-conversation with — that is the "opens a new chat" report.
   - Worse: `openConversation()` (clicking a Chat History item) set `sessionId`/`messages`
     directly, then the caller changed `view` — which re-triggered the same wipe-on-switch
     effect and immediately overwrote what was just restored, if the opened conversation
     belonged to a different agent than the one active. That is the "history sometimes doesn't
     load" report.
   - On a fresh page load, the single global `ats_session` localStorage key was reused as the
     FIRST message's chatId regardless of which agent view was active — so the very first turn
     after a reload could silently reuse a chatId that belonged to the other agent's last
     session, blending their Flowise memory under one chatId. That is the real mechanism behind
     "mingled all agent conversation in same history", not just a display bug.
   - The Chat History panel also rendered `chat.conversations` unfiltered (both agents' items
     in one undifferentiated list) — a second, purely cosmetic contributor to "mingled".
   **Fix**: replaced the single session pair with a `sessionsByView` map (one slot per agent,
   like separate tabs) so navigating away and back always restores exactly what was there
   instead of wiping it; each view's chatId is now persisted separately (`vitech_sessions`,
   replacing `ats_session`) so a reload can never hand two agents the same chatId;
   `RightSidebar`'s conversation list is filtered to `c.view === view` (`App.jsx`) so each
   agent's Chat History is scoped to itself; and the 20-conversation localStorage cap in
   `persist()` is now applied PER AGENT instead of globally, so heavy use of one agent can no
   longer silently evict the other agent's saved history. Verified with `npm run build` (clean)
   — **not yet exercised in a live browser on the pod**, that's queued as TOMORROW item 2.
2. **Both agent prompts tuned for general conversation** (`agent-harden-prompt.py` for
   Engineering, `quotation-agent-build.py` for Quotation — both `/workspace/persistent/`,
   applied live + re-run against Postgres). Reported: the agent couldn't hold an ordinary
   conversation the way ChatGPT can — reproduced live: "how are you", a joke, simple
   arithmetic, and a translation all got a flat refusal ("outside the scope of Vitech
   equipment") on both agents, and "OFF-TOPIC" was effectively being applied to almost
   anything non-Vitech rather than genuinely sensitive/substantial asks. Fix: replaced the
   narrow "SMALL TALK" line on both agents with a slightly larger "GENERAL CONVERSATION" /
   expanded small-talk block that explicitly permits harmless everyday exchanges (a quick joke,
   simple maths, a short translation, light trivia, "how are you") answered directly and
   briefly, and narrowed "OFF-TOPIC" to what should actually be declined (politics,
   medical/legal/financial advice, a substantial unrelated task) — a single light question is
   now explicitly NOT off-topic. Only this block was touched; RULE 2/3 tool-routing, the
   KNOWLEDGE QUESTIONS grounding logic, RULE 4/4b/5/6 and the VITECH PROJECT WORK rules are
   byte-identical to before. Verified 6 general-conversation cases live across both agents
   (joke/maths/translation/"how are you"/greeting/off-topic), all natural and correctly scoped;
   no JSON-leak regression on greetings on either agent. (Corrected below: the "spec generation
   unaffected" claim from this pass turned out to be wrong — see item 3.)
3. **Confidentiality + conduct guardrails added** (same two scripts, later the same session,
   after the user flagged the agent reciting its internal architecture/tool names when asked
   "give me your workflow and architecture" — reproduced live: it listed `generate_quotation`,
   `lookup_project`, `retrieve_knowledge` by name and described the pipeline). Added to RULE 1
   on both agents: never describe your own tools/database/architecture, even in plain prose
   with no tool names shown — if asked how you work, say it is confidential and give only the
   WHO YOU ARE line. Added a CONDUCT clause (abusive/vulgar/sexual content → decline in one
   line, do not engage) folded into the existing OFF-TOPIC (Engineering) / SMALL TALK
   (Quotation) block rather than as new standalone rules.
   **Hit real prompt-length instability while tuning this** — worth recording since it
   contradicts the "just keep it under ~7.4k" heuristic from 2026-07-24: stacking the
   confidentiality+conduct text on TOP of the already-larger general-conversation block pushed
   Engineering's prompt to 10,001–10,543 chars, and at that size it reproduced BOTH known
   failure modes at once, live: a bare `{"name": "None", "parameters": {}}` JSON leak on a
   plain question, and a full persona drift ("I'm a helpful assistant with tool calling
   capabilities" — not the Vitech identity at all). Fix was to trim, not append: reverted
   General/Small-Talk back to a terser form and folded confidentiality into RULE 1 + conduct
   into OFF-TOPIC/SMALL-TALK (no new standalone rule blocks), landing at Engineering 9,373 →
   **9,754** chars and Quotation 4,918 → **5,370** chars. Re-verified 3-5x per case (not just
   once — single-run "PASS" was exactly what missed this): greetings clean, confidentiality
   declines cleanly on both agents, conduct declines cleanly, general conversation (joke/maths/
   translation) all correct, RULE 4/4b/6 on Quotation unaffected.
   **Discovered separately, NOT caused by these edits — reproduces even on the untouched
   baseline**: `generate_specification`'s "print spec_markdown verbatim, starting with `###`,
   no preamble" instruction (VITECH PROJECT WORK → SPECIFICATIONS rule) is genuinely flaky on
   Engineering Agent — repeated identical calls at temperature 0 sometimes return the correct
   verbatim table and sometimes a paraphrased bullet list prefixed "Based on the tool's
   output..." (violates RULE 1). **The underlying VALUES were correct in every run** (all
   fields, all "To be determined" rows preserved exactly) — this is a formatting/RULE-1-wording
   compliance gap, not a hallucination or golden-rule-2 violation, and golden/lookup/pricing/
   retrieval tests (which call the Python engine directly, not through the LLM) are unaffected.
   Left open for a future session: it is unclear whether this is fixable via more prompt
   emphasis (risky, given the instability just found) or is an inherent llama3.1:8b limit that
   needs the RULE 4-style structural fix already used for quotations/lookups (render the full
   reply in code and have the agent print ONE field verbatim) applied to specs too.
4. **Clarified the Engineering vs Quotation Agent distinction** (the user asked "if the
   Quotation Agent can give client details AND technical specification, what's different from
   Engineering Agent?"). Reproduced both cases live: a bare technical/design question ("what
   materials should be used for a wet scrubber and why") correctly hands off to Engineering
   Agent (RULE 6, unaffected by today's edits). A NAMED-CLIENT lookup ("give me client details
   for Armstrong") correctly returns `lookup_markdown`, which includes a "Technical details
   (the engineered solution)" section BY DESIGN — that is reporting a past project's
   already-engineered fields, not the Quotation Agent doing new engineering, and Engineering
   Agent's own lookup_project returns the identical section. The real split: Engineering Agent
   is the only one that can build a NEW spec for a fresh requirement (`generate_specification`,
   Consulting or ATS mode, TBD gap-fill, geometry) or answer general engineering knowledge
   questions; Quotation Agent's technical content is always either (a) inside a quotation's
   Technical Specification table (commercial framing, always priced) or (b) a past record's
   technical fields via lookup — never a new engineered answer from scratch.
- **NOT YET COMMITTED/PUSHED** — `CLAUDE.md`, `frontend/src/hooks/useAgentChat.js`,
  `frontend/src/App.jsx` are modified but uncommitted as of end of session; the prompt scripts
  under `/workspace/persistent/` are outside the git repo by design (same pattern as every
  prior prompt-tuning session) but ARE captured in the fresh `vitech.sql` dump (2026-07-30
  06:48, confidentiality/conduct rules confirmed inside).

### ▶ 2026-07-24 session: agent testing + Quotation Agent prompt tuning (DONE)
Container disk had been wiped again; ran `bootstrap-pod.sh` then `start-all.sh` — all 4
services verified 200, DB restored 2 chatflows + 5 tools, golden 10 / lookup 12 / retrieval
16 ALL PASS. Then live-tested both agents with varied real prompts (Mode A/B routing,
enumeration, content-relevance lookup, revise/compare flows, small talk) and found + fixed
**two reproducible bugs** in the **Quotation Agent** (Engineering Agent was clean):
1. **Missing quotation on first ask**: "quote wet scrubber 800 cfm 750mm tower 4 nos" on a
   fresh chat reliably (3/3 runs) returned a generic "This is the quotation... as per your
   requirement" sentence with **no price and no quotation_markdown block**, even though the
   tool returned it correctly. Root cause: the "output quotation_markdown verbatim" rule was
   the 3rd bullet under "QUOTATION WORK", buried below several other rules — llama3.1:8b
   wasn't reliably obeying it. **Fix**: promoted it to a top-level "RULE 4" right after RULE
   3, with a concrete pattern-match cue (the literal `### VITECH ENVIRO SYSTEMS...` starting
   string) and an explicit self-check ("if your sentence doesn't start with ###, stop and
   paste the field instead"). Verified 3/3 fresh chats now emit the full block with the
   correct price; revise/compare flows re-verified still correct after the change.
2. **Leaked tool-call JSON on compound greetings**: "hello there" / "hi, who are you?" (but
   NOT single-clause "hi" or "who are you?" alone) returned the literal text
   `{"name": "greet", "parameters": {}}` to the user — reproduced on brand-new UUID chatIds,
   so NOT the known BufferMemory-poisoning gotcha (that needs a fresh chat, which this was).
   RULE 1 already said "never output JSON like {...}" but wasn't concrete enough. **Fix**:
   added an explicit named anti-example to RULE 1 ("if greeted, reply in a plain sentence...
   NEVER output a tool-call-shaped JSON stub... a reply that begins with a curly brace is
   always wrong"). **Gotcha hit while editing**: an intermediate version added a literal
   `{"name": "greet", "parameters": {}}` example directly into the system prompt string and
   Flowise's chatflow build threw `Error: Single '}' in template` (500) — the prompt is
   loaded into a template engine that chokes on certain literal brace patterns (nested/
   matched empty `{}` in particular). Fix: describe the anti-pattern in words, no literal
   braces in the prompt text. Verified 6/6 across repeated fresh chats after the reword.
   **If tuning either agent's prompt again and need to show a literal JSON example, avoid
   raw curly braces in the system prompt string — describe it instead or the chatflow build
   will 500.**
Both fixes are in `/workspace/persistent/quotation-agent-build.py`'s `SYS` string (already
applied to the live chatflow + `pg-backup.sh` run afterward, 2026-07-24 06:44). If the pod
is rebuilt from `vitech.sql`, the fix is already baked into the restored dump; the `.py`
script is only needed for a from-scratch rebuild.

### ▶ 2026-07-24 (continued) — engine correctness + spec-template foundation + UI (DONE)
Big session. All committed+pushed on `fix/list-projects-category-filter`; golden 10 / lookup
12 / retrieval 16 stayed ALL PASS throughout; PG backed up 08:40 (hardened prompt in the dump).
1. **Paint booth filtration bug FIXED** (commit b307ff1). An agent-generated paint-booth spec
   contradicted itself (water-wash/SS304 from the rule engine vs a reused DRY booth). Root
   cause: `PROCESS_RULES["liquid"]` = SS304/water-wash, but **13 of 14** Vitech booths are
   dry-filter/MS. `material_service.py` now defaults liquid-family paint to **dry/MS**, water-
   wash only when the booth type says so; `booth_type` threaded through `compute_spec`.
2. **Hot air oven hallucination FIXED** (commit 7bd33f6). The oven spec showed INVENTED numbers
   badged "Deterministic" (tool returned category=conveyor, 0 rows). Fixes: (a) `classify.py`
   recognises "bake oven" + a "conveyorized oven is an OVEN not a conveyor" boost; (b) marked
   `hot_air_oven` **`case_based`** so the router builds it in DATA mode by REUSING the nearest
   historical oven (OFF-SURFACE-OVEN-356R3) deterministically; (c) param aliases
   (max_operating_temp_c→operating_temp, hook_load→job_weight_kg, fuel_type→heating_mode).
3. **Spec-template foundation BUILT** (commit 2814c5e) — the client's stated goal ("generate a
   spec for every equipment type; look up project, reuse what exists, CALCULATE the gaps, then
   generate a 2D drawing"). Three pieces, all deterministic, category-agnostic:
   - **`app/spec_template.py` + `spec_template` in catalog**: per-category canonical output-field
     list; `apply_template` (in `analysis.py`) fills every uncovered field with an explicit
     **`origin:"tbd"`** row. Opt-in (no template = unchanged). `hot_air_oven` is the reference impl.
   - **Deterministic guardrail**: TBD rows fill the vacuum that caused the hallucination; the
     Engineering Agent prompt now keeps "To be determined" verbatim (never guesses).
   - **Structured geometry** (`main.py::_spec_geometry`, `/api/tools/spec`→`geometry`): numeric
     mm envelope + per-dimension status for the future 2D-drawing generator (real dims only).
   **HOW TO EXTEND when the client uploads calcs/data** (see "The engine" §): add the category's
   `spec_template` field list + wire its formulas into `formula_service.py`; TBDs then compute.
4. **Frontend** (commits 8b4b2e1, bb7529d, 631a095): merged the chat header into the surface
   then made chat **header-less (ChatGPT-style)** — thin 50px top strip with only theme/
   fullscreen/panel controls; hero + quick-actions **collapse on first message**; markdown now
   renders nested `+` sub-bullets; tighter top/bottom spacing. Verified in-browser (Playwright).
- **STATUS / next**: user said **HOLD on adding templates for the other categories until they
  upload the engineering calculations + field lists.** When those land: per category, add its
  `spec_template` + formulas (see §3). Also fold in the client's note that an oven spec must
  distinguish **hook load** (kg/hook) from **production capacity** (hooks × load) — a label fix
  in the oven template. Follow-ups B0 (filtration-aware booth matching) + B0b (reconcile a
  client attribute like LPG vs a reused diesel design) still open below.

### ▶ 2026-07-26 session: agent routing fixes + client data sheets landed (DONE)
Container disk was wiped again → `bootstrap-pod.sh` then `start-all.sh`; all 4 services 200,
DB restored 2 chatflows + 5 tools. Then two pieces of work, both committed on
`fix/list-projects-category-filter`; golden/lookup/pricing/retrieval ALL PASS throughout.
1. **Quotation Agent misrouting FIXED** (commit ed3b7f6). Reproduced by replaying multi-turn
   chats against the live agent. (a) A stated requirement went to `lookup_project` instead of
   `generate_quotation` — "specification for a paint booth 5m x 3m x 4m" hit lookup with no
   client named, because RULE 3 never mentioned "specification" and RULE 6 listed "dimensions"
   as a technical hand-off, fighting the quote rule. (b) A bare follow-up "generate quotation"
   lost the requirement already stated in the chat ("for the same" worked, "generate quotation"
   alone did not) — which is why a **fresh chat behaved better**. (c) Root of the visible
   symptom: on a lookup the model **hand-wrote** a `### VITECH ENVIRO SYSTEMS PVT. LTD.` header,
   dressing an archive record as a quotation. Prompt wording alone did NOT hold, so it is fixed
   **structurally**: `analytics.render_lookup_markdown()` renders the record in code (headed
   **"Historical Project Found"**, sections Requirement / Engineered Solution / Commercial /
   Source), `/api/tools/lookup` returns it as **`lookup_markdown`**, and new **RULE 4b** makes
   the agent print that field verbatim so it composes nothing. This also delivers the queued
   "lookup output template" item. Prompt 4250 → ~4.9k chars (still far under the ~7.4k where
   llama3.1 leaks tool-call JSON); greetings re-verified clean 3/3.
2. **Client data sheets received** (commit 872795d) — 3 PDFs: painting plant, powder coating
   plant, dust collection equipment. **They are ENQUIRY forms, not quotations**, so they do NOT
   define the issued-quotation layout (still not supplied). What they gave:
   - **House document style** → `quotation_pdf.py` restyled: centred underlined title, numbered
     `1.0/2.0` underlined sections, `Label : Value` rows with an aligned colon column, bordered
     grid tables, exclusions/notes/assumptions, closing contacts. **Confidence removed from the
     customer PDF** (matches the markdown's customer-facing stance + the agent's own rule).
   - **Per-category field lists** → `spec_template` + `field_labels` for **paint_booth**,
     **dust_collector**, **powder_coating_plant** (this was the CLAUDE.md HOLD item). **Gotcha:
     template labels MUST match what the engine actually emits** or the row appears twice —
     once resolved, once as a phantom TBD (hit with "Exhaust airflow" / "Dimensions").
   - **NEW `app/datasheet_pdf.py` + `POST /api/datasheet/pdf` + `GET /api/datasheet/forms`**:
     generates the enquiry data sheets themselves (blank or prefilled) on the letterhead, with
     vector tick-boxes and the client's yellow highlighter on ticked options. Forms are declared
     as data in `FORMS` — adding an equipment type is a schema entry, not drawing code. A bare
     prefill label fills its FIRST occurrence; qualify as `"<section>::<label>"` for a repeat
     (labels like "Material Handling" appear in several sections).
3. **Confidence bug FIXED** (in 872795d, found while templating): `analysis.py::_confidence`
   counted a **`tbd` row as a rule-backed decision** (it fell through `origin not in
   ("reused","kept")`), so **adding admitted gaps RAISED confidence** — templating paint_booth
   pushed it 84% → 90% with 9 fields unknown. TBDs are now excluded from `backed` but stay in
   the denominator, so unknowns dilute coverage (that case is now 82%, with a note naming the
   open fields). Latent since spec templates were introduced (only `hot_air_oven` had one and it
   is not in the ATS goldens). **`tests_golden.json` was recaptured** — the 3 paint_booth ATS
   cases change (template order + TBD rows + corrected confidence); all 4 wet-scrubber cases
   stayed byte-identical, which is the proof the confidence fix touches only TBD specs.
- **STILL NEEDED FROM THE CLIENT**: a real **issued quotation** (the data sheets are input
  forms). Until then the quotation PDF body is house-styled but its section order is our best
  guess. Also still open: the engineering **calculations** per category — the new templates
  resolve what history/rules cover and honestly show the rest as TBD.

- [x] `git pull` DONE (2026-07-23): merged origin/main into fix/list-projects-category-filter
      (conflict in main.py resolved for the agent_router extraction), golden ALL PASS.
- [x] Stack restarted DONE (2026-07-23): container disk was WIPED, so ran `bootstrap-pod.sh`
      first (uncovered + FIXED the flowise-components version-drift + `lunary` bugs — see the
      Flowise section) then `start-all.sh`. All 4 services 200; agent verified (Mode A + tools).
- [ ] Verify the frontend redesign renders on the pod (glass shell, blueprint bg, hero
      card, header→workspace spacing) in both light+dark once it's serving. **Code + build
      verified** (no vite errors; HeroCard/glass/blueprint present) — only the visual
      light/dark eyeball remains, do it in the forwarded browser.
- [x] **spec → Download PDF** VERIFIED on the pod (2026-07-23): `POST /api/specification/pdf`
      returns a valid 1-page PDF (fpdf2 2.8.7 installed here, unlike local Windows), correct
      content-type/filename, deterministic content (800 CFM → 1359 CMH), latin-1 clean.
- [x] **source-file open** VERIFIED on the pod (2026-07-23): `GET /api/offers/by-source/{file}`
      resolves the extracted record on exact, basename, and case-insensitive matches.
- [~] **Phase 3 ingestion** (highest value): pipeline VERIFIED READY on the pod (2026-07-23)
      — ran an isolated end-to-end self-test (ingest .txt → metadata resolve → embed →
      filtered retrieve score 0.789 → facets → cleanup back to 33), so `rag.ingest` works the
      moment real files land. **BLOCKED on input files**: `data/bulk/` is empty and there are
      no documents to ingest (won't fabricate engineering standards — that would inject fake
      authoritative content). Drop real docs (.pdf/.docx/.xlsx/.json/.txt/.md) in
      `backend/data/bulk/` then `cd backend && .venv/bin/python -m rag.ingest data/bulk
      --equipment-type X --customer Y`. Until then `retrieve_knowledge` stays `count:0`.
- [ ] After ANY agent/prompt change: `bash /workspace/persistent/pg-backup.sh` before stopping.

Backend next-phase (sequenced; full detail + rationale in local memory
`backend-next-phase-plan`). **Every engine change: run `tests_golden.py` before AND after —
must stay ALL PASS.** Pod-side unless marked LOCAL:
- [ ] B0b. **Reconcile a client-given attribute that conflicts with a REUSED design**
      (found 2026-07-24, generalises B0). Case-based reuse (paint booth Track A kept-fields,
      hot air oven Track B) does not honour/flag a client requirement that contradicts the
      reused categorical field. Examples: customer asks **LPG fired** but the nearest oven
      (OFF-SURFACE-OVEN-356R3) is **diesel** — the tech table shows "diesel fired ..." (only 2
      historical ovens exist, neither LPG); paint-booth water-wash request reuses a dry booth's
      booth_type. Both are honestly attributed + Low confidence, but should either override the
      fuel word / booth_type from the requirement or emit a cross-validation "confirm: customer
      requested X, nearest design is Y" note. `analysis.py::cross_validate` is the natural seam.
- [ ] B0. **Filtration-aware paint-booth matching** (found 2026-07-24). `retriever.py`
      picks the nearest paint booth by DIMENSIONS only, not by filtration type. Vitech has
      1 water-wash booth (OFF-YONEX-PB-367) vs 13 dry — so a water-wash REQUEST ("wet cross
      draft"/"water wall") reuses a DRY booth's categorical fields (booth_type "dry type...",
      paper_filter, dry_scrubber) which then contradict the rule engine's water-wash/SS304.
      The common DRY case is already coherent (fixed in b307ff1: liquid→dry/MS default). Fix:
      score offers on filtration match (wet vs dry) as well as size, OR in `generate_spec`
      Track A suppress dry-only reused fields when the design is water-wash. Guard with a new
      golden case for a water-wash booth. Also: Track A does not honour a client-given
      categorical `booth_type` over the reused one (Track B does) — same file.
- [ ] B1. Add a **BGE cross-encoder reranker** to `rag/retrieve.py` (top-20 → top-5),
      new `rag/reranker.py` — biggest quality win, no migration. (needs models; do after A2 ingest)
- [ ] B2. Add a **Redis cache** for embeddings/retrieval (Redis already runs, unused today).
- [x] C1 DONE (2a60dd3): `_prepare`+`_meta` → `app/agent_router.py`, golden ALL PASS.
- [x] C2 DONE (2026-07-23): the spec-generation calc/formula/material engine
      (`generate_spec` + `_interpolate`/`_scale`/`_snap`/`_ratio`/`_support_count`/
      `_match_rule` + the `_num`/`_fmt`/`_given`/`_tech` primitives) → `app/engineering_planner.py`.
      `analysis.py` now orchestrates matching/confidence/presentation and imports the engine;
      dependency runs one way (analysis → engineering_planner, no cycle). Golden ALL PASS,
      verified byte-identical live via `/api/tools/spec` (conf 88%, 16 rows).
- [x] C3 DONE (2026-07-23): Ollama HTTP transport (`_opts`/`_ollama_chat`/`_ollama_stream`/
      `warmup`) → `app/ollama_client.py`; `llm.py` is now purely the plan+run answer layer.
      `main.py` warmup import repointed to `ollama_client`. Golden ALL PASS.
- [x] (C-followup) DONE (2026-07-23): the calculation kernel in `rules.py` was decomposed
      into the target `app/engineering/` package per the client architecture diagram:
      `unit_converter.py` (CFM->CMH factor table), `calculation_engine.py` (round/count/snap
      primitives), `standards_service.py` (governing-standard strings), `material_service.py`
      (process->material matrix), `formula_service.py` (design constants + `compute_spec`/
      `compute_wet_scrubber`, composing the four). `engineering_planner.py` moved INTO the
      package. `rules.py` is now a compat shim re-exporting the two formula fns. Golden ALL
      PASS, verified live (wet scrubber conf 88, paint booth conf 84). **Client-extension
      points** are the design constants in `formula_service.py`, the factor table in
      `unit_converter.py`, the standards in `standards_service.py`, and the matrix in
      `material_service.py` — "the client will provide details" slots into exactly these.
- [ ] D1. **Qdrant** replaces embedded Chroma + re-ingest with **BGE-M3** = full re-embed
      (invalidates existing vectors — embedding-model-match gotcha).
- [ ] D2. Model swap to **DeepSeek R1** — FIRST confirm it advertises `tools` in Ollama;
      llama3.1:8b stays the fallback.
- [ ] E1. `permission_filter` (needs a user/role/ACL model — none today). E2. Teams/Slack/
      mobile/REST channels (each its own auth + delivery surface).

## Current state (Engineering Agent LIVE on the RunPod pod)
- **Backend**: FastAPI in `backend/app/`, embedded **ChromaDB**, **Ollama** (`qwen2.5:3b`
  locally; `llama3.1:8b` on the GPU VPS — must be a **tool-capable** model, base
  `llama3` is NOT, so the Flowise Tool Agent can't call tools with it).
- **Frontend**: React + Vite in `frontend/`. Multi-agent UI, 3 agents: **Engineering**,
  **Quotation**, **Drawing** (roadmap) + **Knowledge Base** and **Upload** pages.
  Both the Engineering AND Quotation chats are wired to their **Flowise agents**
  (the chat is agent-aware: `agentUrl(view)` picks the id by nav view; switching
  between them starts a fresh session). Other pages still call the backend directly.
  The old deterministic `QuotationPage` form component is retained but no longer routed.
  The **Knowledge Base** page is organised (Priority 2): stats strip + collections
  taxonomy (Historical Projects live; Standards/Specs/Quotations/Drawings/Vendor
  Catalogues structured + ingestion-ready; Engineering Rules from the engine) +
  equipment facet chips + searchable table, all fed by `/api/knowledge/overview`.
  **Database Visibility (Priority 5)**: collection cards are clickable and there is a
  "Database" nav group; each opens a `CollectionPage` (breadcrumb + stats + last-updated
  + search/filters). Historical Projects is the populated table; the empty collections
  get a professional state-aware panel (ingestion-ready → Upload; on-demand → open the
  relevant agent; Rules → lists the 10 rule-backed equipment types). Sidebar has per-item
  icons + live/soon status dots (Priority 4).
- **Flowise**: pinned + patched `3.0.13` at `/opt/flowise-app`, Postgres-backed, with
  **THREE** chatflows built and verified end-to-end: **Engineering Agent**,
  **Quotation Agent** and **Drawing Agent** (`f486d388-d032-44bb-acb5-db9dad3b950d`,
  built 2026-08-01 by `/workspace/persistent/drawing-agent-build.py`).
- **Data**: 33 real Vitech offers in `backend/data/offers/*.json` (hand-extracted).
  Record schema: `{id, category, client, vendor, ref, date, source_file,
  given_data{}, technical_details{}, price_schedule{}}`.

## The engine (the valuable, reusable core)
- **One resolver, two policies** (`app/spec_schema.py` `Policy`): **Consulting**
  (knowledge mode — reason from engineering knowledge, defer unknowns to "To Be
  Determined") and **ATS** (data mode — build from historical offers). Impl:
  `app/resolver.py` + `app/analysis.py`.
- **Routing** (`app/agent_router.py::prepare`, re-exported as `_prepare` in `main.py`;
  extracted in C1): default is Consulting (reason, don't copy). Data mode only when the
  user says "refer db" OR the category is **adaptable** (has engineering rules / scaling).
  Non-adaptable categories reason from knowledge.
- **Engineering Intelligence** (`app/engineering/` package): the deterministic calc core,
  decomposed per the client architecture. `engineering_planner.py` (orchestrator: builds
  each traceable spec value — origin/reason) sits atop the calc sub-services:
  `formula_service.py` (design constants + `compute_spec`/`compute_wet_scrubber`),
  `unit_converter.py` (CFM→CMH etc.), `calculation_engine.py` (round/count/snap),
  `standards_service.py` (governing standards), `material_service.py` (process→material).
  `app/rules.py` is a back-compat shim → `formula_service`. `analysis.py` orchestrates
  matching/confidence/presentation around the planner.
- **Spec templates + TBD gap-fill** (`app/spec_template.py`, added 2026-07-24): a
  per-category **`spec_template`** in `catalog.py` (ordered `{label, kind}` list) defines
  the OUTPUT fields a complete spec must have (`kind` ∈ geometry/computed/standard/text).
  `apply_template` runs in `analyze()` after `generate_spec`: resolved rows appear in
  template order and every uncovered field becomes an explicit **`origin:"tbd"`** row
  ("To be determined — needs engineering input"). This is the **deterministic guardrail** —
  a gap is shown AS a gap so the LLM never fills a vacuum (the oven-hallucination root cause).
  **Opt-in**: no template = unchanged (booth/scrubber/golden untouched). `hot_air_oven` is the
  reference impl. **The Engineering Agent prompt keeps "To be determined" verbatim** (never
  guesses) — in `agent-harden-prompt.py`. **HOW TO EXTEND when the client uploads calcs/data:**
  (1) add the category's `spec_template` field list to its catalog profile; (2) wire its
  formulas into `formula_service.py` (+ `field_rules`/`rules` in the profile) so `computed`
  fields resolve instead of showing TBD; the geometry/reuse plumbing needs no further change.
- **Structured geometry for 2D drawings** (`main.py::_spec_geometry`, `/api/tools/spec` →
  `geometry`): a machine-readable numeric **mm envelope** + per-dimension status the drawing
  generator consumes (the prose table is for humans). Real numeric dims only — an unknown
  dimension is `tbd`, never guessed. Populates when dims are given (booth 5×3×4 →
  5000×3000×4000 `ready:true`), `tbd` when not (oven). Fills as calcs land (keep their
  outputs numeric here). Per-row `status`/`kind` also exposed on the tool response.
- **Pricing**: `app/pricing.py` — nearest priced offer normalised **per-unit**,
  scaled by the sizing driver, cross-checked against a size→price trend, ±range +
  confidence. This figure stays the **recommended headline** (verified quotes never move).
- **Pricing intelligence** (`app/pricing_intelligence.py`, added 2026-07-24 — "how the
  amount is fixed"): layers **three deterministic signals** on top of the historical
  headline and reconciles them (golden rule #2 holds — numbers from code + history + seeded
  constants, the LLM only explains): (A) **historical scaling** (the anchor), (B) **cost-plus
  build-up** = material + fabrication + bought-outs + overhead + margin from `SEED_*` tunable
  constants (weight = driver × `SEED_KG_PER_DRIVER`), (C) **market benchmark** = ₹-per-driver
  band across priced offers + positioning (**aggressive / market / premium**). `analyse_pricing`
  returns `position`, `rationale`, `flags` (fires when cost-plus vs history diverge ≥30% — a
  *tuning signal*, not a bug), and `basis_markdown` (internal "Pricing Basis" block). Attached
  to the quote as `pricing_intelligence` / `pricing_basis_markdown` — **advisory, NOT printed in
  the customer `quotation_markdown`**. Quotation Agent **RULE 5** presents the basis only when
  the user asks why/margin/market/how-competitors-price. **CLIENT ACTION: the `SEED_*` rates are
  industry defaults — replace with the real rate card / margin policy; until then cost-plus
  diverges from history for bought-out-heavy gear (booth/DC) and the flag says so.** Guarded by
  `tests_pricing.py`.
- **Quotation**: `app/quotation.py` (assembly) + `app/quotation_pdf.py` / `app/specification_pdf.py`
  (fpdf2 PDF). Both PDFs now render the **official Vitech data-sheet letterhead** via the shared
  `app/vitech_letterhead.py` (added 2026-07-24): logo + "VITECH ENVIRO SYSTEMS PVT. LTD" +
  Chennai address header on every page, vertical green tagline banner, green footer band
  (office/factory/tel/e-mail), and a "For any assistance, please contact" block (Mageswaran /
  Sam Mohan) — matching the client's uploaded data sheets. Logo asset: `app/assets/logo.png`.
  Row helpers pre-measure with fpdf `dry_run` so table rows never split across a page break.
  The **quotation PDF body follows the client's data-sheet house style** (2026-07-26): centred
  underlined title, numbered `1.0/2.0` sections, `Label : Value` rows, bordered grids; it shows
  **no confidence** (customer-facing).
- **Enquiry data sheets** (`app/datasheet_pdf.py`, added 2026-07-26): regenerates Vitech's own
  requirement-capture forms (painting plant / powder coating plant / dust collection equipment)
  on the letterhead — vector tick-boxes, highlighted selections, component-matrix + pretreatment
  grids. `GET /api/datasheet/forms` lists them; `POST /api/datasheet/pdf` renders one blank or
  prefilled. Forms are DATA (`FORMS` dict) — a new equipment type is a schema entry, not code.
- **Deterministic analytics + record lookup**: `app/analytics.py` (exact counts /
  lists / clients; `record_detail` renders one file's extracted fields). **Project lookup**
  (`app/retriever.py`, fixed 2026-07-23): `entity_hits` keys on CLIENT IDENTITY + offer-id
  only (word-boundary) — NOT title words, so "water wall **paint booth**" no longer matches
  every paint/booth/conveyor offer. `structured_project_hits` handles no-client queries by
  equipment type + dimensions (deterministic, exact match returned alone), e.g.
  "0.9 x 0.92 x 2 water wall paint booth" → the one Yonex booth (exact-dimension path).
  Otherwise `_relevant_offer_hits` does a **content-relevance search over the offers**
  (semantic vector fused with query-term overlap, then a gap-cut so only the cluster near
  the top score is returned — never a whole-category dump, so it scales to thousands of
  files). This finds Armstrong (category=conveyor) for "paint booth conveyor improvement"
  by what the project IS, not by crude category classification, and lists the oven clients
  for "hot air oven ...". `project_hits` = named first, else structured. `list_projects`
  scopes on a literal category mention too (e.g. "how many clients for conveyor" → 1, not
  all 33), not just a confident classification. Guarded by `tests_lookup.py`.
- **Support**: `app/validate.py`, `app/ledger.py`, `app/catalog.py` (category
  profiles + `required_inputs`), `app/understand.py` (intent + param extraction),
  `app/llm.py` (plan_answer, answer layer), `app/ollama_client.py` (Ollama transport,
  extracted in C3), `app/prompt.py` (system prompts).
- **Retrieval Engine** (`rag/` package, multi-stage as of 2026-07-23): `retrieve_documents`
  runs **cache → vector over-fetch (+ broaden) → permission filter → hybrid rerank → chunk
  select → cache**. Sub-services: `cache.py` (Redis + in-proc LRU, version-invalidated on
  ingest), `reranker.py` (RRF fusion of dense + BM25-lite lexical + metadata boost + lexical
  magnitude — model-free, cross-encoder-ready interface), `chunk_selector.py` (dedup +
  per-doc cap), `permissions.py` (`Principal`/role filter, allow-all default + restricted-
  category hook), `citations.py` (one per source, numbered), `response_formatter.py`
  (budgeted numbered context). `/api/tools/retrieve` now returns `citations` + `context`.
- **Blower selection** (`app/engineering/blower_service.py`, added 2026-08-01): the client's
  vendor chart (Continental Thermal, direct drive — 203 models / 21 pressure classes) as data.
  `select_booth_blower(cfm)` returns a REAL catalogue model or None (never an interpolated
  machine), pinned to the **CLP-4 pressure class** Vitech actually builds booths around;
  `select_booth_blower_set` splits across N machines beyond the largest model. Reproduces the
  client's own costed BOM line exactly (9000 CFM -> `CLP-4-10-9000`, 10 HP) — that is the anchor
  test. This supersedes the old invented "13000 m3/h per fan" constant.
- **Paint-shop calculations** (`app/engineering/paint_shop_service.py`, added 2026-08-01):
  the client's own design document, transcribed literally — exhaust = area x velocity with the
  area chosen by draft direction, inlet air +10% (rooms/zones) / −10% (booths) / nil (side
  draft), 5-side surface area (floor excluded) -> sheet weight, and the oven's 100 ft3 = 12 kW
  heat load. Values the document omits are NOT invented (see the CLIENT-CONFIRMATION slots).
- **Rate card** (`app/engineering/rate_card.py`, added 2026-08-01): Vitech's real ₹/kg, ₹/HP,
  ₹/sq.ft and bought-out unit prices from their costed BOM; feeds `pricing_intelligence`'s
  cost-plus model in place of the seeded industry defaults.
- **2D GA drawing engine** (`app/drawing/`, added 2026-08-01): turns `_spec_geometry`'s mm
  envelope into a dimensioned general-arrangement sheet — `primitives` (byte-stable SVG, one
  `<g>` per layer), `views` (third-angle + standard scale), `symbols` (per-category glyphs,
  **client-extension point**), `title_block`, `sheet`, `drawing_service`. Unknown dimension ->
  TBD callout, never a drawn line. Endpoints: `GET /api/drawing/catalog` (drives the studio
  form as data), `POST /api/drawing/render`, `POST /api/tools/drawing` (`generate_drawing`).
- **Golden tests**: `backend/tests_golden.py` (10 cases, byte-identical) — **run before and
  after any engine change**, must stay ALL PASS. **Engineering tests**:
  `backend/tests_engineering.py` (45 checks — the vendor chart, selection semantics, and every
  formula in the client's calculation doc) — run after any `app/engineering/` change.
  **Drawing tests**: `backend/tests_drawing.py` (37 checks — determinism, layer structure,
  scale choice, the honest-gap contract) — run after any `app/drawing/` change. **Retrieval tests**: `backend/tests_retrieval.py`
  (reranker/selector/permissions/citations/formatter/cache; model-free) — run after any
  `rag/` change. **Pricing tests**: `backend/tests_pricing.py` (headline stays historical;
  cost-plus/market signals present, consistent, deterministic) — run after any
  `pricing*.py`/`quotation.py` change. **Lookup tests**: `backend/tests_lookup.py`.

## Tool endpoints for Flowise (the migration bridge)
`app/main.py` exposes clean JSON tools so Flowise Custom Tools call Python (Python
does the reasoning, Flowise only orchestrates + narrates). Each carries an explicit
FastAPI `operation_id` — that string becomes the tool name the agent sees, so do NOT
remove them (without one, FastAPI auto-generates `tool_spec_api_tools_spec_post`):
- `POST /api/tools/spec`     → `generate_specification`
- `POST /api/tools/quote`    → `generate_quotation` (carries preformatted `price_display`,
  `price_range_display`, and `price.*_display` rupee strings — see 10x-price fix below)
- `POST /api/tools/lookup`   → `lookup_project` (carries **`lookup_markdown`** — a
  code-rendered "Historical Project Found" block the agent prints verbatim, so an
  archive record can never be re-dressed as a freshly generated quotation)
- `POST /api/tools/retrieve` → `retrieve_knowledge`
- `POST /api/tools/list`     → `list_projects` (enumerate ALL offers: count, clients,
  category counts, projects — for "how many / list all / which clients / what categories")
- `GET  /api/tools/filters`  → `list_filters`
- UI data: `GET /api/offers`, `GET /api/offers/{id}`, `POST /api/uploads`, `GET /api/uploads`,
  `GET /api/knowledge/overview` (structured "Database Organization" surface: collections
  taxonomy + equipment facets + stats, all counts computed from the store — powers the
  organised Knowledge Base page)

## Target architecture (in progress)
**Flowise orchestrates; Python owns all business logic + calculations.** Stack:
React+Vite+**TypeScript**, FastAPI, **Flowise** + Ollama + **Llama 3** + ChromaDB +
Redis, **PostgreSQL**, **Docker Compose**, **RunPod GPU VPS** (Ubuntu 22.04). Agents:
Engineering (live), Quotation (live), Drawing (roadmap — **design plan in
`docs/drawing-agent-plan.md`**: a "studio" split chat+canvas that turns the
deterministic `_spec_geometry` envelope into a 2D GA drawing via a new
`backend/app/drawing/` engine + `/api/tools/drawing`; geometry stays
deterministic, TBDs render as callouts), coordinated later by a **Supervisor**.
The current chat engine's reasoning becomes the Flowise **tools** above; the
chat-orchestration layer (`/api/query`, `llm.py`) is what Flowise replaces.

## Dev commands
- **Start EVERYTHING on the pod (do this first, every new session):**
  `bash /workspace/persistent/start-all.sh` — idempotent; brings up PG, Redis, Ollama,
  backend, Flowise, frontend. Then forward ports **5173** (app), **3000** (Flowise),
  **8000** (backend) in the VS Code PORTS panel.
- Backend (local): `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Backend (VPS/Linux venv): `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Full stack (Docker host only — NOT the RunPod pod): `docker compose up -d --build`
- Frontend: `cd frontend && npm install && npm run dev`
- Golden tests: `cd backend && .venv/bin/python tests_golden.py` (Linux) — must stay ALL PASS
- Supabase/Postgres export: `cd backend && python export_supabase.py` → `data/export/`

## Key gotchas
- **Frontend "failed to load" / "Blocked request. This host is not allowed."**: Vite 6
  rejects unknown Host headers. `frontend/vite.config.js` now sets `allowedHosts: true`
  so the app loads through the pod's forwarded URL / ngrok / VS Code port-forward
  (whatever hostname). If it ever regresses to a pinned host, that's the cause.
- **Embedding-model match**: the ChromaDB collection was built with **all-MiniLM-L6-v2**.
  If Flowise queries it with a different embedding model, retrieval breaks — use the
  same model or re-ingest. (This is why the agent searches via the backend's
  `retrieve_knowledge` tool and NOT a Flowise Chroma retriever node.)
- **Stale query index after ingest (found 2026-07-23) — call `POST /api/admin/reload-index`
  after ingesting documents** (no full restart needed). ChromaDB embedded: a running
  server's in-memory query index is NOT refreshed by writes from a separate process (the
  `rag.ingest` CLI). Symptom: after ingest, `/api/health` shows the new `documents_indexed`
  count (count() reads from disk) but `retrieve_knowledge` returns `count:0` (the query
  index still lacks the new vectors). Fix: `store.reload_collection()` clears Chroma's
  in-process system cache; the `/api/admin/reload-index` endpoint calls it + invalidates the
  retrieval cache. `rag.ingest` also bumps the (Redis-shared) cache version on completion.
  A backend restart still works as the blunt fallback.
- **Grounding vs. general knowledge (prompt, 2026-07-23).** The agent's prompt now routes
  knowledge questions (face velocity, filter media, standards, "what should X be") to
  `retrieve_knowledge` FIRST and never asks for dimensions for them. If records return, it
  answers from them and cites the source; if NOTHING returns (today's empty corpus), it
  must open "General engineering guidance (not from Vitech records):" and flag that
  company-specific values need confirming. NB: llama3.1:8b imperfectly BLENDS the two
  branches (leads with the general label even when it used a retrieved value) — an inherent
  8B limitation the branch wording can't fully fix; a stronger model (roadmap D2) would.
  The hallucinated-generic-answer complaint is fundamentally the empty corpus (Phase 3),
  proven live: ingest one doc → restart → the agent surfaces the doc's exact figure.
- **Agent says "I don't have the ability to call external tools" / "I'll simulate a
  response" → THE BACKEND IS DOWN.** The tool's fetch to `localhost:8000` failed and
  llama3.1 improvised. It is not model flakiness: with all services up, tool-calling
  is 5/5 reliable. Check `curl localhost:8000/api/health` first.
- **Tool-capable model required**: the Flowise Tool Agent needs native tool-calling.
  `llama3` does NOT advertise it; `llama3.1:8b` does. Check with
  `curl localhost:11434/api/show -d '{"model":"X"}'` → `capabilities` must list `tools`.
- **Docker networking**: services talk by **service name** (`http://ollama:11434`,
  `http://chroma:8000`) — but that is Docker-only. The RunPod pod runs NATIVE, so it is
  all `localhost` (see below).
- **ASCII in console/PDF**: avoid em-dashes / non-latin1 glyphs in text that reaches
  the Windows console or the fpdf2 PDF.

## Docs (in `docs/`)
`architecture.html` (system diagram), `technical-flow.html` (detailed flow + status),
`agent-transition.html` (current agent → Flowise), `client-meeting.html` (client
review), `vps-setup.md` (deploy runbook).

## The Engineering Agent (BUILT AND LIVE in Flowise)
Chatflow **"Engineering Agent"**, id `c4bfba16-aeb0-4c1b-840e-21b474639a8d`
(Flowise UI → Chatflows; deployed). Built **programmatically** (the OpenAPI Toolkit
UI is broken in 3.0.13 — see below), stored in Postgres `chat_flow` + `tool` tables.
- **Graph**: `ChatOllama (llama3.1:8b @ localhost:11434, temp 0)` + `BufferMemory`
  → **Tool Agent** ← 4 **Custom Tool** nodes (each a `node-fetch` POST to
  `http://localhost:8000/api/tools/*` with a `question` string input).
- **Tools** (5): `generate_specification`, `generate_quotation`, `lookup_project`,
  `retrieve_knowledge`, `list_projects` (the 5th, added for enumeration —
  `customTool_4`, rebuilt by `/workspace/persistent/agent-add-list-tool.py`, also
  baked into `agent-build.py` for from-scratch rebuilds).
- **System prompt** (on the Tool Agent node) defines **TWO MODES** — this balance is the
  whole trick, mirroring `app/prompt.py::CHAT_SYSTEM`. Do not make it stricter without
  re-reading this:
  - **Mode A — Consulting / general engineering (no tools)**: concepts, how/why,
    comparisons, selection guidance, materials, formulas, greetings. Answer from
    engineering knowledge, labelled as general knowledge. An earlier over-strict prompt
    made it answer "No matching records found" to *"how does a wet scrubber work?"* —
    that phrase belongs ONLY to a failed records lookup.
  - **Mode B — Vitech project work (tools mandatory)**: spec, quote, price, client/offer
    lookup. Pass the requirement **verbatim** (rephrasing loses "4 nos" → qty=1); copy
    tool numbers **exactly**; never invent a client/ref/price/material; on `count:0` say
    records have no match, then optionally help via Mode A knowledge.
  - **Constants** are given in the prompt (1 CFM = 1.699 CMH) because llama3.1 invented
    "1 CFM = 1725 CMH" when left to itself.
  - Known nit: llama3.1 often fires `retrieve_knowledge` even on Mode A questions. It
    then answers from knowledge anyway — wasteful, not wrong.
- **Rebuild scripts** (after a pod delete): `/workspace/persistent/agent-build.py`
  then `agent-harden-prompt.py`. Easier: restore `/workspace/persistent/postgres-backups/vitech.sql`.
- **Verify without the UI**: `POST http://localhost:3000/api/v1/prediction/<id>`
  with `{"question":"...","chatId":"x"}` (this route is whitelisted — no auth).
  Add `"streaming":true` for SSE.

## The Quotation Agent (BUILT AND LIVE in Flowise — 2026-07-17)
Second chatflow **"Quotation Agent"**, id `6fa5a302-2d73-4191-bbea-ce98e4af2f1f`.
Same architecture as the Engineering Agent (ChatOllama llama3.1:8b @ temp 0 +
**BufferMemory** + Tool Agent), specialised for budgetary quotations.
- **Tools (4)**: `generate_quotation`, `lookup_project`, `retrieve_knowledge`,
  `list_projects` (drops `generate_specification` — that's the Engineering Agent's job).
  It **reuses the same shared `tool` rows** — no new tool rows created.
- **Build/rebuild**: `/workspace/persistent/quotation-agent-build.py` — clones the LIVE
  Engineering Agent flow (guarantees correctly-shaped nodes for this install), keeps only
  the quotation tools, swaps in the quotation prompt. **Idempotent**: updates the existing
  'Quotation Agent' in place, never duplicates. Or just restore `vitech.sql`.
- **Prompt** (6 RULES, ~4250 chars — 2026-07-24): same price discipline (copy `..._display`
  verbatim); never preface with "Based on the tool's output"; compare = report each figure +
  which is higher, **no percentages/ratios**; **no confidence / R-squared exposed**.
  **RULE 5** = present `pricing_basis_markdown` (margin/cost-plus/market) only when pricing
  basis is asked. **RULE 6** = **technical/engineering questions are HANDED OFF to the
  Engineering Agent** (one-sentence redirect, no tool, no answer) — the Quotation Agent no
  longer answers engineering theory. **KEEP THE PROMPT SHORT**: at ~7.4k chars (after adding
  RULE 5+6 verbosely) llama3.1 **leaked `greet` tool-call JSON at greetings 3/3**; compressing
  back to ~4.25k fixed it 3/3. Do not let it grow; compress, don't append.
- **Memory** (2026-07-24): **BufferMemory** — gives correct **per-session** memory keyed on
  the request `chatId` (verified: a follow-up recalls the earlier requirement). It is
  **in-process**, so it resets on a Flowise restart. **RedisBackedChatMemory attempt FAILED**:
  building the node programmatically in `quotation-agent-build.py` made the Tool Agent throw
  `memory.getChatMessages is not a function` at prediction (Flowise instantiated a stub, not
  the class) — reverted to BufferMemory. The node's connect-credential IS optional (→
  `localhost:6379`), so **for cross-restart persistence add a "Redis-Backed Chat Memory" node
  via the Flowise UI** and wire it to the Tool Agent's memory input (the UI builds the instance
  correctly); the disabled `_to_redis_memory()` helper in the build script documents the shape.
- **Verified end-to-end (5 cases)**: generate, revise/add-qty (₹25,50,000 → ₹38,25,000
  for 4→6 nos, matches backend), compare (two quotes, no bad math), client-specific lookup
  (₹99,64,925 Indian grouping), enumerate. Through the UI proxy too (`:5173/flowise`).

## Flowise (ACTUAL install — pinned + patched, not vanilla)
Isolated install at **`/opt/flowise-app`** (container disk, NOT global npm, NOT Docker).
Started by `/workspace/persistent/flowise-start.sh`; rebuild with `flowise-reinstall.sh`.
- **Snapshot fast-path (added 2026-07-23).** `/opt` is wiped on a pod delete/migrate, and
  rebuilding from npm is ~20 min (3300 pkgs + native C++ compiles) AND drifts versions.
  So a **1.0G tarball of the known-good patched tree** lives at
  `/workspace/persistent/flowise-app.tar.gz`. `flowise-reinstall.sh` **extracts it (~1-2 min)
  when present** and only falls back to npm if it's missing or you pass `--from-npm`.
  Refresh it after a verified rebuild with `flowise-snapshot.sh` (atomic write). This is the
  Flowise analogue of the `vitech.sql` PG restore — bootstrap a migrated pod in minutes.
- **Pinned `flowise@3.0.13`**. Do NOT "upgrade" to 3.1.x: all 3.1.x pin
  `@langchain/core@1.1.20`, whose missing `./utils/uuid` subpath makes node loading
  throw. 3.0.x uses the `@langchain/core 0.3.x` tree.
- **Version-drift trap (bit us 2026-07-23, now fixed):** `flowise@3.0.13`'s OWN
  package.json references `flowise-components`/`flowise-ui` with a **caret** (`^3.0.13`),
  so a plain `npm install` re-resolves them to the newest 3.x on the registry — today
  that's `3.1.3`, which nests the broken `@langchain/core@1.1.20` (missing `./utils/uuid`)
  and Flowise crashes at startup. Fix: an **`overrides`** block in `package.json` hard-pins
  `flowise-components` + `flowise-ui` to `3.0.13`. Verify after any reinstall:
  `@langchain/core` top-level must be `0.3.61` and there must be NO
  `flowise-components/node_modules/@langchain/core`.
- 3.0.13 forgets to declare **three** deps its code eager-requires — we add them back at
  top level (`dependencies`): `multer-azure-blob-storage@^1.2.0`, `winston-azure-blob@^1.5.0`,
  and **`lunary@0.7.15`** (required by `flowise/dist/utils/updateChatMessageFeedback.js`;
  only `flowise-components` declares it, so the 3.0.13 pin leaves it nested where `flowise`
  can't resolve it → `Cannot find module 'lunary'`). Declaring it hoists it to top level.
- Two deprecated nodes are **deleted** post-install (`ReActAgentChat`, `ReActAgentLLM`)
  — their transitive langgraph import references the missing `./utils/uuid` and logs
  startup errors. We don't use them (we use Tool Agent).
- **Patched** `flowise-components/.../OpenAPIToolkit/OpenAPIToolkit.js`: upstream
  double-`pop()`s the data-URI, discarding the uploaded spec and base64-decoding the
  header into garbage → Server/Endpoints dropdowns never populate. All patches are
  reapplied by `flowise-reinstall.sh`.
- **SSRF config** (user-authorised, in `flowise-start.sh`): Flowise's default deny-list
  blocks loopback, so Custom Tools could not reach `localhost:8000`. We set
  `HTTP_SECURITY_CHECK=false` + `HTTP_DENY_LIST=169.254.0.0/16,fd00:ec2::254,0.0.0.0`
  → localhost allowed, cloud-metadata SSRF still blocked. Without this the agent
  fails with "Access to this host is denied by policy".

## Frontend ↔ Agent wiring (Phase 1 — DONE)
The Engineering Chat calls **Flowise**, not the backend's `/api/query`:
- `vite.config.js` (dev) + `frontend/nginx.conf` (prod) proxy **`/flowise` → :3000**
  (prefix stripped) so the browser calls the agent same-origin (no CORS).
- `App.jsx` POSTs `/flowise/api/v1/prediction/<AGENT_ID>` with
  `{question, streaming:true, chatId:sessionId}` and parses Flowise SSE:
  `{"event":"token","data":"..."}` → append, `usedTools` → captured, `end` → finalise.
  Agent id overridable via `VITE_ENGINEERING_AGENT_ID`.
- The backend's own `/api/query` engine still exists and still works — it is simply no
  longer what the chat calls. Other pages (Quotation, Knowledge Base) still use `/api/*`.

## KNOWN ISSUES — start the next session here (in this order)
1. **10x price bug — FIXED (2026-07-17).** Fixed structurally per golden rule #2, not by
   prompting. `pricing.py::inr_display()` produces Indian-grouped rupee strings; the price
   dict now carries `amount_display`/`unit_price_display`/`range_low_display`/
   `range_high_display`/`range_display`, and `/api/tools/quote` carries top-level
   `price_display` + `price_range_display`. The `lookup_project` path is covered too:
   `analytics.py::record_detail` now uses `inr_display`, and each lookup record carries a
   `price_schedule_display` map (e.g. `₹99,64,925`). The prompt tells the agent to print the
   `..._display` string verbatim and never regroup digits. Verified end-to-end: agent
   prints `₹25,50,000` exactly. Golden tests unaffected (ALL PASS).
2. **No enumeration tool — FIXED (2026-07-17).** Added `POST /api/tools/list` →
   `list_projects` (exact count, full client list, category counts, projects) and wired it
   as the 5th Custom Tool (`customTool_4`). Verified: "how many projects / which categories"
   now returns the true 33 with the correct breakdown, using `list_projects`. Rebuild via
   `agent-add-list-tool.py` (additive, idempotent) or a fresh `agent-build.py` run.
3. **Phase 3 ingestion** — `retrieve_knowledge` still returns `count:0`; only the 33
   offers (type=`offer`) exist, no type=`document` corpus. See Immediate next steps.
4. **Phase 2 pages** — Dashboard done; Historical Projects / Specification / Projects /
   Settings remain. Follow the Dashboard pattern in `App.jsx` (NAV entry + view ternary
   + component + styles).

## Agent gotchas learned the hard way
- **Poisoned memory**: if the agent starts emitting `{"name": "...", "parameters": {...}}`
  JSON at the user, its BufferMemory contains earlier leaked replies and it is COPYING
  its own history. No prompt fix can clean that. **Click "+ New chat"** (rotates
  sessionId → fresh memory). Always test prompt changes with a FRESH chatId.
- **Keep the system prompt SHORT.** It grew to 5,643 chars by appending a rule per bug;
  llama3.1:8b then narrated tool mechanics instead of acting. Rewriting to ~3,300 chars,
  leading with "never show the mechanics", fixed four bugs at once. Resist appending.
- **Never let a non-requirement reach a tool.** Passing "i'm keerthivasan" to
  generate_specification returned a paint-booth skeleton and the model narrated an
  "iron casting" project that never existed.
- There is only ONE agent. The "Consulting Engineer" / "ATS Quotation Engineer" badges
  are derived in `App.jsx::agentData()` from which tools ran — they are not two agents.

## Immediate next steps
- **Phase 3 (highest value)**: ingest real documents so `retrieve_knowledge` stops
  returning `count:0` — drop files in `backend/data/bulk/`, then
  `cd backend && .venv/bin/python -m rag.ingest data/bulk --equipment-type X --customer Y`.
  Only the 33 offers (type=`offer`) exist today; `retrieve_knowledge` searches
  type=`document`, which is empty until this runs.
- **Phase 2**: build out the workspace pages (Dashboard, Projects, Quotation,
  Specification, Historical Projects, Settings).
- Later: Quotation / Consultant / Validation agents — clone the Engineering Agent
  pattern, changing only the system prompt + which tools are attached.

## RunPod native deployment (ACTUAL running setup, not Docker)
RunPod GPU pods can't run Docker-in-Docker (no CAP_NET_ADMIN / user-namespaces),
so the stack runs **natively** on the pod, not via `docker compose`:
- Everything durable lives on the **`/workspace` persistent volume** (survives pod
  delete): the repo, `backend/.venv`, `frontend/node_modules`, and
  **`/workspace/persistent/`** → `ollama/` (models, symlinked from `/root/.ollama`),
  `chroma/` (Chroma dir, via `CHROMA_DIR` in `backend/.env`), `flowise/` (keys/logs/
  uploads), `postgres-backups/vitech.sql`, and **`flowise-app.tar.gz`** (1.0G snapshot of
  the patched `/opt/flowise-app` tree — restored fast by `flowise-reinstall.sh`).
- Postgres + Redis data dirs stay on the container disk (the volume can't `chown`,
  which PG requires) — back PG up with `/workspace/persistent/pg-backup.sh`.
- **Restart after a pod stop/start:** `bash /workspace/persistent/start-all.sh`
  (idempotent; brings up PG, Redis, Ollama, backend, Flowise, frontend).
  Stop with `stop-all.sh`. These are plain background procs (no systemd here).
- **If the CONTAINER DISK was wiped** (start-all.sh fails because psql/node/ollama are
  gone): `bash /workspace/persistent/bootstrap-pod.sh` FIRST, then `start-all.sh`.
  It reinstalls PG + Redis + Node 20 + the Ollama binary + Flowise (/opt/flowise-app —
  now via the `flowise-app.tar.gz` snapshot fast-path, ~1-2 min instead of ~20),
  relinks `/root/.ollama` to the volume's models, recreates the DB role/database,
  restores the Engineering Agent from `postgres-backups/vitech.sql`, and regenerates
  the git SSH key (printing the pubkey to add to GitHub). Idempotent; it refuses to
  restore over an existing chatflow. Verified: the dump restores 1 chatflow + 4 tools
  + 33 offers with the tuned prompt intact.
- **The agent lives in Postgres on the container disk** — the dump on the volume is its
  only lifeline. Run `bash /workspace/persistent/pg-backup.sh` after ANY agent change
  (prompt tuning included) and before stopping the pod.
- Native = services talk over **`localhost`** (NOT the Docker service names in
  `docs/vps-setup.md`): Ollama `localhost:11434`, backend tools
  `http://localhost:8000/api/tools/*`, Postgres `localhost:5432`.
