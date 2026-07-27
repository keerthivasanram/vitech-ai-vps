# Vitech AI VPS — High-Level Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE LAYER                               │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Frontend (React + Vite)                                             │  │
│  │  • Chat Interface (queries, context)                                 │  │
│  │  • Knowledge Base Browser (offers, documents, specifications)        │  │
│  │  • PDF Export (quotations, specs)                                    │  │
│  │  • Session Management (history, uploads)                             │  │
│  └────────────────────────────┬─────────────────────────────────────────┘  │
│                               │ HTTP/REST                                   │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
                ┌───────────────▼───────────────┐
                │   API Gateway / Middleware   │
                │  • CORS                      │
                │  • API Key Auth              │
                │  • Session Validation        │
                └───────────────┬───────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────────────────┐
│                       BACKEND APPLICATION LAYER                              │
│                          (FastAPI - main.py)                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AGENT ORCHESTRATION LAYER (agent_router.py)                        │   │
│  │                                                                     │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │   │
│  │  │ Consulting   │  │  Quotation   │  │  Analysis Agent      │    │   │
│  │  │ Engineer     │  │  Engineer    │  │  (Spec Generator)    │    │   │
│  │  │              │  │              │  │                      │    │   │
│  │  │ • Asks for   │  │ • Deterministic
│  │  │   missing    │  │   pricing    │  │ • Calculates:        │    │   │
│  │  │   inputs     │  │ • BOM gen    │  │   - Dimensions       │    │   │
│  │  │ • Route to   │  │ • Validation │  │   - Flow rates       │    │   │
│  │  │   appropriate│  │ • Hybrid     │  │   - Pressures        │    │   │
│  │  │   agent      │  │   threshold  │  │   - Materials        │    │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ REQUEST PROCESSING PIPELINE                                         │ │
│  │                                                                      │ │
│  │  Query ──────────────────────────────────────────────────────────┐  │ │
│  │    │                                                              │  │ │
│  │    ├─► understand()        [Intent + Entity Extraction]         │  │ │
│  │    │   (LLM JSON mode OR regex fallback)                        │  │ │
│  │    │                                                              │  │ │
│  │    ├─► retrieve()          [Multi-stage Retrieval]              │  │ │
│  │    │   • Cache lookup (Redis)                                   │  │ │
│  │    │   • Vector search (ChromaDB)                               │  │ │
│  │    │   • Permission filter (ACL)                                │  │ │
│  │    │   • Hybrid rerank (dense + lexical + RRF)                  │  │ │
│  │    │   • Diversity select (max 3 per source doc)                │  │ │
│  │    │                                                              │  │ │
│  │    ├─► analyze()           [Spec + Metadata Assembly]           │  │ │
│  │    │   (rules + historical matching)                            │  │ │
│  │    │                                                              │  │ │
│  │    └─► generate_answer()   [LLM Synthesis + Fallback]           │  │ │
│  │        (Ollama HTTP + templated fallback)                       │  │ │
│  │                                                                   │  │ │
│  │    ─────────────────────────────────────────────────────► Answer │  │ │
│  └──────────────────────────────────────────────────────────────────┘ │ │
│                                                                          │ │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ TOOL ENDPOINTS (Flowise Integration)                               │ │
│  │                                                                      │ │
│  │  /api/tools/spec          → generate_specification()               │ │
│  │  /api/tools/quote         → generate_quotation()                   │ │
│  │  /api/tools/lookup        → lookup_project()                       │ │
│  │  /api/tools/retrieve      → retrieve_knowledge()                   │ │
│  │  /api/tools/list          → list_projects()                        │ │
│  │  /api/tools/filters       → list_filters()                         │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐  ┌────▼──────┐  ┌──▼──────────────┐
│ RAG ENGINE   │  │ STORAGE   │  │ EXTERNAL        │
│ (rag/)       │  │ & CACHE   │  │ SERVICES        │
│              │  │           │  │                 │
└───────┬──────┘  └────┬──────┘  └──┬───────────────┘
        │              │            │
        │              │            │
