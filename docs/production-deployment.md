# Local Production Deployment

> Moving the platform off the RunPod pod onto a local server.
> **Phase 1 = office LAN** (the plan now). **Phase 2 = LAN + remote staff over
> VPN**, which has prerequisites that must be done first — see §6.
>
> Compose file: `docker-compose.prod.yml`. It is deliberately separate from the
> dev `docker-compose.yml`, which is stale and carries landmines (§1).

## 0. Server requirements

| | Requirement | Why |
|---|---|---|
| GPU | NVIDIA, **8 GB+ VRAM** | `llama3.1:8b` at usable speed. Confirmed available. |
| Driver | NVIDIA driver + **nvidia-container-toolkit** | Docker cannot pass the GPU through without it. |
| RAM | 32 GB recommended | Ollama + Postgres + Flowise + backend together. |
| Disk | 100 GB+ SSD | Ollama models ~9 GB, Postgres, Chroma, Docker images. |
| OS | Ubuntu 22.04 / 24.04 LTS | Matches what the stack is proven on. |

Keeping an 8 GB+ GPU matters beyond speed: **every agent prompt is tuned against
`llama3.1:8b` specifically**, through repeated live testing (see the prompt
history in CLAUDE.md). Changing the model invalidates that tuning and requires
re-verifying each agent 3–5× per case.

Verify GPU passthrough before anything else:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

## 1. Why NOT to use the old `docker-compose.yml`

It dates from 2026-07-16, before most of the platform existed, and would fail:

| Problem | Consequence |
|---|---|
| `flowiseai/flowise:latest` | Pulls 3.1.x, which pins `@langchain/core@1.1.20` — its missing `./utils/uuid` subpath makes node throw at startup. **`docker-compose.prod.yml` pins 3.0.13.** |
| Separate `chroma` service | The backend uses **embedded** ChromaDB via `CHROMA_DIR`; the container is unused and steals host port 8000. Removed. |
| Ollama GPU block commented out | Model runs on CPU — 10–30× slower. Now enabled. |
| No `HTTP_SECURITY_CHECK` | Flowise's SSRF deny-list blocks the Custom Tools from reaching the backend: *"Access to this host is denied by policy"*. Now set, with cloud-metadata still blocked. |
| Live code bind-mount | Fine for dev, wrong for production. Removed; the image is built. |
| Every service published | Postgres, Redis, Flowise and the backend were all exposed. Now only the frontend publishes a port. |

## 2. First deployment

```bash
git clone <repo> vitech-ai-vps && cd vitech-ai-vps

cp .env.example .env    # then edit — see §3
docker compose -f docker-compose.prod.yml config      # validate BEFORE up
docker compose -f docker-compose.prod.yml up -d --build

# Pull the model into the ollama volume (once, ~5 GB)
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.1:8b

# Confirm the model advertises tool calling — the Tool Agent REQUIRES it
docker compose -f docker-compose.prod.yml exec ollama \
  ollama show llama3.1:8b | grep -i tools
```

Then **restore the agents** (§4) and **ingest the offers** (§5).

## 3. `.env` for production

```ini
POSTGRES_USER=vitech
POSTGRES_PASSWORD=<strong unique password>
POSTGRES_DB=vitech

FLOWISE_USERNAME=admin
FLOWISE_PASSWORD=<strong unique password>

OLLAMA_MODEL=llama3.1:8b
HTTP_PORT=80

# Leave EMPTY on a trusted LAN. SET IT before the VPN rollout (§6).
API_KEY=
```

The compose file uses `${VAR:?}` for the credentials, so it refuses to start
rather than silently falling back to a default password.

## 4. Restoring the agents — do not skip

**The three Flowise agents live in Postgres.** A fresh `pgdata` volume has none,
and the app will look broken in a way that is not obvious.

```bash
# Put the dump where the postgres container can see it
cp /path/to/vitech.sql ops/restore/

docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U vitech -d vitech < ops/restore/vitech.sql

docker compose -f docker-compose.prod.yml restart flowise
```

