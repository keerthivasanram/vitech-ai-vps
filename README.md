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

## Run the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt

python -m app.ingest             # build the vector index from data/sample_documents.json
uvicorn app.main:app --reload    # http://localhost:8000
```

## Run the frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

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

- `GET  /api/health` — index size + LLM config
- `POST /api/ingest` — start batched background ingestion → returns `job_id`
- `GET  /api/ingest/{job_id}` — poll ingestion progress/status
- `POST /api/query`  — `{ "question": "..." }` → answer + sources + steps