┌───────▼──────────────▼────────────▼─────────────────────────────────────┐
│                                                                         │
│  ┌──────────────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │ RETRIEVAL ENGINE     │  │ PERSISTENT STORE │  │ EXTERNAL       │   │
│  │ (retrieve.py)        │  │                  │  │ LLM            │   │
│  │                      │  │ ChromaDB         │  │                │   │
│  │ • Vector search      │  │ • Embeddings     │  │ Ollama HTTP    │   │
│  │   (cosine sim)       │  │ • Metadata       │  │ (localhost:    │   │
│  │ • Sparse search      │  │ • Chunks + docs  │  │  11434)        │   │
│  │   (BM25 OR lexical)  │  │                  │  │                │   │
│  │ • Reranking          │  │ path:            │  │ Models:        │   │
│  │   (RRF fusion +      │  │ backend/         │  │ • llama3.1:8b  │   │
│  │    metadata boost)   │  │ chroma_store/    │  │ • Other        │   │
│  │ • Permission filter  │  │                  │  │   (configurable)
│  │ • Chunk diversity    │  │                  │  │                │   │
│  │   selection          │  │                  │  │                │   │
│  └──────────────────────┘  └──────────────────┘  └────────────────┘   │
│                                                                         │
│  ┌──────────────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │ INGESTION PIPELINE   │  │ CACHING LAYER    │  │ SESSION STORE  │   │
│  │ (ingest.py)          │  │ (cache.py)       │  │                │   │
│  │                      │  │                  │  │ Redis          │   │
│  │ • Document loading   │  │ • Query cache    │  │ • User sessions│   │
│  │   (PDF/DOCX/XLSX)    │  │   (Redis)        │  │ • Chat history │   │
│  │ • Batched chunking   │  │ • Fallback LRU   │  │ • Metadata     │   │
│  │   (structure-aware)  │  │   (in-process)   │  │                │   │
│  │ • Metadata extract   │  │ • TTL: 15 min    │  │ (Falls back to │   │
│  │   (explicit→body→    │  │                  │  │  in-process if │   │
│  │    filename)         │  │                  │  │  Redis down)   │   │
│  │ • Embedding gen      │  │                  │  │                │   │
│  │ • ChromaDB insert    │  │                  │  │                │   │
│  │   (batched: 256)     │  │                  │  │                │   │
│  └──────────────────────┘  └──────────────────┘  └────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow — Query to Answer

```
┌──────────────┐
│ User Query   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│ 1. UNDERSTAND INTENT         │
│    • Classify equipment type │
│    • Extract parameters      │
│    • Detect intent (spec/    │
│      quote/lookup/retrieve)  │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 2. ROUTE TO AGENT            │
│    • Check completeness      │
│    • If <60% inputs:         │
│      → Consulting Engineer   │
│      (ask for missing info)  │
│    • If ≥60% inputs:         │
│      → Quotation Engineer    │
│      (build spec + quote)    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 3. RETRIEVE KNOWLEDGE        │
│    • Cache hit? → return     │
│    • Vector search (top 24)  │
│    • Filter by permissions   │
│    • Hybrid rerank           │
│    • Select diverse top-6    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 4. ANALYZE (Deterministic)   │
│    • Match to historical     │
│    • Calculate specs         │
│    • Price from rules        │
│    • Confidence + sources    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 5. SYNTHESIZE (LLM)          │
│    • Send: retrieved context │
│      + analysis + history    │
│    • Ollama generates prose  │
│    • Fallback: template      │
│      if LLM unavailable      │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 6. RETURN ANSWER             │
│    • Text (prose)            │
│    • Metadata (sources, etc) │
│    • Flags (grounded?,       │
│      complete?, confidence)  │
│    • Session update          │
└──────────────────────────────┘
```

