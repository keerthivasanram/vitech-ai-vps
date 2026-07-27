# Project Sharing Guide

> **For safely sharing this project with colleagues at other companies**

---

## Overview

This guide clarifies what can and cannot be shared from the Vitech AI VPS project, based on confidentiality, intellectual property, and business sensitivity.

**Golden Rule**: When in doubt, **don't share**. Ask yourself: *Would sharing this give away our competitive advantage, expose customer data, or violate security?*

---

## ✅ Safe to Share (Review First)

These items are acceptable to share **after confirming they contain no confidential information**.

### Documentation
- [ ] High-level folder structure (top-level folders only)
- [ ] `requirements.txt` (public libraries only)
- [ ] `ARCHITECTURE.md` (conceptual diagrams, no implementation details)
- [ ] Generic architecture diagrams (e.g., "Query → Retrieve → Analyze → Answer")
- [ ] High-level tech stack overview
- [ ] `README.md` (after removing internal notes and links)
- [ ] This `SHARING_GUIDE.md`

### Configuration Templates
- [ ] `.env.example` **with placeholders only** (no real values)
- [ ] `config.py` **structure only** (keys, not values)
- [ ] Config schema/keys (without defaults or tuning parameters)

### API Design
- [ ] API endpoint names and routes
- [ ] HTTP method (GET/POST/DELETE)
- [ ] Request/response structure (parameter names only, not business logic)
- [ ] Error codes

### Example Data
- [ ] Dummy/sample datasets you created
- [ ] Synthetic test cases (no real customer data)
- [ ] Mock API responses (sanitized)

### General Patterns
- [ ] Design patterns (e.g., "multi-stage retrieval pipeline")
- [ ] Architectural concepts (e.g., "permission filtering happens after vector search")
- [ ] Technology choices and trade-offs
- [ ] Deployment approach (docker-compose, containerization concepts)

---

## ⚠️ Share Only After Sanitizing

These require careful review and removal of sensitive details.

### Configuration Files
- [ ] `docker-compose.yml` — Remove internal hosts, ports, credentials, real service names
- [ ] `Dockerfile` — OK to share if no secrets embedded
- [ ] Build scripts — Remove paths, credentials, internal references

### Folder Structure
- [ ] **Top-level only** is safe (`backend/`, `frontend/`, `scripts/`)
- [ ] **Do NOT share** subdirectory structure that reveals business logic
  - ❌ `backend/app/pricing.py` (reveals pricing engine exists)
  - ❌ `backend/rag/reranker.py` (reveals reranking strategy)
  - ❌ `backend/engineering/` (reveals internal calculations)

### Diagrams & Documentation
- [ ] Remove specific threshold values (e.g., `TOP_K=6`, `HYBRID_THRESHOLD=0.6`)
- [ ] Remove specific model names or versions (e.g., `llama3.1:8b`)
- [ ] Remove internal metric names or calculations
- [ ] Generic version OK: "LLM for prose generation", not "Ollama with llama3.1:8b"

### Database Schema
- [ ] Only if it contains **no business logic** or customer data
- [ ] Metadata fields must be generic, not company-specific

---

## ❌ Do NOT Share

### Source Code

**Application Logic**
- ❌ `app/main.py` — API routes and business logic
- ❌ `app/agent_router.py` — Agent orchestration strategy
- ❌ `app/analysis.py` — Spec generation and calculations
- ❌ `app/quotation.py` — Pricing and quotation logic
- ❌ `app/pricing.py` — Cost formulas and pricing rules
- ❌ `app/catalog.py` — Product catalog and lookup logic
- ❌ `app/engineering/` — Engineering calculations
- ❌ Any other `app/` modules

**RAG Pipeline**
- ❌ `rag/retrieve.py` — Retrieval implementation
- ❌ `rag/reranker.py` — Reranking logic and algorithms
- ❌ `rag/ingest.py` — Document ingestion strategy
- ❌ `rag/chunker.py` — Chunking algorithm and parameters
- ❌ `rag/metadata.py` — Metadata extraction rules
- ❌ `rag/permissions.py` — Access control implementation
- ❌ Any other `rag/` modules

**Scripts & Automation**
- ❌ Internal deployment scripts
- ❌ CI/CD pipeline configuration
- ❌ Backup and maintenance scripts
- ❌ Data migration scripts

### Configuration & Secrets

- ❌ `.env` file (always)
- ❌ API keys
- ❌ Tokens and authentication credentials
- ❌ Database passwords
- ❌ Redis URLs with credentials
- ❌ Ollama connection strings with internal IPs
- ❌ SSH keys
- ❌ Certificates and SSL keys
- ❌ Real configuration values
- ❌ Actual environment setup

