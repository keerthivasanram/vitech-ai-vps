#!/bin/bash
# =============================================================================
# Vitech AI platform — back up everything that CANNOT be regenerated.
#
#   bash ops/backup.sh                    # -> $DEST/vitech-backup-<stamp>.tar.gz
#   DEST=/mnt/nas bash ops/backup.sh      # somewhere else
#
# WHY THIS EXISTS, AND WHAT IT CORRECTS
# ------------------------------------
# `pg-backup.sh` dumps Postgres and nothing else. That was complete when the
# agents in Postgres were the only irreplaceable thing on the box. They are not
# any more: three stores the platform itself declares PERMANENT were added and
# never entered any backup, nor the four-bucket audit in
# `docs/disaster-recovery.md` — which is why that audit's "no uncovered item"
# conclusion no longer holds.
#
#   auth.db    accounts, password hashes, sessions, and the PERMANENT audit
#              trail — the record of who asked for what, and what was denied.
#   ops.db     the PERMANENT job record: one row per specification, drawing,
#              BOM, quotation and package the platform has ever issued.
#   data/jobs  the artifacts themselves — the actual documents a customer
#              received, each with the SHA-256 it was issued under.
#
# Losing those is not "re-ingest and carry on" like Chroma or the Ollama models.
# There is no second copy anywhere: they are gitignored (correctly — they hold
# password hashes and customer requirements), they are not in the critical
# tarball, and nothing else writes them.
#
# THE SQLITE POINT, which is the reason this is not five `cp` lines:
# the backend holds both databases OPEN. Copying a live SQLite file with `cp`
# can capture a torn write — a backup that restores to a corrupt database, and
# you find out when you need it. Both are copied through SQLite's own online
# backup API, then `PRAGMA integrity_check` is run on the COPY. A backup that
# has not been read back is only a hope.
#
# RESTORE: see `ops/restore.sh`, and rehearse it — an unrehearsed restore is an
# untested code path holding your audit trail.
# =============================================================================
set -u
REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
DEST=${DEST:-/workspace/persistent/backups}
DATA=$REPO/backend/data
STAMP=$(date +%Y%m%d-%H%M%S)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

PY=$(command -v python3 || echo "$REPO/backend/.venv/bin/python3")
step() { echo; echo "== $* =="; }
warn() { echo "  WARNING: $*"; }

[ -d "$REPO" ] || { echo "FATAL: repo not found at $REPO"; exit 1; }
mkdir -p "$DEST" "$STAGE/sqlite" "$STAGE/postgres"

# ---------- 1. Postgres — the three Flowise agents --------------------------
# The agents are the one asset not reproducible from git. Everything else in
# this database is Flowise's own state.
step "PostgreSQL (the agents)"
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
fi
if command -v pg_dump >/dev/null && [ -n "${POSTGRES_USER:-}" ]; then
  if PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump -h localhost -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" -F p > "$STAGE/postgres/${POSTGRES_DB}.sql" 2>"$STAGE/pg.err"; then
    # COUNT THE ROWS INSIDE THE COPY BLOCK, not INSERT statements. A plain
    # pg_dump writes COPY ... FROM stdin followed by tab-separated rows, so
    # grepping for "INSERT INTO public.chat_flow" returns 0 on a PERFECTLY GOOD
    # dump — and this script would then warn that the agents were missing on
    # every single run. A backup check that cries wolf every time is one nobody
    # reads on the day it is right.
    dump=$STAGE/postgres/${POSTGRES_DB}.sql
    count_copy() {   # rows between "COPY public.<table> (" and the closing \.
      awk -v tbl="$1" '
        $0 ~ "^COPY public\\." tbl " \\(" {inblock=1; next}
        inblock && $0 == "\\."            {inblock=0}
        inblock                            {n++}
        END {print n+0}' "$dump"
    }
    flows=$(count_copy chat_flow)
    tools=$(count_copy tool)
    echo "  dumped $(du -h "$dump" | cut -f1) | chatflow rows: $flows | tool rows: $tools"
    [ "$flows" -gt 0 ] || warn "the dump contains NO chatflow rows — the agents would NOT come back from it"
    for agent in "Engineering Agent" "Quotation Agent" "Drawing Agent"; do
      grep -qF "$agent" "$dump" || warn "'$agent' is NOT in the dump"
    done
  else
    warn "pg_dump failed: $(head -2 "$STAGE/pg.err" | tr '\n' ' ')"
  fi
else
  warn "pg_dump or POSTGRES_USER unavailable — Postgres NOT backed up"
fi

