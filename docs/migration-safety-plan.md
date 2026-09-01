# Migration Safety Plan — nothing is lost

> Goal: move from the RunPod pod to the local production server with **zero data
> loss**, and know it rather than hope it.
>
> Run top to bottom. Every step has a **verification** — do not tick a box until
> its check passes. Nothing is deleted from the pod until §5 proves the new
> server works.

---

## 1. Inventory — what exists and how it is recovered

| Asset | Where it lives | Criticality | How it is recovered |
|---|---|---|---|
| Application code | git | — | `git clone` |
| 33 historical offers | git (`backend/data/offers/`) | — | `git clone` |
| **Agent build scripts** | git (`ops/flowise/`) | **CRITICAL** | `git clone` — rebuilds all 3 agents |
| Compose + runbook | git | — | `git clone` |
| **Live agents (tuned prompts)** | Postgres → `vitech.sql` | **CRITICAL** | restore dump, or rebuild from scripts |
| **Flowise encryption key** | `flowise/secrets/` | **CRITICAL** | backup only — cannot be regenerated |
| Chat history | Postgres → `vitech.sql` | medium | restore dump (else lost, harmless) |
| Deploy SSH key | `ssh/` | low | regenerate + re-add to GitHub |
| Chroma vector store | `chroma/` | low | `python -m rag.ingest data/offers` |
| Ollama models (9 GB) | `ollama/` | none | `ollama pull llama3.1:8b` |
| Flowise tarball (1 GB) | `flowise-app.tar.gz` | none | Docker image on the new server |

**Of 10.2 GB, ~5 MB is irreplaceable.** Everything else is code, or regenerates.

### The three-copy rule
Every critical asset must exist in **three independent places** before the pod is
touched: (1) **GitHub**, (2) the **downloaded tarball on your machine**,
(3) the **new server**. The pod does not count — it is what we are leaving.

---

## 2. Pre-migration — on the pod (do first)

- [ ] **Fresh dump.** Agents live in Postgres; the dump must be newer than the
      last prompt change.
      ```bash
      bash /workspace/persistent/pg-backup.sh
      ls -la /workspace/persistent/postgres-backups/vitech.sql   # check timestamp
      ```
- [ ] **Verify the dump really contains all three agents** — a dump that ran
      against a stopped DB looks fine and is empty.
      ```bash
      for a in "Engineering Agent" "Quotation Agent" "Drawing Agent"; do
        printf "%-20s %s\n" "$a" "$(grep -c "$a" /workspace/persistent/postgres-backups/vitech.sql)"
      done   # every count must be >= 1
      ```
- [ ] **Verify git holds the prompts** — the scripts must match the LIVE agents,
      or a rebuild silently produces older behaviour. This is the check that
      makes copy (1) trustworthy:
      ```bash
      cd /workspace/vitech-ai-vps && bash ops/verify-agents.sh
      ```
- [ ] **Everything pushed.**
      ```bash
      git status --porcelain   # must be empty
      git log origin/$(git rev-parse --abbrev-ref HEAD)..HEAD   # must be empty
      ```
- [ ] **Build the backup bundle.**
      ```bash
      tar -czf /workspace/vitech-ai-vps/vitech-critical-backup-$(date +%Y%m%d-%H%M).tar.gz \
        -C /workspace/persistent postgres-backups/vitech.sql flowise/secrets ssh chroma
      sha256sum /workspace/vitech-ai-vps/vitech-critical-backup-*.tar.gz
      ```
- [ ] **Download it** (VS Code Explorer → right-click → Download) and **verify
      the checksum on your machine matches**. A truncated download is the most
      likely silent failure here.
- [ ] **Store a second copy** of the tarball somewhere that is not your laptop
      (encrypted drive, password manager attachment, private cloud). It holds
      private keys — never a public location, never git.

---

## 3. New server — prepare

- [ ] OS ready, Docker + **nvidia-container-toolkit** installed.
- [ ] **GPU passthrough proven** *before* anything else:
      ```bash
      docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
      ```
- [ ] `git clone` the repo.
- [ ] `cp .env.example .env` and set real passwords (`POSTGRES_*`, `FLOWISE_*`).
      Leave `API_KEY` empty for LAN; set it before the VPN phase.
- [ ] **Validate the compose before starting anything** — it has never been
      executed, only written:
      ```bash
      docker compose -f docker-compose.prod.yml config
      ```

---

## 4. New server — restore

- [ ] Unpack the tarball somewhere private (e.g. `/tmp/vb`).
- [ ] Start the stack:
      ```bash
      docker compose -f docker-compose.prod.yml up -d --build
      docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.1:8b
      ```
- [ ] **Confirm the model advertises tool calling** — the Tool Agent cannot work
      without it, and this fails loudly here rather than mysteriously later:
      ```bash
      docker compose -f docker-compose.prod.yml exec ollama ollama show llama3.1:8b | grep -i tools
      ```
