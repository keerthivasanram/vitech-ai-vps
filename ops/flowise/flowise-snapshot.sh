#!/bin/bash
# Snapshot the CURRENT /opt/flowise-app (patched, version-pinned node_modules +
# package.json) to the persistent volume, so a migrated/deleted pod can restore
# it in ~1-2 min instead of rebuilding from npm (~20 min + native compiles).
#
# flowise-reinstall.sh extracts $SNAP automatically when present (its fast path).
# Run this AFTER you have verified the running Flowise is healthy — it overwrites
# any existing snapshot. Atomic: writes .partial then renames, so a killed run
# never leaves a half-written tarball that would be mistaken for good.
#
#   bash /workspace/persistent/flowise-snapshot.sh
set -e
SNAP=/workspace/persistent/flowise-app.tar.gz
APP=/opt/flowise-app

[ -x "$APP/node_modules/.bin/flowise" ] || {
  echo "FATAL: $APP/node_modules/.bin/flowise missing — nothing good to snapshot."; exit 1; }

echo "Snapshotting $APP → $SNAP …"
tar czf "$SNAP.partial" -C "$APP" node_modules package.json
mv "$SNAP.partial" "$SNAP"
echo "Snapshot written: $(du -h "$SNAP" | cut -f1)"