---

## Configuration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ENVIRONMENT (.env)                        │
│                                                             │
│  DATA_FILE=./data/sample_documents.json                     │
│  CHROMA_DIR=./chroma_store                                  │
│  COLLECTION_NAME=engineering_knowledge                      │
│  OLLAMA_HOST=http://localhost:11434                         │
│  OLLAMA_MODEL=llama3.1:8b                                   │
│  REDIS_URL=redis://localhost:6379/0                         │
│  VITECH_API_KEY=<secret>                                    │
│  RESTRICTED_DOC_CATEGORIES=confidential,internal            │
│  PRIVILEGED_ROLES=admin,lead_engineer                       │
│  ...                                                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  config.py (Python)    │
    │                        │
    │  • Loads .env via      │
    │    dotenv.load_dotenv()│
    │  • Type conversion     │
    │  • Defaults if missing │
    │  • Validation          │
    │                        │
    │  Exports:             │
    │  - TOP_K              │
    │  - CHUNK_SIZE         │
    │  - HYBRID_THRESHOLD   │
    │  - OLLAMA_*           │
    │  - REDIS_*            │
    │  - RESTRICTED_*       │
    │  - etc.               │
    └────────────┬───────────┘
                 │
    ┌────────────▼───────────────────────────────────┐
    │  Application Imports                           │
    │                                                │
    │  from app import config                        │
    │  config.TOP_K                 # 6              │
    │  config.OLLAMA_HOST           # HTTP endpoint  │
    │  config.RESTRICTED_DOC_CATEGORIES # ACL        │
    └────────────────────────────────────────────────┘
```

---

## RAG Retrieval Pipeline (Multi-Stage)

```
Query: "What's the pressure drop for a 500 CFM wet scrubber?"
│
├─ Stage 1: CACHE CHECK
│  └─► Redis key: hash(query + filters + k)
│      Hit? → return cached hits (15 min TTL)
│      Miss? → continue to Stage 2
│
├─ Stage 2: VECTOR SEARCH
│  ├─► Embed query (Ollama embeddings)
│  ├─► Cosine similarity in ChromaDB
│  ├─► Retrieve top 24 candidates (RETRIEVE_CANDIDATES)
│  └─► Each hit: {text, page, section, equipment_type, score, ...}
│
├─ Stage 3: PERMISSION FILTER
│  ├─► Read principal from X-Role header
│  ├─► If doc_category in RESTRICTED_DOC_CATEGORIES:
│  │   └─► Only allow if principal.role in PRIVILEGED_ROLES
│  └─► Drop unauthorized hits
│
├─ Stage 4: HYBRID RERANKING
│  ├─► For each hit:
│  │   ├─ Dense rank = 1 / (rank + RERANK_RRF_K)        [vector order]
│  │   ├─ Lexical rank = 1 / (bm25_rank + RRF_K)        [keyword order]
│  │   ├─ Metadata boost if equipment_type matches      [ACL-like]
│  │   └─ Fused score = w_dense * dense + w_lex * lex + mag * score
│  │
│  └─► Re-sort by fused score
│
├─ Stage 5: DIVERSITY SELECT
│  ├─► Group by source_file
│  ├─► Max 3 chunks per file (SELECT_MAX_PER_DOC)
│  ├─► Keep top-K overall (request.top_k = 6)
│  └─► Final hits sorted by rerank score
│
└─ Stage 6: CACHE STORE
   └─► Redis: key = hits + TTL 15 min