### AI & Machine Learning Assets

- ❌ System prompts and prompt templates
- ❌ Internal instructions (e.g., `CLAUDE.md` if it contains proprietary logic)
- ❌ Prompt engineering techniques
- ❌ LLM fine-tuning data or weights
- ❌ Embedding model weights or fine-tuned models
- ❌ Internal datasets or training data
- ❌ Embedding vector indexes (ChromaDB collections)

### Business Data

- ❌ Customer PDFs and documents
- ❌ Customer quotations and pricing
- ❌ Customer contact information
- ❌ Customer order history
- ❌ Production database backups
- ❌ Chroma vector store (actual embeddings)
- ❌ Internal engineering specifications
- ❌ Historical quotations and price lists
- ❌ Proprietary product specifications

### Infrastructure

- ❌ Production VPS configuration
- ❌ Server IP addresses and hostnames
- ❌ Network architecture and topology
- ❌ Monitoring and logging configuration
- ❌ Backup and disaster recovery setup
- ❌ Infrastructure-as-Code (even if it looks generic)
- ❌ DNS configuration
- ❌ CDN or caching configuration

---

## What to Share Instead

### Option 1: Share This Guide + High-Level Docs
**Best for**: Explaining your architecture to peers

```
Share:
├── SHARING_GUIDE.md (this file)
├── ARCHITECTURE.md (conceptual overview)
├── requirements.txt (library list)
├── README.md (generic project description)
└── .env.example (template, no values)
```

### Option 2: Create a Sanitized Example Project
**Best for**: Teaching someone your approach

```
Create a minimal example:
├── example-project/
│   ├── README.md (your project structure explained)
│   ├── architecture.md (conceptual, no implementation)
│   ├── requirements.txt (same libraries)
│   ├── docker-compose-template.yml (no credentials)
│   ├── .env.example (template)
│   └── sample-api-docs.md (endpoint names only)
```

### Option 3: Give a Presentation
**Best for**: Sharing knowledge without code

- Slide deck: architecture, design decisions, tech stack
- Live demo: anonymized or mock data
- Q&A: discuss trade-offs and lessons learned
- Code snippets: generic patterns, not business logic

---

## Sharing Checklist

Before sharing **anything**, ask yourself:

- [ ] Does this contain actual customer data? → **Don't share**
- [ ] Does this reveal our pricing algorithm? → **Don't share**
- [ ] Does this expose our engineering calculations? → **Don't share**
- [ ] Does this include credentials or API keys? → **Don't share**
- [ ] Does this reveal our competitive advantage? → **Don't share**
- [ ] Does this include our system prompts? → **Don't share**
- [ ] Have I removed all internal IP addresses, ports, and hostnames? → **OK to consider**
- [ ] Have I removed all specific threshold values and tuning parameters? → **OK to consider**
- [ ] Is this a generic architectural pattern? → **OK to share**
- [ ] Is this a public library or framework? → **OK to share**

**If you answered "Don't share" to any question: STOP and don't share.**

---

## Safe Sharing Examples

### ❌ DON'T Share This
```python
# app/pricing.py
def calculate_price(equipment_type, size, material):
    base_price = PRICING_RULES[equipment_type]["base"]
    size_multiplier = size / PRICING_RULES[equipment_type]["ref_size"]
    material_cost = MATERIAL_COSTS[material] * size_multiplier
    margin = 1.35  # Our markup strategy
    return (base_price + material_cost) * margin
```

### ✅ Share This Instead
```
Our quotation engine calculates pricing from:
1. Base equipment cost (from historical data)
2. Size-based scaling (linear interpolation)
3. Material surcharges
4. Fixed margin

This ensures pricing is deterministic and consistent with past quotes.
```

---

### ❌ DON'T Share This
```python
# rag/reranker.py
RERANK_DENSE_W = 1.0        # Our tuned weight
RERANK_LEXICAL_W = 1.0      # Our tuned weight
RERANK_LEXICAL_MAG_W = 0.03 # Our tuned magnitude
RERANK_RRF_K = 60           # Our RRF constant
```

### ✅ Share This Instead
```
Our retrieval pipeline uses hybrid reranking:
1. Vector similarity (semantic match)
2. Lexical similarity (keyword match)
3. Metadata boost (if equipment type matches)
4. Reciprocal Rank Fusion (RRF) to combine signals

This ensures results are both semantically and lexically relevant.
```

---

