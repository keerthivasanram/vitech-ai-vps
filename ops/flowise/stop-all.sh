#!/bin/bash
# Stop the Vitech AI app processes (leaves Postgres/Redis running).
#   bash /workspace/persistent/stop-all.sh
pkill -f "uvicorn app.main"        && echo "backend stopped"  || echo "backend not running"
pkill -f "flowise start"           && echo "flowise stopped"  || echo "flowise not running"
pkill -f "vite"                    && echo "frontend stopped" || echo "frontend not running"
pkill -f "ollama serve"            && echo "ollama stopped"   || echo "ollama not running"
echo "Postgres and Redis left running (use: service postgresql stop / service redis-server stop)."
