# Vitech AI VPS — High-Level Architecture

> **Note**: This is a conceptual overview. Implementation details and business logic are kept private. 
> See [SHARING_GUIDE.md](./SHARING_GUIDE.md) for what's appropriate to share.

---

## System Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE LAYER                              │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  Frontend (React + Vite)                                            │  │
│  │  • Chat Interface (queries, context)                                │  │
│  │  • Knowledge Base Browser (offers, documents)                       │  │
│  │  • Export Functionality (PDF generation)                            │  │
│  │  • Session Management                                              │  │
│  └─────────────────────────────┬────────────────────────────────────┘  │
│                                │ HTTP/REST API                        │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                ┌────────────────▼────────────────┐
                │   API Gateway / Middleware      │
                │  • CORS policy enforcement      │
                │  • API key authentication       │
                │  • Request validation           │
                └────────────────┬────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────────┐
│                     BACKEND APPLICATION LAYER                              │
│                        (FastAPI Framework)                                │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ REQUEST ORCHESTRATION                                             │   │
│  │                                                                    │   │
│  │  • Agent routing (determines which processing path)              │   │
│  │  • Multi-turn conversation tracking                              │   │
│  │  • Response assembly from multiple stages                        │   │
│  └────────────────┬─────────────────────────────────────────────┘   │
│                   │                                                 │
│  ┌────────────────▼────────────────────────────────────────────┐   │
│  │ REQUEST PROCESSING PIPELINE                                │   │
│  │                                                             │   │
│  │  Query Input                                               │   │
│  │    ├─► Intent & Entity Understanding                       │   │
│  │    │   (Classify intent, extract parameters)              │   │
│  │    │                                                       │   │
│  │    ├─► Knowledge Retrieval                                │   │
│  │    │   (Multi-stage search with filtering)                │   │
│  │    │                                                       │   │
│  │    ├─► Analysis & Synthesis                               │   │
│  │    │   (Deterministic processing + LLM)                   │   │
│  │    │                                                       │   │
│  │    └─► Response Generation                                │   │
│  │        (Answer assembly with sources & metadata)          │   │
│  │                                                             │   │
│  │  ──────────────────────────────► Answer Output             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ EXTERNAL INTEGRATIONS                                     │ │
│  │  • Tool endpoints for agentic workflows                   │ │
│  │  • PDF export services                                    │ │
│  │  • Session management                                     │ │
│  │  • Administrative operations                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────┬────────────────┬───────────────┬─────────────┘
                   │                │               │
       ┌───────────▼───┐  ┌────────▼────┐  ┌──────▼──────────┐
       │ RAG ENGINE    │  │ STORAGE &   │  │ EXTERNAL        │
       │ (Search)      │  │ CACHE       │  │ SERVICES        │
       │               │  │             │  │                 │
       └───────────────┘  └─────────────┘  └──────────────┘
```

---

## Data Flow — Query to Answer

```
┌──────────────┐
│ User Query   │
└──────┬───────┘
       │
       ▼
┌────────────────────────┐
│ UNDERSTAND INTENT      │
│ • Classify request     │
│ • Extract key info     │
│ • Route to agent       │
└──────┬────────────────┘
       │
       ▼
┌────────────────────────┐
│ RETRIEVE KNOWLEDGE     │
│ • Check cache          │
│ • Semantic search      │
│ • Apply filters        │
│ • Rerank & select      │
└──────┬────────────────┘
       │
       ▼
┌────────────────────────┐
│ ANALYZE & PROCESS      │
│ • Match patterns       │
│ • Deterministic logic  │
│ • Prepare context      │
└──────┬────────────────┘
       │
       ▼
┌────────────────────────┐
│ SYNTHESIZE ANSWER      │
│ • LLM generation       │
│ • Fallback options     │
│ • Format response      │
└──────┬────────────────┘
       │
       ▼
