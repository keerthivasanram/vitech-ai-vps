#!/bin/bash
# =============================================================================
# Vitech AI platform — restore from an `ops/backup.sh` archive.
#
#   bash ops/restore.sh /path/to/vitech-backup-<stamp>.tar.gz
#   bash ops/restore.sh <tarball> --dry-run     # inspect, change nothing
#
# ORDER MATTERS, and the reason is worth knowing before you run it:
# the Flowise tool rows in the Postgres dump carry the backend SERVICE KEY the
# three agents authenticate with. That key is only a valid credential if a
# matching service principal exists in `auth.db`. Restore Postgres without
# auth.db and every agent fails with the documented signature — "I don't have
# the ability to call external tools" — which looks exactly like the backend
# being down. So auth.db goes back FIRST.
#
# SAFETY: this refuses to overwrite a live database unless you pass --force,
# and it always moves the existing file aside rather than deleting it.
# =============================================================================
set -u
REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
DATA=$REPO/backend/data
ARCHIVE=${1:-}
shift || true
DRY=0; FORCE=0
for a in "$@"; do
  [ "$a" = "--dry-run" ] && DRY=1
  [ "$a" = "--force" ] && FORCE=1
done

PY=$(command -v python3 || echo "$REPO/backend/.venv/bin/python3")
step() { echo; echo "== $* =="; }

[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || {
  echo "usage: bash ops/restore.sh <backup.tar.gz> [--dry-run] [--force]"; exit 1; }

STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
tar xzf "$ARCHIVE" -C "$STAGE"

step "Archive contents"
[ -f "$STAGE/MANIFEST.txt" ] && sed 's/^/  /' "$STAGE/MANIFEST.txt" || echo "  (no manifest — old archive?)"

# Verify the SQLite copies BEFORE trusting them with anything.
step "Verifying the archive before restoring from it"
"$PY" - "$STAGE/sqlite" <<'PYEOF'
import os, sqlite3, sys
d = sys.argv[1]
if not os.path.isdir(d):
    print("  no sqlite/ in this archive"); raise SystemExit
for name in sorted(os.listdir(d)):
    p = os.path.join(d, name)
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        counts = []
        for tbl in ("vitech_user", "vitech_audit", "vitech_job", "vitech_artifact"):
            try:
                counts.append(f"{tbl}={c.execute(f'SELECT count(*) FROM {tbl}').fetchone()[0]}")
            except sqlite3.Error:
                pass
        c.close()
        print(f"  {name}: integrity_check={ok} | {' '.join(counts)}")
        if ok != "ok":
            print(f"  REFUSING: {name} is corrupt in the archive itself"); sys.exit(1)
    except sqlite3.Error as e:
        print(f"  {name}: UNREADABLE ({e})"); sys.exit(1)
PYEOF
[ $? -eq 0 ] || { echo "Archive failed verification — nothing restored."; exit 1; }

if [ "$DRY" = 1 ]; then
  echo; echo "--dry-run: verified only, nothing written."; exit 0
fi

# ---------- 1. auth.db FIRST (see the header note) --------------------------
step "auth.db — accounts, audit trail"
mkdir -p "$DATA"
for db in auth.db ops.db; do
  src=$STAGE/sqlite/$db
  [ -f "$src" ] || { echo "  $db not in archive — skipped"; continue; }
  dst=$DATA/$db
  if [ -f "$dst" ] && [ "$FORCE" != 1 ]; then
    echo "  $db EXISTS at $dst — refusing without --force (nothing was changed)"
    continue
  fi
  [ -f "$dst" ] && mv "$dst" "$dst.replaced-$(date +%Y%m%d-%H%M%S)" && echo "  existing $db moved aside"
  cp "$src" "$dst"
  echo "  restored $db"
done

# ---------- 2. The issued artifacts -----------------------------------------
step "Issued artifacts"
if [ -d "$STAGE/jobs" ]; then
  mkdir -p "$DATA/jobs"
  cp -an "$STAGE/jobs/." "$DATA/jobs/" 2>/dev/null
  echo "  restored into $DATA/jobs ($(ls "$DATA/jobs" | wc -l) job folders)"
  echo "  note: existing files were KEPT — an artifact is immutable, so a"
  echo "        collision means the same document, not a newer one."
else
  echo "  none in archive"
fi

# ---------- 3. Postgres — the agents ----------------------------------------
step "PostgreSQL (the agents)"
DUMP=$(ls "$STAGE"/postgres/*.sql 2>/dev/null | head -1)
if [ -z "$DUMP" ]; then
  echo "  no dump in archive — skipped"
elif ! command -v psql >/dev/null; then
  echo "  psql not installed — restore it manually from $DUMP"
else
  [ -f "$REPO/.env" ] && { set -a; . "$REPO/.env"; set +a; }
  DSN="postgresql://${POSTGRES_USER:-vitech}:${POSTGRES_PASSWORD:-}@localhost:5432/${POSTGRES_DB:-vitech}"
  EXISTING=$(psql "$DSN" -tAc "SELECT count(*) FROM chat_flow" 2>/dev/null || echo 0)
  if [ "${EXISTING:-0}" -gt 0 ] && [ "$FORCE" != 1 ]; then
    echo "  database already has $EXISTING chatflow(s) — refusing without --force"
  else
    psql "$DSN" -q -f "$DUMP" >/dev/null 2>&1
    n=$(psql "$DSN" -tAc "SELECT count(*) FROM chat_flow" 2>/dev/null || echo 0)
    echo "  restored: $n chatflow(s)"
  fi
fi

# ---------- 4. Flowise secrets ----------------------------------------------
step "Flowise encryption key"
FSEC=${FLOWISE_SECRETS:-/workspace/persistent/flowise/secrets}
if [ -d "$STAGE/flowise-secrets" ]; then
  mkdir -p "$(dirname "$FSEC")"
  cp -an "$STAGE/flowise-secrets/." "$FSEC/" 2>/dev/null
  echo "  restored into $FSEC"
else
  echo "  none in archive"
fi

# ---------- 5. What you must check yourself ---------------------------------
step "Restore complete — VERIFY THESE"
cat <<'EOF'
  1. Restart the backend and Flowise, then confirm an agent can call a tool:
       bash ops/verify-agents.sh
     If an agent says it cannot call external tools, the service key in the
     restored Flowise tool rows does not match a principal in the restored
     auth.db. Re-point it:  bash ops/flowise/set-service-key.sh --check
  2. Confirm you can still log in (auth.db came back, not just its file).
  3. Re-ingest the vector store if this is a new machine — it is NOT in the
     backup because it regenerates:  python -m rag.ingest data/offers
  4. Run the suites as the acceptance gate:  python tests_golden.py
EOF
