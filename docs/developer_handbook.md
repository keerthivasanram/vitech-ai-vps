# Vitech AI Engineering Platform — Developer Handbook

> Rewritten 2026-09-01. The previous version described Gemini, Supabase, a
> monolithic `App.jsx` and a backend on port 8001 — none of which has ever been
> true of this codebase. If you read that version, discard it entirely.
>
> `CLAUDE.md` at the repo root is the running project log and is more current
> than any document here. This handbook is the stable mental model; CLAUDE.md is
> what happened last week.

---

## 1. What this is

An enterprise **AI engineering assistant** for **Vitech Enviro Systems**, who
build industrial air-pollution-control and surface-finishing equipment — wet
scrubbers, paint and powder booths, dust collectors, ovens, conveyors,
pretreatment plant, ducting.

It turns a client requirement into a **technical specification**, a **general-
arrangement drawing**, a **bill of materials** and a **budgetary quotation**,
grounded in Vitech's own historical offers and engineering standards.

**It is not a chatbot.** Three rules govern every design decision:

1. **Never use the word "Copilot"** — anywhere: code, UI, docs, prompts.
2. **Numbers are DETERMINISTIC.** Engineering rules, historical data and Python
   produce every number. The LLM writes prose and narrates. It never invents a
   dimension, price, capacity, count or material. When a value cannot be
   derived, the platform prints **"To be determined"** and says why — a gap is
   shown *as* a gap rather than filled.
3. **Human in the loop.** Every output is an engineer-reviewed *draft*.
   `Released Design` is deliberately unreachable from code: release is a
   signature, and a program that could award it to itself defeats the rule.

If you remember one thing: **rule 2 is why this codebase looks the way it
does.** Almost every unusual structural choice exists to keep a language model
away from a number.

---

## 2. The shape of the system

```
Browser ──► React + Vite frontend (5173)
              │
              ├──► /flowise ──► Flowise 3.0.13 (3000) ──► ChatOllama llama3.1:8b (11434)
              │                     │                     BufferMemory + Tool Agent
              │                     └── Custom Tools ──┐
              └──► /api ────────────────────────────────┴──► FastAPI backend (8000)
                                                                │
                                    ┌───────────────────────────┼──────────────┐
                                    ▼                           ▼              ▼
                            embedded ChromaDB            SQLite auth.db    SQLite ops.db
                            (offers + documents)         (accounts)       (traces, jobs)

  Postgres (5432) holds FLOWISE's own data — the three chatflows and their tool
  rows. It is the one asset not reproducible from git, which is why
  `pg-backup.sh` exists and why `ops/verify-agents.sh` diffs the live prompts
  against the scripts in `ops/flowise/`.
```

**Flowise orchestrates; Python owns all business logic and every calculation.**
An agent's "reasoning" is a system prompt plus a set of Custom Tools, each of
which is a `node-fetch` POST to `http://localhost:8000/api/tools/*`. Python
computes; the model narrates the JSON that comes back.

### The three agents

| Agent | Chatflow id | Tools |
|---|---|---|
| Engineering | `c4bfba16-…639a8d` | generate_specification, generate_quotation, lookup_project, retrieve_knowledge, list_projects, check_voc_safety, calculate_heat_load |
| Quotation | `6fa5a302-…ce98e4af2f1f` | generate_quotation, lookup_project, retrieve_knowledge, list_projects, generate_bom |
| Drawing | `f486d388-…db9dad3b950d` | generate_drawing, generate_specification, lookup_project, list_projects |

Their prompts live in `ops/flowise/*.py` — **those scripts are the source of
truth**. Tune a prompt on the server without mirroring it into git and a rebuild
silently produces older behaviour; `ops/verify-agents.sh` is what catches that,
and it exits non-zero so it can gate a deploy.

---

## 3. Repository layout

```
backend/
  app/
    main.py             64 lines. Wiring only: middleware, startup, router registration.
                        REGISTRATION ORDER IS PART OF THE CONTRACT (see §7).
    api/                17 routers, ~56 endpoints. tools.py is the agent bridge.
    engineering/        THE DETERMINISTIC CALCULATION CORE (see §4).
    drawing/            geometry -> byte-stable SVG / DXF / PDF general arrangements.
    package/            composes one resolved analysis into 14 reviewable documents.
    siting/             places resolved equipment on a customer's site photograph.
    auth/               accounts, sessions, and policy.py - the security matrix as code.
    observability/      contextvars, spans, JSON logs, jobs, artifacts, metrics.
    resolver.py         one resolver, two policies (Consulting / ATS).
    analysis.py         orchestrates matching, confidence, cross-validation, presentation.
    catalog.py          per-category profiles: required inputs, rules, spec templates.
    spec_template.py    the canonical output field list, and the TBD gap-fill.
    release_gate.py     may this document leave the building?
    values.py           the readers that decide what "12 nos 600 x 600" means.
  rag/                  ingestion + multi-stage retrieval (cache, rerank, permissions).
  data/
    offers/             33 hand-extracted historical offers - the ATS corpus.
    knowledge_docs/     the client's calculation workbooks and datasheets.
  tests_*.py            13 suites. See §8.
frontend/src/           React + Vite. No UI library; vanilla CSS.
ops/flowise/            agent build scripts + pod operations. Source of truth for prompts.
docs/                   design documents, plans, and the queries sent to the client.
```

