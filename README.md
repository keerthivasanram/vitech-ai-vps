# ATS Engineering Assistant — Prototype

Proves the **intelligence layer** of the product: existing extracted engineering
data → knowledge base → AI that answers engineering questions and generates
specifications. Extraction (CAD/PDF → JSON) is deliberately faked for the demo by
starting from already-extracted JSON.

```
Extracted JSON  ->  Embeddings (local)  ->  Chroma  ->  Retriever
                                                            |
                                          Prompt Builder  <-+
                                                            |
                                              Local LLM (Ollama)
                                                            |
                                                   Intelligent answer
```

- **Embeddings:** ONNX `all-MiniLM-L6-v2` (local, no PyTorch)
- **Vector DB:** Chroma (persistent, file-backed)
- **LLM:** Ollama (`llama3.1:8b` by default) — falls back to a grounded
  template if Ollama isn't running, so the demo always works
- **Backend:** FastAPI · **Frontend:** React (Vite)

## Run it

On the deployed pod, everything at once (this is the normal path):

```bash
bash /workspace/persistent/start-all.sh    # Postgres, Redis, Ollama, backend, Flowise, frontend
```

If `psql`/`node`/`ollama` are missing the container disk was wiped — run
`bash /workspace/persistent/bootstrap-pod.sh` first, then the above.

From scratch, locally:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt

python -m rag.ingest data/offers        # build the vector index from the offer corpus
python -m app.auth.bootstrap admin me   # create an account — prints the password ONCE
uvicorn app.main:app --reload           # http://localhost:8000
```

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

For a production deployment read `docs/production-deployment.md` — it has two
steps (the first account, and pointing the agents at a service key) that a
fresh deploy is broken without.

## Back it up

```bash
bash ops/backup.sh          # agents, accounts + audit, job records, issued documents
bash ops/restore.sh <tarball> --dry-run
```

`pg-backup.sh` covers Postgres **only** and is not sufficient on its own: the
accounts, the audit trail, and every document the platform has ever issued live
in `backend/data/`, which nothing else copies.

## (Optional) Enable the real local LLM

```bash
# install Ollama from https://ollama.com, then:
ollama pull llama3.1:8b
```
Restart the backend. Without this, answers come from the grounded fallback.

## Use your real data

Add per-category offer files under `backend/data/offers/` (one JSON array per
file). Each record carries `category`, `source_file`, `given_data` (the client
requirement) and `technical_details` (the engineered answer); see
`wet_scrubber.json` / `paint_booth.json`. Re-run `python -m app.ingest`. To add a
new equipment type, add an entry to `CATEGORY_PROFILES` in `app/catalog.py`.

## Scale / bulk ingestion

`DATA_SOURCE` can be a single JSON file **or a directory of JSON files** (one
object or an array per file). Ingestion is **batched** (`BATCH_SIZE`, default
256) and runs as a **background job** with progress polling — so it handles
thousands of extracted CAD/PDF documents. There is no "500 file" limit; the
ceiling is your disk + vector DB, not the code.

```bash
# generate 2500 synthetic records across 50 files, then ingest the folder
python -m scripts.generate_bulk 2500
DATA_SOURCE=./data/bulk python -m app.ingest      # ~146s on CPU, batched
```

Measured: **2500 records ingested in ~146 s on CPU** (the embedding step is the
bottleneck; a GPU embedding model makes it far faster). For production, swap the
in-process job runner in `app/jobs.py` for Celery/RQ + Redis — the
`ingest_source()` call inside stays identical.

## API

**Every route except `GET /api/health` requires a credential** (since
2026-08-05). There is no default account: create the first one with
`python -m app.auth.bootstrap admin <username>` — the generated password prints
once. An empty user table locks everyone out, which is the intended failure.

The agent-facing tools, each carrying an `operation_id` that **is** the tool
name the Flowise agents see:

- `POST /api/tools/spec` → `generate_specification`
- `POST /api/tools/quote` → `generate_quotation`
- `POST /api/tools/drawing` → `generate_drawing`
- `POST /api/tools/lookup` → `lookup_project`
- `POST /api/tools/retrieve` → `retrieve_knowledge`
- `POST /api/tools/list` → `list_projects`
- `POST /api/tools/bom` → `generate_bom`
- `POST /api/tools/voc` · `/api/tools/heat-load` → safety and heat-load checks

Documents and data: `POST /api/package` (the full engineering package),
`POST /api/drawing/render`, `POST /api/bom`, `GET /api/jobs`,
`GET /api/knowledge/overview`, `GET /api/offers`.

`GET /api/health` is a status probe only; the detailed diagnostics moved to
`GET /api/admin/health/detail` behind the admin role.

> `/api/query` still exists but is **legacy and administrator-only**: it is the
> backend's own chat engine, which predates the Flowise architecture and has no
> caller in the product. The UI chat goes to the Flowise agents, which call the
> `/api/tools/*` endpoints above.
