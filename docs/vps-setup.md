# VPS Setup Runbook — Vitech AI Engineering Platform

Copy-paste steps for tomorrow, once the RunPod GPU VPS is bought. Everything
below runs **on the VPS** (via SSH or VS Code Remote-SSH). Nothing is stored
locally.

## 0. Before you start
- A RunPod **GPU** pod, Ubuntu 22.04, with an SSH endpoint.
- This repo pushed to a git remote (GitHub/GitLab). See `docs/git-move.md` if
  we prepared that; otherwise `scp`/`rsync` the folder up once.

## 1. Connect
```bash
ssh root@<POD_IP> -p <PORT>        # or: VS Code -> Remote-SSH -> Connect to Host
```
In VS Code, when connected, install the **Claude Code** extension *on the remote
host* when prompted — then Claude Code edits + runs commands on the VPS.

## 2. Install Docker + Compose
```bash
curl -fsSL https://get.docker.com | sh
docker version && docker compose version
```
(NVIDIA GPU for Ollama: install `nvidia-container-toolkit`, then uncomment the
`deploy:` GPU block in `docker-compose.yml`.)

## 3. Get the code
```bash
mkdir -p /home/vitech && cd /home/vitech
git clone <YOUR_REPO_URL> .
```

## 4. Secrets
```bash
cp .env.example .env
nano .env          # set strong POSTGRES_PASSWORD + FLOWISE_PASSWORD
```

## 5. Bring the stack up
```bash
docker compose up -d --build
docker compose ps          # ollama, chroma, redis, postgres, flowise, backend
```

## 6. Pull the models (Ollama)
```bash
docker exec -it $(docker compose ps -q ollama) ollama pull llama3
docker exec -it $(docker compose ps -q ollama) ollama pull nomic-embed-text   # embeddings for Flowise
```

## 7. Load the data (Postgres + Chroma)
```bash
# Postgres tables (from the export we generated locally):
docker exec -i $(docker compose ps -q postgres) psql -U vitech -d vitech \
  < backend/data/export/schema.sql
docker exec -i $(docker compose ps -q postgres) psql -U vitech -d vitech \
  < backend/data/export/data.sql

# Chroma vectors (backend ingests the offers on first run, or trigger it):
docker exec -it $(docker compose ps -q backend) python -m app.ingest
```

## 8. Smoke-test the backend tool endpoints
```bash
curl -s localhost:8080/api/health
curl -s -X POST localhost:8080/api/tools/quote \
  -H 'Content-Type: application/json' \
  -d '{"question":"wet scrubber 800 cfm 750mm tower 4 nos"}'
```

## 9. Build the Engineering Agent in Flowise
Open `http://<POD_IP>:3000` (login with FLOWISE_USERNAME/PASSWORD), then:
1. **Chatflow -> Add New**.
2. **ChatOllama**: Base URL `http://ollama:11434`, model `llama3`, temp `0.2`.
3. **Postgres Chat Memory**: host `postgres`, db/user/pass from `.env`.
4. **Tool Agent** node: wire in ChatOllama + Memory + the Custom Tools below.
5. **Custom Tools** — one per capability, each `fetch`ing the backend (inside
   the compose network the backend is `http://backend:8000`):
   - `retrieve_knowledge`      -> `POST /api/tools/retrieve` — search the KB with metadata filter
   - `generate_specification`  -> `POST /api/tools/spec`     — deterministic engineered spec
   - `generate_quotation`      -> `POST /api/tools/quote`    — deterministic budgetary price
   - `lookup_project`          -> `POST /api/tools/lookup`   — a named client / offer's data
6. Paste the Engineering Agent **system prompt** (below).

> **Do NOT use a Flowise "Ollama Embeddings + Chroma retriever" node for search.**
> The collection was embedded with **all-MiniLM-L6-v2**; a Flowise Chroma node
> using `nomic-embed-text` reads it with the wrong model and retrieval silently
> breaks (the #1 gotcha). The `retrieve_knowledge` tool goes through the backend,
> which uses the *same* embedding model AND adds metadata filtering — so the
> agent searches Chroma correctly and can pre-filter by equipment type, customer,
> project, section, revision.

### `retrieve_knowledge` Custom Tool
Input variables: `question` (string), `equipment_type` (string, optional),
`section` (string, optional). Function body:
```js
const res = await fetch("http://backend:8000/api/tools/retrieve", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question: $question,
    filters: {
      ...($equipment_type ? { equipment_type: $equipment_type } : {}),
      ...($section ? { section: $section } : {}),
    },
  }),
});
return JSON.stringify(await res.json());
```
(The other three tools follow the same shape, POSTing `{ question }` to their
endpoint.) Discover valid filter values any time with `GET /api/tools/filters`.

### Engineering Agent system prompt (paste verbatim)
```
You are a senior process/mechanical engineer at Vitech Enviro Systems. You turn
a customer requirement into a technical specification. Follow this workflow every
time:

1. Read the customer's requirement and identify the equipment type.
2. Call retrieve_knowledge to pull similar historical projects and any relevant
   standards. Filter by equipment_type (and section="technical_specification"
   when you want past specs).
3. Call generate_specification with the requirement. Its returned numbers are
   AUTHORITATIVE and DETERMINISTIC.
4. Write the specification, combining the retrieved engineering knowledge (for
   context, materials, standards, approach) with the tool's calculated values.

Hard rules:
- NEVER invent or alter a dimension, capacity, count, price, or material. Every
  number MUST come from generate_specification (or generate_quotation). If a
  value is not in a tool result, it is "To Be Determined".
- If generate_specification reports missing_inputs, ASK the customer for exactly
  those inputs. Do not guess them.
- Present the output as an engineer-reviewed DRAFT for human approval.
- Cite source files from the tool results where relevant.
```

## 10. Wire the frontend
Flowise exposes `POST /api/v1/prediction/<chatflowId>`. Your FastAPI calls that
(Flowise stays internal); React talks only to FastAPI.

---
### Gotchas
- Services talk by **service name**, not `localhost`.
- **Embedding-model match** is the #1 retrieval bug — same model to write and read Chroma.
- Keep **all business logic in the backend** tools; Flowise only orchestrates.
