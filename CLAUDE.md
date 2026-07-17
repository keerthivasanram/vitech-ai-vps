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
- **Routing** (`app/main.py::_prepare`): default is Consulting (reason, don't copy).
  Data mode only when the user says "refer db" OR the category is **adaptable**
  (has engineering rules / scaling). Non-adaptable categories reason from knowledge.
- **Pricing**: `app/pricing.py` — nearest priced offer normalised **per-unit**,
  scaled by the sizing driver, cross-checked against a size→price trend, ±range +
  confidence.
- **Quotation**: `app/quotation.py` (assembly) + `app/quotation_pdf.py` (fpdf2 PDF).
- **Deterministic analytics + record lookup**: `app/analytics.py` (exact counts /
  lists / clients; `record_detail` renders one file's extracted fields).
- **Support**: `app/validate.py`, `app/ledger.py`, `app/catalog.py` (category
  profiles + `required_inputs`), `app/understand.py` (intent + param extraction),
  `app/llm.py` (plan_answer), `app/prompt.py` (system prompts).
- **Golden tests**: `backend/tests_golden.py` (10 cases, byte-identical). **Run
  before and after any engine change** — must stay ALL PASS.

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
Engineering (live), Quotation (live), Drawing (roadmap), coordinated later by a
**Supervisor**. The current chat engine's reasoning becomes the Flowise **tools**
above; the chat-orchestration layer (`/api/query`, `llm.py`) is what Flowise replaces.

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
- **Prompt**: quotation-centric two-mode prompt. Same price discipline as the Engineering
  Agent (copy `..._display` verbatim). Extra rules learned in testing: never preface with
  "Based on the tool's output"; when comparing, report each tool figure and say which is
  higher — **do not compute percentages/ratios** (llama3.1 got them wrong); report
  confidence as High/Med/Low and **do not expose R-squared / regression internals**.
- **Memory note**: Flowise 3.0.13 has **no Postgres *chat*-memory node** compatible with
  the Tool Agent (`AgentMemory` is a LangGraph checkpointer, not a `BaseChatMemory`, so it
  won't connect). We use BufferMemory (same as Engineering, proven). If cross-restart
  persistence is wanted later, `RedisBackedChatMemory` is the drop-in (Redis is running).
- **Verified end-to-end (5 cases)**: generate, revise/add-qty (₹25,50,000 → ₹38,25,000
  for 4→6 nos, matches backend), compare (two quotes, no bad math), client-specific lookup
  (₹99,64,925 Indian grouping), enumerate. Through the UI proxy too (`:5173/flowise`).

## Flowise (ACTUAL install — pinned + patched, not vanilla)
Isolated install at **`/opt/flowise-app`** (container disk, NOT global npm, NOT Docker).
Started by `/workspace/persistent/flowise-start.sh`; rebuild with `flowise-reinstall.sh`.
- **Pinned `flowise@3.0.13`**. Do NOT "upgrade" to 3.1.x: all 3.1.x pin
  `@langchain/core@1.1.20`, whose missing `./utils/uuid` subpath makes node loading
  throw. 3.0.x uses the `@langchain/core 0.3.x` tree.
- 3.0.13 forgets to declare two deps its code eager-requires — we add them back
  (upstream added them in 3.1.0): `multer-azure-blob-storage@^1.2.0`, `winston-azure-blob@^1.5.0`.
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
  uploads), `postgres-backups/vitech.sql`.
- Postgres + Redis data dirs stay on the container disk (the volume can't `chown`,
  which PG requires) — back PG up with `/workspace/persistent/pg-backup.sh`.
- **Restart after a pod stop/start:** `bash /workspace/persistent/start-all.sh`
  (idempotent; brings up PG, Redis, Ollama, backend, Flowise, frontend).
  Stop with `stop-all.sh`. These are plain background procs (no systemd here).
- **If the CONTAINER DISK was wiped** (start-all.sh fails because psql/node/ollama are
  gone): `bash /workspace/persistent/bootstrap-pod.sh` FIRST, then `start-all.sh`.
  It reinstalls PG + Redis + Node 20 + the Ollama binary + Flowise (/opt/flowise-app),
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
