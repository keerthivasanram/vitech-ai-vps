# Flowise agent + pod operations scripts

These are the **source of truth for all three Flowise agents**. They previously
lived only on the pod's `/workspace/persistent/` volume, which survives a pod
*stop* but not a volume *terminate* — so they are mirrored here, in git.

| Script | Purpose |
|---|---|
| `agent-build.py` | Build the Engineering Agent from scratch |
| `agent-harden-prompt.py` | **Engineering Agent system prompt** (the live source) |
| `agent-add-list-tool.py` | Add the `list_projects` tool (additive, idempotent) |
| `quotation-agent-build.py` | Build the Quotation Agent + **its prompt** |
| `drawing-agent-build.py` | Build the Drawing Agent + **its prompt** |
| `bootstrap-pod.sh` | Rebuild a wiped container disk (PG, Redis, Node, Ollama, Flowise) |
| `start-all.sh` / `stop-all.sh` | Bring the stack up / down |
| `flowise-*.sh` | Flowise install, snapshot and start |
| `pg-backup.sh` | Dump Postgres to the volume — run after ANY agent change |

They contain **no secrets**: credentials are read from `/workspace/vitech-ai-vps/.env`
at runtime.

## Restoring after a total volume loss

1. Recreate the pod, clone this repo, write `.env`.
2. `bash ops/flowise/bootstrap-pod.sh` (installs the stack).
3. If `postgres-backups/vitech.sql` is available, restore it — that is the
   fastest path and carries the tuned prompts.
4. Otherwise rebuild the agents from scratch:
   `agent-build.py` → `agent-add-list-tool.py` → `agent-harden-prompt.py`,
   then `quotation-agent-build.py`, then `drawing-agent-build.py`.
   Each is idempotent and updates in place rather than duplicating.

**Not in git, and must be backed up separately** (see the critical-backup
tarball described in CLAUDE.md): `postgres-backups/vitech.sql`,
`flowise/secrets/` (the encryption key Flowise credentials are tied to), and
`ssh/` (the deploy key — regenerable, just re-add the pubkey to GitHub).