# ---------- 2. The two SQLite stores, through the online backup API ---------
step "SQLite stores (auth.db, ops.db)"
"$PY" - "$DATA" "$STAGE/sqlite" <<'PYEOF'
import sqlite3, sys, os
src_dir, out_dir = sys.argv[1], sys.argv[2]
for name in ("auth.db", "ops.db"):
    src = os.path.join(src_dir, name)
    if not os.path.exists(src):
        print(f"  {name}: ABSENT at {src} — nothing to back up")
        continue
    dst = os.path.join(out_dir, name)
    # The online backup API is the whole point: it takes a consistent snapshot
    # of a database another process is actively writing to.
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    with d:
        s.backup(d)
    s.close()
    # Read the COPY back. An unverified backup is a hope, not a backup.
    ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    counts = []
    for tbl in ("vitech_user", "vitech_audit", "vitech_job", "vitech_artifact"):
        try:
            counts.append(f"{tbl}={d.execute(f'SELECT count(*) FROM {tbl}').fetchone()[0]}")
        except sqlite3.Error:
            pass
    d.close()
    size = os.path.getsize(dst)
    print(f"  {name}: {size:,} bytes | integrity_check={ok} | {' '.join(counts)}")
    if ok != "ok":
        print(f"  WARNING: {name} COPY FAILED ITS INTEGRITY CHECK")
PYEOF

# ---------- 3. The issued documents themselves ------------------------------
# Every artifact carries the SHA-256 it was issued under, and the platform
# refuses to serve one whose digest no longer matches. So the backup verifies
# the same thing: a silently rotted artifact is found HERE rather than when a
# customer asks for the drawing again.
step "Issued artifacts (data/jobs)"
if [ -d "$DATA/jobs" ]; then
  cp -a "$DATA/jobs" "$STAGE/jobs"
  "$PY" - "$STAGE/sqlite/ops.db" "$STAGE/jobs" <<'PYEOF'
import hashlib, os, sqlite3, sys
db, root = sys.argv[1], sys.argv[2]
if not os.path.exists(db):
    print("  ops.db absent — artifacts copied but NOT digest-verified"); raise SystemExit
conn = sqlite3.connect(db)
rows = conn.execute("SELECT job_id, name, path, sha256 FROM vitech_artifact").fetchall()
checked = missing = bad = 0
for job_id, name, path, sha in rows:
    p = os.path.join(root, job_id, name)
    if not os.path.exists(p):
        missing += 1; continue
    if sha:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() != sha:
            bad += 1; print(f"  DIGEST MISMATCH: {job_id}/{name}")
            continue
    checked += 1
total = sum(len(files) for _, _, files in os.walk(root))
print(f"  {total} files in {len(os.listdir(root))} job folders")
print(f"  digest-verified {checked}/{len(rows)} recorded artifacts"
      + (f" | {missing} missing" if missing else "")
      + (f" | {bad} MISMATCHED" if bad else ""))
if bad:
    print("  WARNING: a mismatched artifact is not the document that was issued")
PYEOF
else
  echo "  no artifacts yet ($DATA/jobs absent)"
fi

# ---------- 4. Flowise encryption key ---------------------------------------
# Flowise credentials are encrypted with this key. Lose it and every stored
# credential — including the backend service key the agents authenticate with —
# is unreadable even though the rows survive in the Postgres dump.
step "Flowise encryption key"
FSEC=${FLOWISE_SECRETS:-/workspace/persistent/flowise/secrets}
if [ -d "$FSEC" ]; then
  cp -a "$FSEC" "$STAGE/flowise-secrets"
  echo "  copied from $FSEC"
else
  warn "no Flowise secrets at $FSEC — stored credentials would not decrypt after a restore"
fi

# ---------- 5. Manifest -----------------------------------------------------
step "Manifest"
{
  echo "Vitech AI platform backup"
  echo "created   : $(date -Is)"
  echo "host      : $(hostname)"
  echo "repo      : $REPO"
  echo "git commit: $(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "git branch: $(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo
  echo "CONTENTS"
  echo "  postgres/       the three Flowise agents + Flowise state"
  echo "  sqlite/auth.db  accounts, password hashes, PERMANENT audit trail"
  echo "  sqlite/ops.db   PERMANENT job records (every document ever issued)"
  echo "  jobs/           the issued artifacts, digest-verified at backup time"
  echo "  flowise-secrets the key those stored credentials are encrypted with"
  echo
  echo "NOT INCLUDED, because it regenerates:"
  echo "  Ollama models (re-pull) | Chroma vectors (re-ingest from data/offers)"
  echo "  node_modules, .venv, Docker images"
  echo
  echo "RESTORE: bash ops/restore.sh <this-tarball>"
} > "$STAGE/MANIFEST.txt"
cat "$STAGE/MANIFEST.txt" | sed 's/^/  /'

# ---------- 6. Write it atomically ------------------------------------------
step "Writing archive"
OUT=$DEST/vitech-backup-$STAMP.tar.gz
tar czf "$OUT.tmp" -C "$STAGE" . && mv "$OUT.tmp" "$OUT"
echo "  $OUT ($(du -h "$OUT" | cut -f1))"
echo
echo "Done. COPY IT OFF THIS MACHINE — a backup on the same volume as the"
echo "original does not survive the failure it exists for."