---

## 4. The engine

### One resolver, two policies

`app/spec_schema.py` defines a `Policy`. `app/resolver.py` applies it:

* **Consulting (knowledge mode)** — reason from engineering knowledge, defer
  unknowns to "To be determined". The default.
* **ATS (data mode)** — build from the historical offers. Entered when the user
  says "refer db", or when the category is *adaptable* (it has engineering rules
  or scaling behaviour).

`app/agent_router.py::prepare` makes that routing decision and is the ONE place
that owns completeness and thresholds.

### The calculation core (`app/engineering/`)

Every module here is either the client's own document transcribed, or a vendor
catalogue as data. None of it guesses.

| Module | What it owns |
|---|---|
| `formula_service` | design constants, `compute_spec`, `compute_wet_scrubber` |
| `design_standards` | booth vocabulary and design face velocity, filters, lighting, duct, electrical, fire |
| `blower_service` | the Continental Thermal chart, 203 real models. Selection returns a REAL model or None — never an interpolated machine |
| `paint_shop_service` | the client's paint-shop calculation document, literally |
| `heat_load_service` | tank / dry-off oven / curing oven, from `Heat Load.xlsx` |
| `voc_service` | solvent concentration and the LEL gate — a VERDICT, not a spec row |
| `scrubber_service` | tower and duct diameter from airflow |
| `material_service` | process → material matrix, and the stock-section weight table |
| `rate_card` | Vitech's real ₹/kg, ₹/HP, ₹/sq.ft and bought-out prices |
| `geometry_service` | resolves the equipment type and envelope ONCE, for spec and drawing alike |

**Where the client extends it:** the design constants in `formula_service`, the
factor table in `unit_converter`, the standards strings in `standards_service`,
the matrix in `material_service`, and the glyph registry in `drawing/symbols`.

### Spec templates and the TBD contract

A category's `spec_template` in `catalog.py` lists the fields a complete
specification must have. `apply_template` fills each uncovered field with an
explicit `origin: "tbd"` row. This is the guardrail that stopped the
hot-air-oven hallucination: **a gap the engine leaves is printed as a gap**, so
the model has no vacuum to fill.

When adding a category: add its `spec_template` field list, then wire its
formulas into `formula_service`. **Template labels must match what the engine
emits**, or the row appears twice — once resolved, once as a phantom TBD.

---

## 5. Authentication

**Every route except `GET /api/health` requires a credential.** Accounts live in
SQLite at `backend/data/auth.db` (gitignored). There is no default account and
no seeded password — an empty user table locks everyone out, which is the
correct failure.

```bash
.venv/bin/python -m app.auth.bootstrap admin|user|service|list|password
```

Three principal kinds: `engineer` < `admin` are humans; **`service` is not in
that ladder** — it has its own route allow-list, and that is the important
property. **A leaked agent key can call `/api/tools/*` and nothing else.**

`app/auth/policy.py` IS the security matrix, executable — one central table
rather than per-route decorators, because deny-by-default only means something
for the route nobody remembered to decorate: **an unclassified path defaults to
administrator.** `docs/endpoint-security-matrix.md` is the same policy in prose.

Sessions are stored, not JWTs, so logout revokes immediately. Login never
reveals whether the username or the password was wrong, and hashes even for an
unknown user so response time is not an enumeration oracle.

---

## 6. Observability

`app/observability/` is stdlib-only and writes to `data/ops.db`.

* Request ids go in the **`X-Request-ID` response header**, job ids in
  **`X-Job-ID`**. **Never put either in a response body** — the contract suite
  hashes bodies, and a request id in one would change all 28 fingerprints.
* Six seams carry spans (retrieval, RAG, Ollama, routing, planning, packaging).
  **A span outside a request is a no-op that still runs its body**, which is
  what keeps the golden tests a test of the engine rather than of the tracing.
* **Customer requirements never reach the logs.** They live on the job record
  behind the Engineer/Admin roles. Pinned by a test that greps live log output.
* Jobs and artifacts are **permanent**; requests and spans are purged at 90 days.
  Artifacts carry a SHA-256, and **a file whose digest no longer matches is
  reported missing, never served** — it is not the document that was issued.

**The contextvar trap, worth knowing:** Starlette's `BaseHTTPMiddleware` runs the
downstream app in a separate task, so a `ContextVar` *rebound* inside
`call_next` is invisible to the middleware that wrapped it. A mutable dict
shared by reference does cross that boundary, which is why `context.identify()`
writes to a fact bag as well as to the vars.

