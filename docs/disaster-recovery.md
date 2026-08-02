# Disaster recovery — "the VPS is gone"

Answers one question: **if the pod and its network volume vanished right now,
what is lost?**

Short answer, audited on 2026-08-02: **nothing is lost, even if the downloaded
tarball is also gone.** GitHub alone rebuilds the whole platform, including the
three tuned agent prompts. The tarball only makes recovery *fast*.

`docs/migration-safety-plan.md` covers a *planned* move to a new server. This
document covers *unplanned* total loss.

---

## 1. What is where

Everything on the volume falls into exactly one of four buckets. There is no
fifth bucket, and nothing sits outside them — that is the point of the audit.

| On the volume | Size | Bucket | Recovered by |
|---|---|---|---|
| `vitech-ai-vps/` (code, docs, 33 offers, goldens, ops scripts) | 2.9 G | **In git** | `git clone` |
| `persistent/*.py`, `*.sh` (agent build + bootstrap scripts) | ~60 K | **In git** (`ops/flowise/`) | `git clone` |
| `postgres-backups/vitech.sql` (the live tuned agents) | 4.7 M | **In the tarball** | download, or rebuild from git |
| `flowise/secrets/` (encryption key) | 2.6 M | **In the tarball** | regenerate + re-enter credentials |
| `ssh/` (deploy key) | 51 K | **In the tarball** | regenerate, re-add the pubkey to GitHub |
| `chroma/` (vector store) | 6.3 M | **In the tarball** | re-ingest from the 33 offers |
| `ollama/` (model weights) | 9.2 G | **Regenerable** | `ollama pull llama3.1:8b` |
| `flowise-app.tar.gz` (patched Flowise tree) | 1.0 G | **Regenerable** | `flowise-reinstall.sh --from-npm` |
| `logs/` | 1.5 M | **Disposable** | — |
| `flowise-package.json` | 512 B | **Redundant** | the authoritative pins are written inline by `flowise-reinstall.sh`, which is in git |

Of ~11 GB on the volume, roughly **5 MB is irreplaceable-in-principle** — and
even that is reproducible from git (§3).

## 2. Why the agents survive without the SQL dump

The three agent prompts are the only thing that lives *solely* in PostgreSQL,
and PostgreSQL sits on the container disk, which is wiped routinely. That would
be the single point of failure — except that `ops/flowise/*.py` carries the
build script for every agent, and **`ops/verify-agents.sh` proves the scripts
still reproduce the live prompts**:

```
$ bash ops/verify-agents.sh
  AGENT                   LIVE     GIT   MATCH
  Engineering Agent       9894    9894   yes
  Quotation Agent         5370    5370   yes
  Drawing Agent           3102    3102   yes
RESULT: all three agents reproducible from git
```

It pulls each live prompt out of Postgres and diffs it against the git script,
exiting non-zero on mismatch. Run it after every prompt-tuning session: a green
result is what makes GitHub a *trustworthy* backup rather than a hopeful one.

## 3. Recovery from total loss — git only

Worst case: pod gone, volume gone, tarball not downloaded. All you have is the
GitHub repository.

1. **New machine, clone the repo.**
   ```
   git clone git@github.com:<owner>/vitech-ai-vps.git /workspace/vitech-ai-vps
   ```
2. **Restore the ops scripts to where the runbooks expect them.**
   ```
   mkdir -p /workspace/persistent
   cp /workspace/vitech-ai-vps/ops/flowise/* /workspace/persistent/
   ```
3. **Bootstrap the stack** — installs PostgreSQL, Redis, Node 20, Ollama and
   Flowise, and pulls the model.
   ```
   bash /workspace/persistent/bootstrap-pod.sh
   ```
   With no `vitech.sql` present it will create an empty database instead of
   restoring one. That is expected here.
4. **Rebuild the three agents from their scripts, in this order.**
   ```
   python3 /workspace/persistent/agent-build.py
   python3 /workspace/persistent/agent-add-list-tool.py
   python3 /workspace/persistent/agent-harden-prompt.py
   python3 /workspace/persistent/quotation-agent-build.py
   python3 /workspace/persistent/drawing-agent-build.py
   ```
   Each is idempotent and updates in place. The Quotation and Drawing agents
   clone the live Engineering flow, so the Engineering Agent must exist first.
5. **Re-ingest the vector store** from the 33 offers already in the repo.
   ```
   cd /workspace/vitech-ai-vps/backend
   .venv/bin/python -m rag.ingest data/offers
   curl -X POST localhost:8000/api/admin/reload-index
   ```
6. **Start everything and verify.**
   ```
   bash /workspace/persistent/start-all.sh
   bash /workspace/vitech-ai-vps/ops/verify-agents.sh
   cd backend && for t in tests_*.py; do .venv/bin/python $t; done
   ```

**What you must re-enter by hand:** the `.env` credentials, and a new SSH deploy
key added to GitHub. Nothing else.

**What changes:** rebuilding mints **new chatflow IDs**. Set
`VITE_ENGINEERING_AGENT_ID`, `VITE_QUOTATION_AGENT_ID` and
`VITE_DRAWING_AGENT_ID` in the frontend environment, or the UI will call flows
that no longer exist.

Expect a few hours, most of it waiting on the model download.

## 4. Recovery with the tarball — the fast path

If `vitech-critical-backup-<date>.tar.gz` was downloaded, steps 4 and 5 above
collapse into a restore:

```
tar -xzf vitech-critical-backup-<date>.tar.gz -C /workspace/persistent
bash /workspace/persistent/bootstrap-pod.sh    # restores vitech.sql automatically
```

This keeps the **existing chatflow IDs**, the Flowise encryption key (so stored
credentials still decrypt) and the already-built vector store. Minutes, not
hours — and no frontend environment change.

## 5. Keeping this true

- **Run `pg-backup.sh` after ANY agent change** and before stopping the pod.
- **Run `verify-agents.sh` after any prompt tuning.** If it reports a mismatch,
  the live prompt has drifted from git and a rebuild would silently produce
  older behaviour — mirror the change into `ops/flowise/*.py` immediately.
- **Re-download the tarball whenever the dump changes.** It is ~1.6 MB; there is
  no reason to have a stale one.
- **The three-copy rule:** GitHub + a downloaded tarball + the running server.
  The pod does not count as a copy of itself.

## 6. Audit trail

The table in §1 was produced by enumerating `/workspace/persistent`, diffing each
ops script against its counterpart in `ops/flowise/`, and confirming every
remaining entry is either in the tarball or regenerable. On 2026-08-02 all
thirteen scripts were byte-identical to git, all 33 offer records were readable
from the tracked JSON, and `verify-agents.sh` was green. Re-run that audit if
anything new is ever written to the volume.
