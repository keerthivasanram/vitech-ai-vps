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
3. **Ollama Embeddings** (`nomic-embed-text`) -> **Chroma** node: URL
   `http://chroma:8000`, your collection. *(Retrieval only if the collection was
   embedded with the SAME model — otherwise re-ingest through Flowise.)*
4. **Postgres Chat Memory**: host `postgres`, db/user/pass from `.env`.
5. **Tool Agent** node: wire in ChatOllama + Chroma + Memory + Custom Tools.
6. **Custom Tools** — one per capability, each `fetch`ing the backend:
   - `generate_specification` -> `POST http://backend:8000/api/tools/spec`
   - `generate_quotation`     -> `POST http://backend:8000/api/tools/quote`
   - `lookup_project`         -> `POST http://backend:8000/api/tools/lookup`
   (inside the compose network the backend is `http://backend:8000`.)
7. Paste the Engineering Agent **system prompt** (senior engineer; never invent
   numbers — always call the tool).

## 10. Wire the frontend
Flowise exposes `POST /api/v1/prediction/<chatflowId>`. Your FastAPI calls that
(Flowise stays internal); React talks only to FastAPI.

---
### Gotchas
- Services talk by **service name**, not `localhost`.
- **Embedding-model match** is the #1 retrieval bug — same model to write and read Chroma.
- Keep **all business logic in the backend** tools; Flowise only orchestrates.