Verify all three exist:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U vitech -d vitech -tAc 'SELECT name FROM chat_flow ORDER BY name;'
# Drawing Agent / Engineering Agent / Quotation Agent
```

**If you have no dump**, rebuild from scratch — the scripts in `ops/flowise/`
are the source of truth (see its README for the order). They are idempotent.

Afterwards, the frontend needs the chatflow IDs. If a rebuild produced new ones,
set them in the frontend build environment:
`VITE_ENGINEERING_AGENT_ID`, `VITE_QUOTATION_AGENT_ID`, `VITE_DRAWING_AGENT_ID`.

## 5. Ingest + verification

```bash
# Vector store (the 33 offers). Chroma is embedded, so this runs in the backend.
docker compose -f docker-compose.prod.yml exec backend \
  python -m rag.ingest data/offers
docker compose -f docker-compose.prod.yml exec backend \
  curl -s -X POST localhost:8000/api/admin/reload-index

# The six suites are the acceptance gate — all must pass
for t in golden engineering drawing lookup pricing retrieval; do
  docker compose -f docker-compose.prod.yml exec backend python tests_$t.py | tail -1
done
```

Then click through: Engineering chat, Quotation chat, Drawing Studio (generate
from the form **and** from the assistant), Knowledge Base.

## 6. Phase 2 — before exposing over VPN

Do these first. On a trusted LAN they are tolerable; over a VPN they are not.

1. **Real authentication (queue item E1).** The login in
   `frontend/src/auth/AuthProvider.jsx` validates credentials **in the browser
   against a hard-coded list** — there is no auth backend. Anyone who can reach
   the page can read the JS and sign in. This is the single most important item.
2. **Set `API_KEY`** so `/api/*` is not open to anything that reaches the host.
3. **HTTPS + a reverse proxy** (Caddy or nginx) in front of the frontend
   container, with a stable internal hostname rather than an IP.
4. **Flowise admin.** `FLOWISE_USERNAME/PASSWORD` guards the Flowise UI on
   :3000 — keep it unpublished (it already is) and reach it via SSH tunnel.
5. **Backups off the machine** — see §7.

## 7. Backups

The irreplaceable set is small (~5 MB); everything else regenerates.

```bash
# Postgres — the agents. Run after ANY agent or prompt change.
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U vitech vitech > backups/vitech-$(date +%F).sql

# Flowise encryption key — credentials are tied to it, losing it invalidates them
docker compose -f docker-compose.prod.yml cp \
  flowise:/root/.flowise/secrets ./backups/flowise-secrets-$(date +%F)
```

Copy both **off the server**. Regenerable and not worth backing up: Ollama
models (re-pull), the Chroma store (re-ingest from the offers), Docker images.

## 8. Operations

```bash
docker compose -f docker-compose.prod.yml ps          # health of each service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml up -d --build   # deploy an update
docker compose -f docker-compose.prod.yml down            # stop (volumes kept)
```

**Updating:** `git pull` then rebuild. Application code is in the image, so a
rebuild is the deploy. Agent prompts are **not** in the image — they live in
Postgres, so changing one means running the relevant `ops/flowise/*.py` script
against the production database and dumping again.

## 9. Known gaps carried over from the pod

* **Auth is frontend-only** (§6.1) — the blocker for anything beyond the LAN.
* `retrieve_knowledge` returns `count:0` until documents are ingested into
  `backend/data/bulk/`; only the 33 offers exist today.
* Two of the ten client spec-review defects remain open — see
  `docs/spec-quality-plan.md`.
* `docker-compose.prod.yml` is **written but not yet executed** — there is no
  Docker on the RunPod pod to validate it against. Run
  `docker compose -f docker-compose.prod.yml config` on the target server first,
  and expect to adjust the Flowise image tag if `3.0.13` is not published for
  your architecture (the pod runs a patched npm install, not this image; the
  patches covered the OpenAPIToolkit UI, which this platform does not use, so
  the stock image is expected to work — **verify tool calling end to end**).
