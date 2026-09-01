# Rotating the internal service key

The three Flowise agents authenticate to the backend with a **service principal**
— a long-lived key sent as `X-API-Key`. Rotation is manual for Version 1.0;
automating it was deliberately deferred until operational need justifies the
complexity.

## When to rotate

- Any suspicion the key leaked (a shared screen, a pasted log, a copied backup).
- Whenever someone with access to the Flowise UI or the Postgres database leaves.
- On a routine schedule if your policy requires one — quarterly is ample for a
  LAN-only deployment.

## What the key can and cannot do

This is the reason rotation is a routine operation rather than an emergency.
The service principal reaches **`/api/tools/*` only**. It cannot read the offer
corpus, ingest, upload, browse the database or read the audit trail — those
return `403` even with a valid key. A leaked agent key exposes the agent tools,
not the platform.

## Procedure

Roughly two minutes, and the agents are down for the Flowise restart only.

```bash
# 1. Issue a new key. The old one stops working the moment this runs.
cd /workspace/vitech-ai-vps/backend
.venv/bin/python -m app.auth.bootstrap service flowise-agents
#    -> prints the key ONCE. It is stored only as a SHA-256, so it cannot be
#       recovered later; if it is lost, just run this again.

# 2. Write it into every Flowise tool row.
cd /workspace/vitech-ai-vps
bash ops/flowise/set-service-key.sh '<the key from step 1>'

# 3. Restart Flowise — the tool rows are cached in the running process.
kill $(pgrep -f flowise); bash /workspace/persistent/flowise-start.sh

# 4. Verify all three agents actually call their tools.
cd backend && .venv/bin/python - <<'PY'
import json, urllib.request, uuid
for name, aid, q in [
    ("Engineering", "c4bfba16-aeb0-4c1b-840e-21b474639a8d", "spec for a paint booth 5m x 3m x 4m liquid"),
    ("Quotation",   "6fa5a302-2d73-4191-bbea-ce98e4af2f1f", "quote wet scrubber 800 cfm 750mm tower 4 nos"),
    ("Drawing",     "f486d388-d032-44bb-acb5-db9dad3b950d", "draw a paint booth 5m x 3m x 4m liquid")]:
    r = urllib.request.Request(f"http://localhost:3000/api/v1/prediction/{aid}",
        data=json.dumps({"question": q, "chatId": uuid.uuid4().hex}).encode(),
        headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=300).read())
    print(name, "->", [t.get("tool") for t in (d.get("usedTools") or [])] or "NO TOOL CALLED")
PY

# 5. Back up Postgres — the agents (and now the key) live there.
bash /workspace/persistent/pg-backup.sh
```

## If the agents stop calling tools

The symptom is the agent replying *"I don't have the ability to call external
tools"* or offering to simulate a response. **That is the same signature as the
backend being down**, so check in this order:

```bash
curl -s localhost:8000/api/health                      # backend alive?
bash ops/flowise/set-service-key.sh --check            # key present in tool rows?
curl -s -o /dev/null -w '%{http_code}\n' \
     -H "X-API-Key: <key>" localhost:8000/api/tools/filters   # expect 200
```

`401` from that last call means the key is wrong or was rotated without updating
the tool rows. `403` means the key is valid but the route is not one the service
principal is allowed to reach — check the policy rather than the key.

## Never do this

- **Do not give the agents a human account.** A user session would grant them
  everything an engineer can do, including the whole offer corpus, and it would
  expire mid-conversation.
- **Do not commit the key.** It belongs in the Flowise tool rows and nowhere
  else. The backend stores only its hash, and `ops/flowise/set-service-key.sh`
  takes it as an argument for exactly this reason.
- **Do not expose Flowise's `credential` table** through the admin console. The
  key lives in that database, which is why "secrets masked server-side" is a
  hard rule rather than a preference.