┌────────────────────────┐
│ RETURN & LOG           │
│ • Answer text          │
│ • Source attribution   │
│ • Confidence signals   │
│ • Save to session      │
└────────────────────────┘
```

---

## RAG Retrieval Pipeline (Multi-Stage)

```
Search Query
│
├─ Stage 1: CACHE CHECK
│  └─► Check cache for previous results
│      Hit? → return immediately
│      Miss? → continue
│
├─ Stage 2: SEMANTIC SEARCH
│  ├─► Embed query
│  ├─► Find similar vectors in database
│  ├─► Retrieve top candidates
│  └─► Each result tagged with metadata
│
├─ Stage 3: PERMISSION FILTERING
│  ├─► Check access level
│  ├─► Apply role-based restrictions
│  └─► Drop unauthorized results
│
├─ Stage 4: INTELLIGENT RERANKING
│  ├─► Combine multiple relevance signals:
│  │   • Semantic similarity
│  │   • Keyword matching
│  │   • Metadata matching
│  └─► Fuse scores to reorder results
│
├─ Stage 5: DIVERSITY SELECTION
│  ├─► Prevent single-source dominance
│  ├─► Balance result variety
│  └─► Apply pagination limits
│
└─ Stage 6: CACHE RESULTS
   └─► Store for future identical queries
```

---

## Chunking Strategy

```
Document Processing Pipeline
│
├─ INPUT FORMATS
│  • PDF documents
│  • Word documents (DOCX)
│  • Excel spreadsheets
│
├─ EXTRACTION PHASE
│  ├─ Extract text content
│  ├─ Identify document structure
│  ├─ Parse tables separately
│  └─ Tag sections & pages
│
├─ SEGMENTATION RULES
│  │
│  ├─ Rule 1: RESPECT STRUCTURE
│  │  └─ Keep tables intact (not split)
│  │     Keep sections as coherent units
│  │
│  ├─ Rule 2: SMART WINDOWING
│  │  └─ Break prose into sized chunks
│  │     Preserve context with overlap
│  │     Maintain section boundaries
│  │
│  └─ Rule 3: RICH METADATA
│     └─ Tag each chunk with:
│        • Page number
│        • Section name
│        • Content type (text/table)
│        • Source document
│
├─ METADATA EXTRACTION (Priority Order)
│  │
│  ├─ Level 1: Explicit Metadata
│  │  └─ Passed by operator (most reliable)
│  │
│  ├─ Level 2: Document Content
│  │  └─ Extracted from text (moderate reliability)
│  │
│  └─ Level 3: Filename Parsing
│     └─ Inferred from filename (best-effort)
│
└─ OUTPUT: INDEXED CHUNKS
   └─ Chunks with all metadata stored
```

---

## Permissions & Access Control

```
┌────────────────────────────────────────┐
│ REQUEST WITH ROLE HEADER               │
└────────────────┬───────────────────────┘
                 │
                 ▼
         ┌───────────────────┐
         │ Extract Principal │
         │ (user role)       │
         └────────┬──────────┘
                  │
                  ▼
    ┌─────────────────────────────┐
    │ Check Access Policies       │
    │ • Are restrictions enabled? │
    │ • Is user privileged?       │
    └────────────┬────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    NO   ▼                ▼   YES
  ┌────────────┐   ┌─────────────┐
  │ ALLOW ALL  │   │ FILTER DOCS │
  │ (default)  │   │ (by role)   │
  └─────┬──────┘   └────────┬────┘
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Return Results    │
        │ (approved only)   │
        └───────────────────┘
```

**Key Concepts**:
- Role is determined per-request (from headers)
- Access rules are configuration-driven
- Default is permissive (single-team setup)
- Can be enabled per deployment

---

## Technology Stack

| Layer | Purpose | Technology |
|-------|---------|-----------|
| **Frontend** | User interface | React, Vite |
| **API Server** | REST framework | FastAPI |
| **Runtime** | Python async | Uvicorn |
| **Vector Store** | Semantic search | ChromaDB |
| **LLM Engine** | Text generation | External (HTTP-based) |
| **Cache Layer** | Session + query | Redis (with fallback) |
| **Document Loading** | PDF extraction | pdfplumber |
| **Document Loading** | Word extraction | python-docx |
| **Document Loading** | Excel extraction | openpyxl |
| **PDF Export** | Report generation | fpdf2 |
| **Validation** | Request schemas | Pydantic |
| **Security** | API authentication | Header-based keys |

---

## Deployment Architecture

```
┌──────────────────────────────────────────────────┐
│         Docker Compose Orchestration             │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │ Services (Containerized)                 │   │
│  │  • Backend API                           │   │
│  │  • Frontend (Nginx reverse proxy)        │   │
│  │  • Vector database                       │   │
│  │  • Cache service                         │   │
│  │  • (Optional) LLM inference              │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │ Persistent Storage (Volumes)             │   │
│  │  • Vector embeddings                     │   │
│  │  • Ingested documents                    │   │
│  │  • Session data                          │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │ Internal Networking                      │   │
│  │  • Inter-service communication           │   │
│  │  • Isolated from external traffic        │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