---

## 7. Things that will bite you

* **`operation_id` IS the tool name the agent sees.** Removing or renaming one
  renames a live agent tool. `tests_api_contract.py` fingerprints
  `/openapi.json` for exactly this reason.
* **Router registration order is part of the contract.**
  `/api/offers/by-source/{path}` must stay ahead of `/api/offers/{offer_id}`.
* **A Flowise tool's optional `$prop` is UNDEFINED when the model omits it.** A
  bare `$question` throws inside the NodeVM, the agent sees an empty result and
  *invents an answer*. Read optional properties as
  `(typeof $x !== 'undefined' ? $x : null)`.
* **Keep agent prompts short and fold new rules INTO existing ones.** Appending
  a standalone rule block destabilises routing even when the result is shorter
  overall. The Engineering Agent leaks tool-call JSON above ~10,000 characters.
* **Give the model less, not more instruction.** When a tool returns both a
  ready-made reply and the numbers behind it, an 8B model summarises the
  numbers. Stripping the structured fields inside the tool function is what
  actually fixes it — the same lesson as deleting `svg` from the drawing tool.
* **Screenshot generated graphics before believing them.** Five drawing bugs and
  two PDF layout bugs were invisible in the source and obvious in the render.
* **Trimming a response is an API change.** Reducing `/api/health` broke three
  pages that silently showed "unknown" and "0 records". Grep every consumer.
* **`quotation-agent-build.py` rebuilds from a clone and drops any tool not in
  `KEEP_TOOLS`.**
* **Test the deterministic layer directly.** A green end-to-end agent run does
  not prove `understand()` works — the LLM may have parsed what the regex could
  not.

---

## 8. Tests

Fifteen suites, all plain scripts — no pytest, no fixtures framework.

```bash
cd backend
.venv/bin/python tests_golden.py          # 10 cases, byte-identical. RUN BEFORE AND AFTER ANY ENGINE CHANGE.
.venv/bin/python tests_engineering.py     # the client's formulas, pinned to their worked examples
.venv/bin/python tests_drawing.py         # determinism, layers, scale, the honest-gap contract
.venv/bin/python tests_pdf.py             # the customer-facing renderers (needs requirements-dev.txt)
.venv/bin/python tests_lookup.py tests_pricing.py tests_retrieval.py tests_review.py
.venv/bin/python tests_bom.py tests_package.py tests_observability.py
.venv/bin/python tests_siting.py          # site placement geometry
.venv/bin/python tests_auth.py            # needs a running server (VT_TEST_* for the role tests)
.venv/bin/python tests_api_contract.py    # needs a running server AND admin credentials
```

`tests_api_contract.py` stores a status code and a SHA-256 of each canonicalised
response for 28 endpoints. Re-record with `--record` **only when a change is
intended**, and say in the commit why the fingerprints moved.

The goldens are the same idea for the engine. When they move, the commit must
say which cases moved and why — "only the 3 paint-booth cases moved, all
wet-scrubber and knowledge cases byte-identical" is the shape of a good answer,
because it proves the change was scoped.

---

## 9. Running it

**On the pod** (RunPod, native — no Docker; the GPU pod cannot run it):

```bash
bash /workspace/persistent/start-all.sh        # idempotent: PG, Redis, Ollama, backend, Flowise, frontend
bash /workspace/persistent/bootstrap-pod.sh    # FIRST, if psql/node/ollama are missing (container disk wiped)
bash /workspace/persistent/pg-backup.sh        # after ANY agent change, before stopping
```

Forward ports 5173 (app), 3000 (Flowise), 8000 (backend).

**Locally**, work on frontend and backend source only — anything validated
without a running pod. Do not try to start Flowise, Ollama or Postgres there.

**Ingesting documents:**

```bash
.venv/bin/python -m rag.ingest data/knowledge_docs --manifest manifest.json
# then POST /api/admin/reload-index, or restart the backend
```

That last step is not optional: embedded Chroma does not refresh a running
server's in-memory query index when another process writes to it. The symptom is
`/api/health` showing the new document count while retrieval returns nothing.

---

## 10. Known limits

* **llama3.1:8b paraphrases where it should print verbatim**, and leaks
  tool-call-shaped JSON on some compound greetings. The frontend guards the
  greeting at the chat boundary. The real fix is a stronger tool-capable model.
* **Eight questions are outstanding with the client**
  (`docs/Vitech_Calculation_Workbook_Queries.pdf`). Until the face-axis question
  is answered, every booth airflow is provisional.
* **Component positions in a drawing are schematic and undimensioned** — Vitech
  has supplied no setting-out rules, and dimensioning a position we invented
  would be exactly the fabrication rule 2 forbids.
* **CORS defaults to `*` and there is no HTTPS in front.** Both are V1.0
  close-out items.