```

---

## Chunking Strategy (Structure-Aware)

```
Source Document (PDF/DOCX/XLSX)
│
├─► Load blocks via pdfplumber/python-docx/openpyxl
│
├─ Example blocks:
│  • {kind: 'heading', text: 'Operating Conditions', page: 3}
│  • {kind: 'prose', text: 'Lorem ipsum...', page: 3}
│  • {kind: 'table', text: '| Param | Value |\n| --- | --- |', page: 4}
│
├─► Chunk via chunker.py:
│
│  Rule 1: TABLE blocks NEVER split
│  └─► Chunk(text=full_table, section='Operating Conditions', kind='table')
│
│  Rule 2: PROSE split on SECTION boundaries first
│  ├─► Detect section headings (regex)
│  ├─► Group lines by active section
│  └─► For each section group, window by words:
│      └─► chunk_size=220, overlap=40
│      └─► Sliding window: [0-219], [180-399], [360-579], ...
│
│  Rule 3: Every chunk tagged
│  └─► Chunk {
│        text: "...",
│        page: 3,
│        section: "Operating Conditions",
│        kind: "text"  or "table"
│      }
│
└─► Metadata Extraction (3-tier priority):
    ├─ Explicit: {customer: "Acme", equipment_type: "wet_scrubber"}
    │   (passed by human running ingest)
    │
    ├─ Body: {customer: "Acme Corp", date: "2024-01-15"}
    │   (regex from document text: "Customer: Acme Corp")
    │
    └─ Filename: {revision: "R3", date: "2024-01-15"}
        (parse: "ACME_WS_R3_240115.pdf" → R3, 240115)
        
    Merge: explicit > body > filename (priority order)
    Source: {customer: "explicit", equipment_type: "explicit", date: "filename"}
```

---

## Permissions & Access Control

```
REQUEST HEADER: X-Role: engineer
  │
  └─► Principal(role="engineer")
      │
      ├─► Check config.RESTRICTED_DOC_CATEGORIES
      │   (e.g., {"confidential", "internal"})
      │
      ├─► For each retrieved chunk:
      │   ├─ chunk["doc_category"] == "confidential"?
      │   ├─ Is "engineer" in config.PRIVILEGED_ROLES?
      │   │  YES → include chunk
      │   │  NO  → drop chunk
      │   │
      │   └─ chunk["doc_category"] == "public"?
      │      YES → include (no restriction)
      │
      └─► Return only allowed chunks
```

**Default Behavior** (Single-Team):
- `RESTRICTED_DOC_CATEGORIES = ""` (empty)
- Every principal sees everything
- Permission filter is a no-op (all chunks allowed)

**With ACL Enabled**:
- `RESTRICTED_DOC_CATEGORIES = "confidential,internal"`
- `PRIVILEGED_ROLES = "admin,lead_engineer"`
- Only `admin` & `lead_engineer` see restricted docs
- Others see public docs only

---

## Technology Stack

| Layer | Component | Tech |
|-------|-----------|------|
| **UI** | Frontend | React 18, Vite, Framer Motion, Lucide Icons |
| **API** | Web Framework | FastAPI (Python) |
| **Server** | ASGI | Uvicorn |
| **Vector DB** | Embeddings + Search | ChromaDB (persistent) |
| **LLM** | Inference | Ollama (HTTP) — llama3.1:8b |
| **Cache** | Query + Sessions | Redis (or in-process LRU fallback) |
| **Extraction** | PDFs | pdfplumber |
| **Extraction** | DOCX | python-docx |
| **Extraction** | XLSX | openpyxl |
| **Export** | PDF Gen | fpdf2 (pure-Python) |
| **Validation** | Schema | Pydantic |
| **Auth** | API Security | X-API-Key header |
| **CORS** | Cross-Origin | CORSMiddleware |

---

## Deployment Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    docker-compose.yml                    │
│                                                          │
│  Services:                                               │
│  ├─ backend        (FastAPI, Python)                    │
│  ├─ frontend       (React, Nginx)                       │
│  ├─ chroma         (ChromaDB, if containerized)         │
│  ├─ redis          (Session + cache store)              │
│  └─ ollama         (LLM inference, optional container)  │
│                                                          │
│  Volumes:                                                │
│  ├─ chroma_data    (persistent embeddings)              │
│  ├─ backend_data   (ingested offers JSON)               │
│  └─ redis_data     (session persistence)                │
│                                                          │
│  Networks:                                               │
│  └─ internal       (inter-service communication)         │
└──────────────────────────────────────────────────────────┘
```