### ❌ DON'T Share This
```yaml
# docker-compose.yml (actual)
redis:
  image: redis:7
  ports:
    - "6379:6379"
  environment:
    - REDIS_PASSWORD=vitech-secret-2024

ollama:
  image: ollama/ollama:latest
  ports:
    - "11434:11434"
  volumes:
    - /var/lib/ollama:/root/.ollama

chroma:
  image: ghcr.io/chroma-core/chroma:latest
  ports:
    - "8000:8000"
  volumes:
    - ./chroma_data:/chroma/data
```

### ✅ Share This Instead
```yaml
# docker-compose-template.yml (sanitized)
services:
  backend:
    build: ./backend
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    environment:
      REDIS_URL: ${REDIS_URL}
      OLLAMA_HOST: ${OLLAMA_HOST}
    depends_on:
      - redis
      - ollama

  redis:
    image: redis:7
    # Configure connection in .env.example

  ollama:
    image: ollama/ollama:latest
    # Configure model via environment

  # See .env.example for all configuration
```

---

## Common Mistakes to Avoid

| ❌ Mistake | ✅ Better Approach |
|-----------|-------------------|
| Share `config.py` with values | Share only keys/structure |
| Share actual `.env` file | Share `.env.example` with placeholders |
| Share `docker-compose.yml` with credentials | Share template with env var references |
| Share actual ChromaDB data | Explain indexing strategy conceptually |
| Share system prompts | Describe the agent's role without exact wording |
| Share pricing formulas | Explain pricing approach in generic terms |
| Share engineering logic | Describe the calculation methodology |
| Share customer quotations | Use sanitized/synthetic examples |
| Share internal IP addresses | Use placeholder hostnames (e.g., `redis-server`) |
| Share folder structure with business logic hints | Share top-level folders only |

---

## Questions to Ask Before Sharing

1. **What am I trying to communicate?**
   - Architecture? → Share diagrams + conceptual descriptions
   - Tech stack? → Share requirements.txt + high-level overview
   - Code patterns? → Share generic examples, not our implementation
   - Lessons learned? → Share insights, not implementation

2. **Who am I sharing with?**
   - Colleague at another company? → Very restrictive
   - Potential hire/intern? → More restrictive (still in interview process)
   - Open-source contributor? → Only what's in public repo
   - Trusted partner? → Still follow this guide

3. **Could this give away our competitive advantage?**
   - If yes → Don't share
   - If no → Proceed with other checks

4. **Does this contain customer data?**
   - If yes → Don't share (ever)
   - If no → Proceed with other checks

5. **Could this help someone replicate our product?**
   - If yes → Don't share (or only share the open-source parts)
   - If no → Proceed with other checks

---

## What Colleagues Can Learn (Safely)

✅ **From You Verbally / In Presentation**
- Why you chose this tech stack
- How multi-stage retrieval improves quality
- Trade-offs in chunking strategies
- Benefits of hybrid reranking
- Importance of permission filtering
- How you handle graceful degradation
- Lessons from production issues

✅ **From Generic Diagrams**
- System architecture (layers)
- Data flow (stages, not implementation)
- Service dependencies
- Conceptual pipeline

✅ **From This Guide**
- What to share and what not to share
- How to safely share a project
- Thought process for security decisions

---

## For Your Friend

If your friend asks for the project, use this response:

> *"I'd love to share what I've built! Here's what I can give you:*
>
> - *A high-level architecture diagram (without implementation details)*
> - *List of libraries we use (requirements.txt)*
> - *Explanation of our approach (multi-stage retrieval, hybrid reranking, etc.)*
> - *Design patterns and trade-offs we made*
> - *A template docker-compose setup*
> - *This sharing guide, so you know what's safe to share from your own projects*
>
> *What I can't share:*
> - *Our actual implementation code*
> - *Pricing and engineering logic*
> - *System prompts and model configuration*
> - *Customer data and production database*
> - *Credentials and secrets*
>
> *Happy to discuss the architecture and approach over a call, or walk through the public documentation!"*

---

## References

- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) — data protection best practices
- [OWASP Secrets Management](https://owasp.org/www-project-secrets-management/) — handling credentials
- [Open Source Licensing](https://opensource.org/licenses/) — if considering open-sourcing parts
- [Your Company Confidentiality Policy](https://internal-policy-link) — always check internal guidelines

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-07-27 | Initial sharing guide |

---

**Last Updated**: 2026-07-27

**Maintained By**: Your Team

**Questions?** Ask your manager or legal team before sharing anything not explicitly listed as "✅ Safe to Share".
