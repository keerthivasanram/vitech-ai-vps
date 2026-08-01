#!/bin/bash
set -a
source /workspace/vitech-ai-vps/.env
set +a
DEST=/workspace/persistent/postgres-backups
mkdir -p "$DEST"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F p > "$DEST/${POSTGRES_DB}.sql.tmp" \
  && mv "$DEST/${POSTGRES_DB}.sql.tmp" "$DEST/${POSTGRES_DB}.sql"
