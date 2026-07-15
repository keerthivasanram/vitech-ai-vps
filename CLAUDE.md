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

## Current state (prototype — migrating to the VPS/target stack)
- **Backend**: FastAPI in `backend/app/`, embedded **ChromaDB**, **Ollama** (`qwen2.5:3b`
  locally; `llama3` on the GPU VPS).
- **Frontend**: React + Vite in `frontend/`. Multi-agent UI, 3 agents: **Engineering**,
  **Quotation**, **Drawing** (roadmap) + **Knowledge Base** and **Upload** pages.
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
does the reasoning, Flowise only orchestrates + narrates):
- `POST /api/tools/spec` · `POST /api/tools/quote` · `POST /api/tools/lookup`
- UI data: `GET /api/offers`, `GET /api/offers/{id}`, `POST /api/uploads`, `GET /api/uploads`

## Target architecture (in progress)
**Flowise orchestrates; Python owns all business logic + calculations.** Stack:
React+Vite+**TypeScript**, FastAPI, **Flowise** + Ollama + **Llama 3** + ChromaDB +
Redis, **PostgreSQL**, **Docker Compose**, **RunPod GPU VPS** (Ubuntu 22.04). Agents:
Engineering (live), Quotation (live), Drawing (roadmap), coordinated later by a
**Supervisor**. The current chat engine's reasoning becomes the Flowise **tools**
above; the chat-orchestration layer (`/api/query`, `llm.py`) is what Flowise replaces.

## Dev commands
- Backend (local): `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Backend (VPS/Linux venv): `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Full stack (VPS): `docker compose up -d --build` (see `docs/vps-setup.md`)
- Frontend: `cd frontend && npm install && npm run dev`
- Golden tests: `cd backend && .venv/Scripts/python tests_golden.py`
- Supabase/Postgres export: `cd backend && python export_supabase.py` → `data/export/`

## Key gotchas
- **Embedding-model match**: the ChromaDB collection was built with **all-MiniLM-L6-v2**.
  If Flowise queries it with a different embedding model, retrieval breaks — use the
  same model or re-ingest.
- **Docker networking**: services talk by **service name** (`http://ollama:11434`,
  `http://chroma:8000`), never `localhost`.
- **ASCII in console/PDF**: avoid em-dashes / non-latin1 glyphs in text that reaches
  the Windows console or the fpdf2 PDF.

## Docs (in `docs/`)
`architecture.html` (system diagram), `technical-flow.html` (detailed flow + status),
`agent-transition.html` (current agent → Flowise), `client-meeting.html` (client
review), `vps-setup.md` (deploy runbook).

## Immediate next steps
On the VPS: `docker compose up -d --build` → `ollama pull llama3` + `nomic-embed-text`
→ load `backend/data/export/schema.sql` + `data.sql` into Postgres → open Flowise
(`:3000`) → build the **Engineering Agent** with 3 Custom Tools pointing at
`http://backend:8000/api/tools/*`.
