#!/bin/bash
# =============================================================================
# Put the internal-service key into every Flowise agent tool row.
#
#   bash ops/flowise/set-service-key.sh <service-key>
#   bash ops/flowise/set-service-key.sh --check
#
# The three agents call /api/tools/* from localhost and cannot present a user
# session, so they authenticate with a service key sent as `X-API-Key`. That key
# lives in each tool's JavaScript body, in Flowise's own `tool` table.
#
# THE KEY IS NEVER COMMITTED. It is passed as an argument, and the backend
# stores only its SHA-256 — so it cannot be recovered, and a rotation always
# issues a new one. Full runbook: ops/rotate-service-key.md
#
# Uses psql, which is already on the box. Deliberately NOT psycopg2: adding a
# Postgres driver to the backend purely for an ops script would be a new
# dependency in a stack the production review already flagged as under-pinned.
#
# IF THIS STEP IS SKIPPED after enabling authentication, all three agents fail
# with "I don't have the ability to call external tools" — the SAME signature as
# the backend being down, so check here first.
# =============================================================================
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a; . "$REPO/.env"; set +a
DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@localhost:5432/$POSTGRES_DB"

OLD="headers: { 'Content-Type': 'application/json' }"

if [ "${1:-}" = "--check" ] || [ -z "${1:-}" ]; then
  echo "Flowise tool rows:"
  psql "$DSN" -tAc "SELECT name || '  ' || CASE WHEN position('X-API-Key' in func) > 0
                      THEN 'key present' ELSE 'NO KEY - agents will fail' END
                    FROM tool ORDER BY name;" | sed 's/^/  /'
  [ -z "${1:-}" ] && { echo; echo "usage: $0 <service-key> | --check"; exit 1; }
  exit 0
fi

KEY="$1"
NEW="headers: { 'Content-Type': 'application/json', 'X-API-Key': '$KEY' }"

# Idempotent: any existing key is stripped first, so re-running with a rotated
# key replaces rather than appends.
psql "$DSN" -q <<SQL
UPDATE tool
   SET func = regexp_replace(func, ', ''X-API-Key'': ''[^'']*''', '', 'g')
 WHERE position('X-API-Key' in func) > 0;
UPDATE tool
   SET func = replace(func, \$old\$$OLD\$old\$, \$new\$$NEW\$new\$)
 WHERE position(\$old\$$OLD\$old\$ in func) > 0;
SQL

echo "Updated:"
psql "$DSN" -tAc "SELECT name || '  ' || CASE WHEN position('X-API-Key' in func) > 0
                    THEN 'key set' ELSE 'NOT SET' END FROM tool ORDER BY name;" | sed 's/^/  /'
cat <<'EOF'

NEXT — the tool rows are cached in the running process:
  kill $(pgrep -f flowise) ; bash /workspace/persistent/flowise-start.sh
Then back up Postgres, because the agents live there:
  bash /workspace/persistent/pg-backup.sh
EOF
