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

### ▶ TOMORROW — start here (as of 2026-07-23, end of session)
State: Engineering Agent is **architecture-complete** (engineering/ calc package + full
retrieval pipeline built; lookup now content-relevance + scales). Golden 10 / retrieval 16 /
lookup 12 ALL PASS. Everything committed+pushed to `fix/list-projects-category-filter`. The
ONLY thing blocking grounded knowledge answers is client documents.
1. **First**: `bash /workspace/persistent/start-all.sh`; forward 5173/3000/8000. If psql/node
   /ollama are missing (container wiped), run `bootstrap-pod.sh` FIRST.
2. **If the client provided documents** → drop them in `backend/data/bulk/`, run
   `cd backend && .venv/bin/python -m rag.ingest data/bulk --equipment-type X --customer Y`,
   then `curl -X POST localhost:8000/api/admin/reload-index` (no restart needed), and verify
   `retrieve_knowledge` returns hits + the agent grounds + cites. This is the #1 value item.
3. **If no documents yet** → either (a) START THE NEXT AGENT (Quotation is live; build Drawing
   or a Supervisor by cloning the Engineering Agent pattern — prompt + which tools attached),
   or (b) platform upgrades that the next agents inherit: cross-encoder reranker into
   `rag/reranker.py`'s existing interface (B1), then Qdrant + BGE-M3 (D1), DeepSeek R1 (D2).
4. **Optional polish** (user asked): tighten lookup relevance gap (`_REL_GAP` in
   `app/retriever.py`) if stricter single-answer precision is wanted; reformat lookup output
   to the "Historical Project Found / Commercial / Source" template the user sketched.
5. Before stopping the pod: `bash /workspace/persistent/pg-backup.sh` (agent lives in PG on
   the container disk — the dump on the volume is its only lifeline).

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
  **TWO** chatflows built and verified end-to-end: **Engineering Agent** and
  **Quotation Agent**.
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
- **Golden tests**: `backend/tests_golden.py` (10 cases, byte-identical) — **run before and
  after any engine change**, must stay ALL PASS. **Retrieval tests**: `backend/tests_retrieval.py`
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
- `POST /api/tools/lookup`   → `lookup_project`
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