- [ ] **Restore the agents** (the step most likely to be skipped — the app looks
      functional without them):
      ```bash
      cp /tmp/vb/postgres-backups/vitech.sql ops/restore/
      docker compose -f docker-compose.prod.yml exec -T postgres \
        psql -U vitech -d vitech < ops/restore/vitech.sql
      ```
- [ ] **Restore the Flowise encryption key**, then restart Flowise:
      ```bash
      docker compose -f docker-compose.prod.yml cp \
        /tmp/vb/flowise/secrets flowise:/root/.flowise/secrets
      docker compose -f docker-compose.prod.yml restart flowise
      ```
- [ ] Rebuild the vector store:
      ```bash
      docker compose -f docker-compose.prod.yml exec backend python -m rag.ingest data/offers
      docker compose -f docker-compose.prod.yml exec backend curl -s -X POST localhost:8000/api/admin/reload-index
      ```

**If the dump is unusable**, rebuild the agents from git instead — idempotent,
in this order: `agent-build.py` → `agent-add-list-tool.py` →
`agent-harden-prompt.py` → `quotation-agent-build.py` → `drawing-agent-build.py`.
If that mints new chatflow ids, set `VITE_*_AGENT_ID` and rebuild the frontend.

---

## 5. Acceptance — proof before decommissioning

**Do not touch the pod until every line below passes.**

- [ ] All three agents present:
      ```bash
      docker compose -f docker-compose.prod.yml exec postgres \
        psql -U vitech -d vitech -tAc 'SELECT name FROM chat_flow ORDER BY name;'
      ```
- [ ] Prompts match git (same script as §2, run against the new DB):
      `bash ops/verify-agents.sh`
- [ ] All six suites pass:
      ```bash
      for t in golden engineering drawing lookup pricing retrieval; do
        docker compose -f docker-compose.prod.yml exec backend python tests_$t.py | tail -1
      done
      ```
- [ ] **Live agent behaviour**, not just presence — tool calling is what breaks
      after a move:
      - Engineering: `spec for a paint booth 5m x 3m x 4m` → starts
        `**ENGINEERING SPECIFICATION`
      - Quotation: `quote wet scrubber 800 cfm 750mm tower 4 nos` → a price
      - Drawing: `draw a paint booth 5m x 3m x 4m` → drawing on the canvas
      - Lookup: `Length: 0.9 m Width: 0.92 m Height: 2 m` → **Yonex only**
- [ ] Browser check: all three chats, Drawing Studio (form **and** assistant),
      Knowledge Base, PDF export.
- [ ] **First backup taken on the new server** (§6) and copied off it.

---

## 6. Ongoing discipline on the new server

The pod taught this the hard way: **the agents live in Postgres, and Postgres is
the one thing that is not in git.**

- **After ANY agent or prompt change**, dump immediately:
  ```bash
  docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U vitech vitech > backups/vitech-$(date +%F-%H%M).sql
  ```
- **Nightly**, automated (cron), keeping 30 days:
  ```bash
  0 2 * * * cd /opt/vitech-ai-vps && docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U vitech vitech > backups/vitech-$(date +\%F).sql 2>>backups/cron.log
  ```
- **Copy backups off the machine** — a backup on the same disk protects against
  mistakes, not hardware failure.
- **Whenever a prompt is edited on the server**, mirror the change into
  `ops/flowise/*.py` and push, so git stays the source of truth.
- **Never commit** `vitech.sql`, `flowise/secrets/`, SSH keys or the backup
  tarball. `.gitignore` blocks them; `git check-ignore -v <file>` confirms.

---

## 7. Decommissioning the pod — last

Only after §5 is fully green **and** the new server has taken its own backup:

- [ ] Final dump + tarball from the pod, downloaded and checksummed (repeat §2).
- [ ] Keep that final tarball for **at least 30 days** after cutover.
- [ ] Stop the pod (reversible) and run for a week before terminating the volume
      (irreversible).
- [ ] Delete the tarball from the server filesystem once stored safely:
      `rm /workspace/vitech-ai-vps/vitech-critical-backup-*.tar.gz`

---

## 8. Rollback

If the new server fails acceptance, nothing has been lost — the pod is untouched
until §7. Restart it (`bash /workspace/persistent/start-all.sh`, or
`bootstrap-pod.sh` first if the container disk was wiped) and continue there
while the problem is diagnosed. **This is why §7 comes last.**

## 9. Known gaps carried into production

* **Authentication is frontend-only** — `AuthProvider.jsx` validates in the
  browser against a hard-coded list, with no auth backend. Acceptable on a
  trusted LAN, **must be fixed before the VPN phase** (queue item E1), along
  with `API_KEY` and HTTPS.
* `retrieve_knowledge` returns `count:0` until documents land in
  `backend/data/bulk/`.
* Two of the ten client spec-review defects remain open — `docs/spec-quality-plan.md`.