---

## Key Design Principles

1. **Deterministic First**
   - All numbers (specs, pricing) come from rules + historical data
   - LLM writes prose only; never computes values

2. **Structure-Aware Chunking**
   - Tables kept atomic (not split)
   - Sections preserved for context
   - Pages + sections tagged for filtering

3. **Multi-Stage Retrieval**
   - Cache first (Redis)
   - Vector search (semantic)
   - Hybrid reranking (dense + sparse + metadata)
   - Permission filtering (ACL-ready)

4. **Graceful Degradation**
   - Ollama unavailable? → Fallback to templated answers
   - Redis down? → In-process LRU cache
   - All components optional; core flow runs standalone

5. **Privacy-by-Hook**
   - Permission filter wired in retrieval path
   - Config-driven (no code changes for ACL)
   - Default allow-all (single-team); enable per config

---

## API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Service status, document count, LLM info |
| `/api/query` | POST | Full pipeline: understand → retrieve → analyze → answer |
| `/api/query/stream` | POST | Same, but token-by-token streaming (SSE) |
| `/api/session/{id}` | GET | Chat history for session |
| `/api/session/{id}` | DELETE | Clear session |
| `/api/ingest` | POST | Start background document ingestion |
| `/api/ingest/{job_id}` | GET | Ingest progress |
| `/api/tools/spec` | POST | Generate specification (deterministic) |
| `/api/tools/quote` | POST | Generate quotation (pricing) |
| `/api/tools/lookup` | POST | Lookup project / client record |
| `/api/tools/retrieve` | POST | RAG search with metadata filters |
| `/api/tools/list` | POST | Enumerate stored offers |
| `/api/tools/filters` | GET | Available filter values (for UI) |
| `/api/specification/pdf` | POST | Export spec to PDF |
| `/api/quotation/pdf` | POST | Export quote to PDF |
| `/api/offers` | GET | All stored offers overview |
| `/api/offers/{id}` | GET | Full offer record |
| `/api/knowledge/overview` | GET | KB stats, categories, facets |
| `/api/admin/reload-index` | POST | Refresh ChromaDB cache |

---

## Folder Structure Reference

```
backend/
├── app/                          # FastAPI application
│   ├── main.py                   # Entry point + routes
│   ├── config.py                 # Configuration management
│   ├── agent_router.py           # Agent orchestration
│   ├── understand.py             # Query parsing + intent
│   ├── retriever.py              # Multi-stage retrieval
│   ├── analysis.py               # Spec calculations
│   ├── quotation.py              # Pricing engine
│   ├── llm.py                    # Ollama wrapper
│   ├── session.py                # Session storage
│   ├── analytics.py              # Usage tracking
│   └── [other services...]
│
├── rag/                          # Retrieval-Augmented Generation
│   ├── ingest.py                 # Document ingestion pipeline
│   ├── loader.py                 # File extraction
│   ├── chunker.py                # Structure-aware chunking
│   ├── metadata.py               # 3-tier metadata extraction
│   ├── retrieve.py               # Vector search
│   ├── reranker.py               # Hybrid reranking
│   ├── permissions.py            # ACL filtering
│   ├── cache.py                  # Redis caching
│   └── [other RAG modules...]
│
├── data/
│   ├── offers/                   # Ingested JSON offers
│   └── chroma_store/             # ChromaDB persistent store
│
├── requirements.txt
└── Dockerfile

frontend/
├── src/
│   ├── App.jsx                   # Main component
│   ├── pages/                    # Route components
│   ├── components/               # Reusable UI
│   ├── hooks/                    # Custom React hooks
│   ├── lib/                      # Utilities
│   └── styles/                   # CSS
├── package.json
└── Dockerfile
```
