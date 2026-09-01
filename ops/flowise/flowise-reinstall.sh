#!/bin/bash
# Rebuild the isolated production Flowise install on /opt (container disk).
# Only needed after a pod DELETE (a stop/start keeps /opt). Data (chatflows,
# credentials) lives in Postgres and is NOT touched by this.
#
# Pinned to flowise@3.0.13 (last line whose flowise-components uses the
# @langchain/core 0.3.x tree). Two deps that 3.0.13 forgot to declare are added
# back (they were added upstream in 3.1.0), and the two deprecated ReActAgent
# nodes are removed because their transitive langgraph import references a
# langchain-core subpath (./utils/uuid) that no npm build of Flowise ships.
#
# flowise@3.0.13's own package.json references flowise-components/-ui with a
# CARET range (^3.0.13), so a plain `npm install` re-resolves against whatever
# is newest on the registry today — which has since moved to 3.1.x, pulling in
# @langchain/core 1.1.x/1.2.x (a version whose ./utils/uuid subpath IS missing,
# reproducing the exact crash above). The "overrides" block below hard-pins
# flowise-components/-ui to 3.0.13 so this can't silently drift again.
#
# lunary@0.7.15 is added at top level for the same reason as the azure packages:
# flowise's own code eager-requires it (dist/utils/updateChatMessageFeedback.js)
# but only flowise-components declares it, so pinning components to 3.0.13 leaves
# lunary nested where `flowise` can't resolve it → "Cannot find module 'lunary'".
# Declaring it here hoists it to the top level.
set -e
SNAP=/workspace/persistent/flowise-app.tar.gz
mkdir -p /opt/flowise-app

# ---- FAST PATH: restore the pre-built, patched, version-pinned tree ----------
# A migrated/deleted pod wipes /opt (container disk). Rebuilding from npm takes
# ~20 min (3300 pkgs + native C++ compiles) AND risks silent version drift. If a
# snapshot of a known-good tree exists on the persistent volume, extract that
# instead (~1-2 min, and it freezes the exact working versions — no drift).
# Force a clean npm rebuild instead with:  flowise-reinstall.sh --from-npm
if [ -f "$SNAP" ] && [ "${1:-}" != "--from-npm" ]; then
  echo "Restoring Flowise from snapshot $SNAP (fast path)…"
  tar xzf "$SNAP" -C /opt/flowise-app
  if [ -x /opt/flowise-app/node_modules/.bin/flowise ]; then
    echo "Flowise restored from snapshot. Start with: bash /workspace/persistent/start-all.sh"
    exit 0
  fi
  echo "WARNING: snapshot extracted but flowise binary missing — falling through to npm rebuild."
fi

# ---- SLOW PATH: rebuild from npm (first-time seed, or --from-npm) ------------
cd /opt/flowise-app
cat > package.json <<'JSON'
{
  "name": "vitech-flowise",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "flowise": "3.0.13",
    "multer-azure-blob-storage": "^1.2.0",
    "winston-azure-blob": "^1.5.0",
    "lunary": "0.7.15"
  },
  "overrides": {
    "flowise-components": "3.0.13",
    "flowise-ui": "3.0.13"
  }
}
JSON
npm install --omit=dev --no-audit --no-fund
# Remove the 2 deprecated nodes that throw the ./utils/uuid load error.
rm -rf node_modules/flowise-components/dist/nodes/agents/ReActAgentChat
rm -rf node_modules/flowise-components/dist/nodes/agents/ReActAgentLLM
# Fix the OpenAPI Toolkit data-URI decoder (upstream double-pop bug corrupts
# uploaded specs so Server/Endpoints never populate).
python3 - <<'PY'
f = "/opt/flowise-app/node_modules/flowise-components/dist/nodes/tools/OpenAPIToolkit/OpenAPIToolkit.js"
s = open(f).read()
bad = ("                    splitDataURI.pop();\n"
       "                    const bf = Buffer.from(splitDataURI.pop() || '', 'base64');\n"
       "                    utf8String = bf.toString('utf-8');")
good = ("                    // VITECH PATCH: upstream double-pop discarded the base64 payload and\n"
        "                    // decoded the data-URI header instead. Take everything after the first\n"
        "                    // comma as the base64 content.\n"
        "                    utf8String = Buffer.from(openApiFile.substring(openApiFile.indexOf(',') + 1), 'base64').toString('utf-8');")
if bad in s:
    open(f, "w").write(s.replace(bad, good)); print("OpenAPI Toolkit data-URI decoder patched")
elif good in s:
    print("OpenAPI Toolkit already patched")
else:
    print("WARNING: OpenAPI Toolkit decoder block not found — verify upstream code")
PY
echo "Flowise reinstalled + patched at /opt/flowise-app."

# Seed the snapshot from this freshly-built, patched tree if one does not exist
# yet, so the NEXT pod gets the fast path above. Never auto-overwrites an
# existing (known-good) snapshot — to refresh it deliberately after a verified
# rebuild, delete $SNAP first, or re-run: flowise-snapshot.sh
if [ ! -f "$SNAP" ]; then
  echo "Seeding snapshot $SNAP for fast future restores…"
  tar czf "$SNAP.partial" -C /opt/flowise-app node_modules package.json \
    && mv "$SNAP.partial" "$SNAP" \
    && echo "Snapshot seeded: $(du -h "$SNAP" | cut -f1)"
fi
echo "Start with: bash /workspace/persistent/start-all.sh"
