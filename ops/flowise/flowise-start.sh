#!/bin/bash
set -a
source /workspace/vitech-ai-vps/.env
set +a
export PORT=3000
export DATABASE_TYPE=postgres
export DATABASE_HOST=localhost
export DATABASE_PORT=5432
export DATABASE_NAME="${POSTGRES_DB}"
export DATABASE_USER="${POSTGRES_USER}"
export DATABASE_PASSWORD="${POSTGRES_PASSWORD}"
export FLOWISE_USERNAME="${FLOWISE_USERNAME}"
export FLOWISE_PASSWORD="${FLOWISE_PASSWORD}"
export LOG_PATH=/workspace/persistent/flowise/logs
export SECRETKEY_PATH=/workspace/persistent/flowise/secrets
export BLOB_STORAGE_PATH=/workspace/persistent/flowise/storage
# SSRF policy (user-authorized): the whole architecture is Flowise -> localhost
# backend/Ollama, but Flowise's default deny-list blocks loopback. Drop the default
# list and keep only cloud-metadata / link-local / 0.0.0.0 denied (the real SSRF
# risk) so Custom Tools can reach http://localhost:8000 while 169.254.x stays blocked.
export HTTP_SECURITY_CHECK=false
export HTTP_DENY_LIST=169.254.0.0/16,fd00:ec2::254,0.0.0.0
# Isolated production install (not global npm) — see /opt/flowise-app.
# Reinstall after a pod DELETE: bash /workspace/persistent/flowise-reinstall.sh
exec /opt/flowise-app/node_modules/.bin/flowise start