---

## Key Architectural Principles

### 1. **Deterministic First**
- Numerical outputs (specifications, pricing) come from rules and historical data
- LLM is used only for prose synthesis, not calculations
- Ensures reproducibility and auditability

### 2. **Structure-Aware Chunking**
- Respects document structure (sections, tables)
- Prevents breaking tables or coherent blocks
- Enables filtering by document sections

### 3. **Multi-Stage Retrieval**
- Cache first (fast hits for repeated queries)
- Semantic search (meaning-based matching)
- Hybrid reranking (combines multiple signals)
- Permission filtering (access control in the pipeline)

### 4. **Graceful Degradation**
- LLM unavailable? → Fall back to templated responses
- Cache service down? → Use in-memory alternatives
- Core functionality remains available

### 5. **Privacy-by-Design**
- Permission filtering is built into the retrieval pipeline
- Configuration-driven (no code changes needed for access control)
- Default-safe: starts permissive, tighten via config

---

## API Endpoint Categories

### Core Functionality
- `/api/query` — Main question answering endpoint
- `/api/session/*` — Conversation history management

### Tool Integration
- `/api/tools/spec` — Generate specifications
- `/api/tools/quote` — Generate quotations
- `/api/tools/lookup` — Project/client search
- `/api/tools/retrieve` — Knowledge base search
- `/api/tools/list` — Enumerate stored records
- `/api/tools/filters` — Get available filter options

### Knowledge Management
- `/api/ingest` — Upload and index documents
- `/api/offers` — Browse stored records
- `/api/knowledge/overview` — KB statistics and metadata

### Export & Admin
- `/api/specification/pdf` — Export specification as PDF
- `/api/quotation/pdf` — Export quotation as PDF
- `/api/admin/reload-index` — Refresh search index

### Monitoring
- `/api/health` — Service status and diagnostics

---

## Folder Structure (Top-Level)

```
vitech-ai-vps/
│
├── backend/              # FastAPI application + RAG pipeline
│   ├── app/              # Application logic
│   ├── rag/              # Retrieval & ingestion
│   ├── data/             # Documents & embeddings
│   └── tests/            # Test suites
│
├── frontend/             # React application
│   ├── src/              # Components & logic
│   ├── public/           # Static assets
│   └── dist/             # Build output
│
├── scripts/              # Utility & setup scripts
├── docs/                 # Documentation
├── docker-compose.yml    # Service orchestration
├── ARCHITECTURE.md       # This file
├── SHARING_GUIDE.md      # Sharing policies
└── README.md             # Project overview
```

---

## Configuration Management

Configuration is **environment-driven** (not hardcoded):

- **Source**: `.env` file (not checked into version control)
- **Template**: `.env.example` (checked in, with placeholders)
- **Processing**: Loaded and validated by `config.py` at startup
- **Types**: Configuration keys cover:
  - Data source locations
  - Storage paths
  - External service endpoints
  - Behavior tuning parameters
  - Security policies

See `.env.example` for all available configuration options.

---

## Integration Points

### External Services
- **LLM**: HTTP-based inference service
- **Cache**: Redis or compatible service
- **Vector DB**: ChromaDB or compatible vector store

### Inbound Interfaces
- **User Interface**: Web browser (HTTP/REST)
- **Agent Systems**: Tool endpoints for orchestration
- **Admin Tools**: Ingest and management endpoints

### Outbound Integrations
- **File Export**: PDF generation (client-side)
- **Document Upload**: File ingestion pipeline
- **Session Storage**: Cache service for persistence

---

## Design Trade-offs

| Decision | Rationale |
|----------|-----------|
| Deterministic first | Ensures reproducible, auditable results |
| Multi-stage retrieval | Balances relevance, performance, and fairness |
| Structure-aware chunking | Preserves document semantics for better search |
| Configuration-driven | Easy to adapt behavior without code changes |
| Graceful degradation | System remains functional if components fail |
| Permission filtering in pipeline | Access control is fast and secure |

---

## See Also

- **[SHARING_GUIDE.md](./SHARING_GUIDE.md)** — What's safe to share publicly
- **[requirements.txt](./backend/requirements.txt)** — Dependencies
- **[README.md](./README.md)** — Project overview
- **[.env.example](./.env.example)** — Configuration template
