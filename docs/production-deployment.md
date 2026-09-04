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

# REQUIRED. The origin the browser loads the app from — e.g. http://vitech.local
# or https://vitech.example.com. The backend defaults to the localhost dev
# origins, which a deployed frontend is NOT served from, so leaving this unset
# means the app's own requests are refused by CORS.
CORS_ORIGINS=http://<the frontend origin>

# Optional runaway guards; the defaults are fine for a normal office.
RATE_LIMIT_PER_MINUTE=120
MAX_CONCURRENT_EXPENSIVE=12
MAX_UPLOAD_MB=50
```

The compose file uses `${VAR:?}` for the credentials and for `CORS_ORIGINS`, so
it refuses to start rather than silently falling back to a default password or
a CORS policy that breaks the app.

> **`API_KEY` is gone and must not be re-added.** The old coarse
> `VITECH_API_KEY` middleware was all-or-nothing and, because the variable was
> never set, never engaged at all. It was replaced by real per-principal
> authentication (`app/auth/`). Setting `API_KEY` today does nothing while
> reading as though the API were protected by it — which is worse than not
> having it.

## 3a. Create the first account — WITHOUT THIS NOBODY CAN LOG IN

There is no default account and no seeded password. An empty user table locks
everyone out, which is the correct failure for a platform holding customer
engineering data — but it means **a fresh deployment has no way in until you
run this**:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.auth.bootstrap admin <username>
```

The generated password prints **once**. `... bootstrap list` shows the
accounts that exist; `... bootstrap password <username>` rotates one.

Accounts live in `backend/data/auth.db`, inside the `./backend/data` bind
mount — so they survive a container rebuild, and they are covered by
`ops/backup.sh`. They are **not** in Postgres and not in git.

## 3b. Point the agents at a service key that exists here

**Do this after restoring Postgres (§4), and do not skip it.** The Flowise tool
rows carry the API key the three agents authenticate to the backend with. That
key is only a valid credential if a matching service principal exists in *this
deployment's* `auth.db` — and a fresh `auth.db` has none, even though the tool
rows restored from the dump look perfectly correct.

```bash
# Create the service principal, then write its key into all nine tool rows
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.auth.bootstrap service flowise-agents
bash ops/flowise/set-service-key.sh          # --check to verify only
```

**The failure signature if you skip it is misleading**: the agent replies "I
don't have the ability to call external tools", which is character-for-character
what it says when the backend is *down*. `ops/rotate-service-key.md` is the
runbook.

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

**Updated 2026-09-04.** The first two items on this list are DONE and the text
that described them as outstanding was wrong for a month — do not plan around
the old version.

1. ~~Real authentication~~ **DONE.** Server-side authentication, roles and an
   audit trail landed 2026-08-05 (`app/auth/`). Accounts are in SQLite with
   scrypt hashes, sessions are stored server-side so logout revokes
   immediately, `X-Role` is no longer trusted, and the frontend password is
   gone from the JS bundle (verified by grepping the built asset). Every route
   except `/api/health` requires a credential, and an unclassified route
   defaults to administrator.
2. ~~Set `API_KEY`~~ **Superseded** — see the note in §3. That variable no
   longer exists.
3. **HTTPS + a reverse proxy** (Caddy or nginx) in front of the frontend
   container, with a stable internal hostname rather than an IP. **Still
   outstanding, and now the top item on this list.** Sessions are bearer
   tokens: over plain HTTP they are readable by anything on the path.
   Terminate TLS at the proxy and add HSTS, X-Frame-Options and a CSP.
4. **Flowise admin.** `FLOWISE_USERNAME/PASSWORD` guards the Flowise UI on
   :3000 — keep it unpublished (it already is) and reach it via SSH tunnel.
5. **Backups off the machine** — see §7. **Read that section again even if you
   read it before**: what has to be backed up changed.
6. **Rate limits.** Already on by default (§3). Review
   `RATE_LIMIT_PER_MINUTE` against the real user count before opening access
   to remote staff.

