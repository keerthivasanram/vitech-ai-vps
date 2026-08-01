#!/bin/bash
# =============================================================================
# Vitech AI platform — REBUILD THE CONTAINER DISK
#
# Run this ONLY when the pod's container disk was wiped (after a pod stop/start
# that lost it, or a fresh pod attached to the same /workspace volume). It
# reinstalls everything that does NOT live on the persistent volume:
#   PostgreSQL, Redis, Node.js 20, the Ollama binary, Flowise (/opt/flowise-app)
# then recreates the DB role/database and restores the Engineering Agent.
#
#   bash /workspace/persistent/bootstrap-pod.sh   # then: start-all.sh
#
# Safe to re-run: every step is skipped if already present, and the database is
# only restored when it is empty (it will never clobber a live agent).
#
# SURVIVES a wipe on /workspace (nothing to do): the repo, backend/.venv,
# frontend/node_modules, Ollama MODELS, ChromaDB, Flowise keys, the pg dump.
# =============================================================================
set -u
REPO=/workspace/vitech-ai-vps
PERS=/workspace/persistent
DUMP=$PERS/postgres-backups/vitech.sql
step() { echo; echo "== $* =="; }

# ---------- preflight -------------------------------------------------------
[ -d "$REPO" ]  || { echo "FATAL: $REPO missing — is the /workspace volume attached?"; exit 1; }
[ -f "$REPO/.env" ] || { echo "FATAL: $REPO/.env missing — cannot know DB credentials."; exit 1; }
set -a; . "$REPO/.env"; set +a
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"

# ---------- 1. PostgreSQL + Redis ------------------------------------------
step "PostgreSQL + Redis"
if command -v psql >/dev/null && command -v redis-server >/dev/null; then
  echo "  already installed"
else
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql redis-server >/dev/null
  echo "  installed"
fi
pg_isready -q 2>/dev/null || service postgresql start
[ "$(redis-cli ping 2>/dev/null)" = "PONG" ] || service redis-server start
until pg_isready -q 2>/dev/null; do sleep 1; done
echo "  postgres up | redis: $(redis-cli ping 2>/dev/null)"

# ---------- 2. Node.js 20 ---------------------------------------------------
step "Node.js 20"
if command -v node >/dev/null && node -v | grep -q '^v20'; then
  echo "  already installed ($(node -v))"
else
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs >/dev/null
  echo "  installed ($(node -v))"
fi

# ---------- 3. Ollama binary (models already on the volume) -----------------
step "Ollama"
if command -v ollama >/dev/null; then
  echo "  binary already installed"
else
  curl -fsSL https://ollama.com/install.sh | sh >/dev/null 2>&1
  echo "  binary installed"
fi
# models live on the persistent volume; /root/.ollama must point at them
if [ ! -L /root/.ollama ]; then
  rm -rf /root/.ollama
  ln -s "$PERS/ollama" /root/.ollama
  echo "  linked /root/.ollama -> $PERS/ollama"
else
  echo "  models already linked ($(du -sh "$PERS/ollama" 2>/dev/null | cut -f1))"
fi

# ---------- 4. Flowise (isolated, pinned + patched) ------------------------
step "Flowise (/opt/flowise-app)"
if [ -x /opt/flowise-app/node_modules/.bin/flowise ]; then
  echo "  already installed ($(/opt/flowise-app/node_modules/.bin/flowise --version 2>/dev/null | head -1))"
else
  echo "  installing — this takes ~12 min (3300 packages)…"
  bash "$PERS/flowise-reinstall.sh"
fi

# ---------- 5. DB role + database ------------------------------------------
step "Database role + schema"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$POSTGRES_USER'" | grep -q 1 \
  || sudo -u postgres psql -qc "CREATE ROLE $POSTGRES_USER LOGIN PASSWORD '$POSTGRES_PASSWORD';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB'" | grep -q 1 \
  || sudo -u postgres psql -qc "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"
echo "  role '$POSTGRES_USER' + database '$POSTGRES_DB' ready"

# ---------- 6. Restore the Engineering Agent -------------------------------
step "Restore Engineering Agent + tools"
DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@localhost:5432/$POSTGRES_DB"
EXISTING=$(psql "$DSN" -tAc "SELECT count(*) FROM chat_flow" 2>/dev/null || echo 0)
if [ "${EXISTING:-0}" -gt 0 ]; then
  echo "  SKIPPED — database already has $EXISTING chatflow(s); refusing to clobber."
  echo "  (To force: drop the DB first, then re-run.)"
elif [ -f "$DUMP" ]; then
  psql "$DSN" -q -f "$DUMP" >/dev/null 2>&1
  n=$(psql "$DSN" -tAc "SELECT count(*) FROM chat_flow" 2>/dev/null || echo 0)
  t=$(psql "$DSN" -tAc "SELECT count(*) FROM tool" 2>/dev/null || echo 0)
  echo "  restored from $(basename "$DUMP"): $n chatflow(s), $t tool(s)"
else
  echo "  WARNING: no dump at $DUMP — the agent must be rebuilt:"
  echo "    python3 $PERS/agent-build.py && python3 $PERS/agent-harden-prompt.py"
fi

# ---------- 7. Git SSH key (container disk — lost on wipe) ------------------
# Restore the SAME key from the volume backup so you never have to re-add it to
# GitHub after a wipe. Only generate a fresh key if no backup exists.
step "Git SSH key"
mkdir -p /root/.ssh && chmod 700 /root/.ssh
# trust GitHub's host key (known_hosts also lives on the wiped container disk)
ssh-keygen -F github.com >/dev/null 2>&1 || ssh-keyscan -t ed25519,rsa github.com >> /root/.ssh/known_hosts 2>/dev/null
if [ -f /root/.ssh/id_ed25519 ]; then
  echo "  key present"
elif [ -f "$PERS/ssh/id_ed25519" ]; then
  cp "$PERS/ssh/id_ed25519" "$PERS/ssh/id_ed25519.pub" /root/.ssh/
  chmod 600 /root/.ssh/id_ed25519
  echo "  restored git SSH key from the volume ($PERS/ssh) — already trusted by GitHub"
else
  ssh-keygen -t ed25519 -C "vitech-runpod-pod" -f /root/.ssh/id_ed25519 -N "" -q
  chmod 600 /root/.ssh/id_ed25519
  mkdir -p "$PERS/ssh" && cp /root/.ssh/id_ed25519 /root/.ssh/id_ed25519.pub "$PERS/ssh/"
  echo "  NEW key generated (backed up to $PERS/ssh) — add this to https://github.com/settings/ssh/new to push:"
  echo "    $(cat /root/.ssh/id_ed25519.pub)"
fi

# ---------- done ------------------------------------------------------------
step "Bootstrap complete"
AGENT_ID=$(psql "$DSN" -tAc "SELECT id FROM chat_flow WHERE name='Engineering Agent'" 2>/dev/null | tr -d ' ')
# NOTE: never echo $DSN — it contains POSTGRES_PASSWORD.
cat <<EOF
  Next:  bash $PERS/start-all.sh
  Then forward ports 5173 (app), 3000 (Flowise), 8000 (backend) in VS Code PORTS.

  Engineering Agent id: ${AGENT_ID:-<none — rebuild with agent-build.py>}

  Smoke-test the agent once Flowise is up:
    curl -s -X POST http://localhost:3000/api/v1/prediction/${AGENT_ID:-<id>} \\
      -H 'Content-Type: application/json' \\
      -d '{"question":"quote wet scrubber 800 cfm 750mm tower 4 nos","chatId":"smoke"}'
EOF
