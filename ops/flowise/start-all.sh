#!/bin/bash
# Vitech AI platform — relaunch every service after a pod stop/start.
# All data lives on the /workspace persistent volume; this only restarts the
# processes (they are plain background procs, not managed by systemd here).
#
#   bash /workspace/persistent/start-all.sh
#
# Idempotent: skips anything already listening.

set -u
REPO=/workspace/vitech-ai-vps
LOGDIR=/workspace/persistent/logs
mkdir -p "$LOGDIR"

up() { curl -s -o /dev/null -m 3 "$1" 2>/dev/null; }        # HTTP check
listening() { ss -tlnp 2>/dev/null | grep -q ":$1 "; }       # port check

echo "== PostgreSQL =="
if pg_isready -q 2>/dev/null; then echo "  already up"; else service postgresql start; fi

echo "== Redis =="
if [ "$(redis-cli ping 2>/dev/null)" = "PONG" ]; then echo "  already up"; else service redis-server start; fi

echo "== Ollama (:11434) =="
if up http://localhost:11434/api/version; then
  echo "  already up"
else
  nohup ollama serve > "$LOGDIR/ollama.log" 2>&1 &
  disown
  until up http://localhost:11434/api/version; do sleep 2; done
  echo "  started"
fi

echo "== Backend FastAPI (:8000) =="
if up http://localhost:8000/api/health; then
  echo "  already up"
else
  cd "$REPO/backend"
  nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$LOGDIR/backend.log" 2>&1 &
  disown
  until up http://localhost:8000/api/health; do sleep 2; done
  echo "  started"
fi

echo "== Flowise (:3000) =="
if up http://localhost:3000/; then
  echo "  already up"
else
  nohup /workspace/persistent/flowise-start.sh > "$LOGDIR/flowise.log" 2>&1 &
  disown
  until up http://localhost:3000/; do sleep 3; done
  echo "  started"
fi

echo "== Frontend (:5173) =="
if listening 5173; then
  echo "  already up"
else
  cd "$REPO/frontend"
  nohup npm run dev -- --host 0.0.0.0 > "$LOGDIR/frontend.log" 2>&1 &
  disown
  until listening 5173; do sleep 2; done
  echo "  started"
fi

echo
echo "== Status =="
printf "  backend : %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health)"
printf "  flowise : %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/)"
printf "  frontend: %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/)"
printf "  ollama  : %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:11434/api/version)"
printf "  postgres: %s\n" "$(pg_isready -q && echo up || echo DOWN)"
printf "  redis   : %s\n" "$(redis-cli ping 2>/dev/null)"
echo
echo "Model in use: $(grep OLLAMA_MODEL "$REPO/backend/.env" | cut -d= -f2)"
echo "Done. Forward ports 3000 (Flowise), 5173 (frontend), 8000 (backend) in the VS Code PORTS panel."