## 7. Backups

**Rewritten 2026-09-04. The old version of this section backed up two things
and there are five.** Postgres and the Flowise key were the whole irreplaceable
set when they were written; three stores the platform declares PERMANENT have
been added since and were in no backup at all:

| What | Where | Why it cannot be regenerated |
|---|---|---|
| The three agents | Postgres | Tuned prompts; the one asset not reproducible from git |
| `auth.db` | `backend/data/` | Accounts, password hashes, and the **permanent audit trail** |
| `ops.db` | `backend/data/` | A row per specification, drawing, BOM, quotation and package **ever issued** |
| `data/jobs/` | `backend/data/` | The issued documents themselves, each with the SHA-256 it went out under |
| Flowise secrets | flowise volume | The key stored credentials are encrypted with — including the agents' service key |

Use the script; it takes all five:

```bash
bash ops/backup.sh                 # -> /workspace/persistent/backups/…tar.gz
DEST=/mnt/nas bash ops/backup.sh   # somewhere off the machine
```

It copies both SQLite stores through SQLite's **online backup API** rather than
`cp` — the backend holds them open, and copying a live database can capture a
torn write that only reveals itself on the day you restore. It then reads the
copy back, integrity-checks it, and verifies every artifact against its
recorded digest.

**Restore, and rehearse it:**

```bash
bash ops/restore.sh <tarball> --dry-run   # verify the archive, change nothing
bash ops/restore.sh <tarball>
```

An unrehearsed restore is an untested code path holding your audit trail. Note
`ops/restore.sh` puts `auth.db` back **before** Postgres, for the reason in
§3b: the restored tool rows carry a service key that is only a credential if a
matching principal exists in `auth.db`.

Copy the archive **off the server** — one on the same disk as the original does
not survive the failure it exists for. Regenerable and deliberately not
included: Ollama models (re-pull), the Chroma store (re-ingest from the
offers), Docker images, `node_modules`, `.venv`.

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

**Corrected 2026-09-04** — two entries here were simply out of date and would
have sent someone re-solving problems that are solved.

* ~~Auth is frontend-only~~ **DONE 2026-08-05.** See §6.1.
* ~~`retrieve_knowledge` returns `count:0`~~ **DONE 2026-09-01.** Vitech's
  knowledge documents are ingested (178 chunks from 15 files) and retrieval
  returns cited results. `backend/data/knowledge_docs/` holds them; re-ingest
  on a new machine with `python -m rag.ingest data/knowledge_docs`.
* **HTTPS is still not done** and is now the top item before any non-LAN
  exposure (§6.3).
* `docker-compose.prod.yml` is **written but STILL not executed** — there is no
  Docker on the RunPod pod to validate it against, so this remains the single
  biggest unknown in the production move. Run
  `docker compose -f docker-compose.prod.yml config` on the target server
  first, and expect to adjust the Flowise image tag if `3.0.13` is not
  published for your architecture (the pod runs a patched npm install, not this
  image; the patches covered the OpenAPIToolkit UI, which this platform does
  not use, so the stock image is expected to work — **verify tool calling end
  to end**).
* **The frontend bakes the three chatflow IDs in at BUILD time.** They are
  compiled into the JS bundle, so if a rebuild of the agents mints new ids the
  frontend must be rebuilt with `VITE_ENGINEERING_AGENT_ID`,
  `VITE_QUOTATION_AGENT_ID` and `VITE_DRAWING_AGENT_ID` set — restarting it is
  not enough.
* **Component setting-out rules are still outstanding from Vitech.** Until they
  arrive every GA states that component positions are indicative. This is a
  product limitation, not a deployment one, but it is what stands between the
  drawings and fabrication-grade output.
* Engineering items still open are tracked in `docs/agent-completion-plan.md`
  (booth BOM cost model, structure weight, the margin model) and in CLAUDE.md.
