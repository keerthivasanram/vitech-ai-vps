# `rag/` — Production Document Ingestion & Metadata-Filtered Retrieval

Turns real engineering documents (PDF / DOCX / XLSX / JSON / TXT) into
richly-tagged, section-aware chunks in ChromaDB, so the Engineering Agent can
**filter by equipment type, customer, project, document category, revision or
section BEFORE semantic search** — far more accurate than vector similarity
alone.

This is **additive** to the offer pipeline (`app/ingest.py`). Documents are
stored under `type="document"` in the *same* collection; the deterministic ATS
spec/quote engine only ever reasons over `type="offer"`, so ingesting documents
cannot change any calculated number. (Proven by `tests_golden.py` staying ALL
PASS with documents present.)

## Pipeline

```
file ─▶ loader ─▶ (metadata: filename + body + explicit) ─▶ chunker ─▶ Chroma
        │            │                                        │
   pages+tables   merged, priority: explicit > body > filename  section-aware,
   preserved                                                  tables kept whole
```

| Module | Responsibility |
|---|---|
| `loader.py` | Extract structure-preserving `Block`s — page numbers (PDF), tables (cleanly separated from prose via bbox filtering), prose. |
| `metadata.py` | Resolve customer / project / equipment_type / doc_category / revision / offer_number / date from **three layers** (explicit > body text > filename). Never invents a value; records which layer won. |
| `sections.py` | Heading-based detection of engineering sections (scope, technical_specification, bill_of_materials, price_schedule, terms_and_conditions, …). |
| `chunker.py` | Chunk prose by section then by word window; **tables are never split**. Every chunk carries page + section. |
| `ingest.py` | Orchestrates the above, writes rich metadata to Chroma, returns an **IngestReport** flagging low-confidence fields for engineer review (human-in-the-loop). |
| `retrieve.py` | `retrieve_documents(question, filters=…)` — hard metadata `$and` filter, then semantic search, with broaden-on-empty. `available_filters()` lists valid facet values. |

## Metadata written per chunk

`type` (=`document`), `source_file`, `title`, `customer`, `project`,
`equipment_type`, `doc_category`, `revision`, `offer_number`, `date` (ISO),
`section`, `page`, `kind` (`text`/`table`), `chunk_index`, `chunk_count`, plus
`_raw` (full chunk record JSON, matching the offer-pipeline convention).

## Usage

```bash
cd backend

# ingest a folder of documents (metadata auto-resolved, review the report)
python -m rag.ingest data/knowledge_docs/

# a single file with explicit overrides (win over body/filename)
python -m rag.ingest "offers/KOBELCO _DRY TYPE BOOTH_R2210324.pdf" \
    --customer "Kobelco" --equipment-type paint_booth --doc-category offer

# per-file overrides for a batch, via a manifest
python -m rag.ingest data/knowledge_docs/ --manifest overrides.json
#   overrides.json:  {"SomeFile.pdf": {"customer": "...", "equipment_type": "..."}}
```

Do **not** pass `--reset` unless you intend to wipe the whole collection
(offers included) — normal runs are idempotent upserts.

## Retrieval (what Flowise / the agent calls)

```python
from rag.retrieve import retrieve_documents, available_filters

retrieve_documents(
    "tower height and diameter",
    filters={"equipment_type": "wet_scrubber", "section": "technical_specification"},
)
```

If a filter is too specific and matches nothing, retrieval automatically
broadens (equipment_type only → then documents only) rather than returning
empty.

## Embedding model — do not change

Ingestion and retrieval both go through `app/store.py` (ONNX
`all-MiniLM-L6-v2`). Writing and reading Chroma with different embedding models
silently breaks retrieval (the project's #1 gotcha). Re-ingest if you ever
change the model.
