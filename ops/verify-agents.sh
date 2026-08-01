#!/usr/bin/env bash
# Prove the agent prompts in git reproduce the LIVE agents in Postgres.
#
# This is the check that makes GitHub a trustworthy backup: if someone tuned a
# prompt on the server without mirroring it into ops/flowise/*.py, a rebuild
# from git would silently produce older behaviour. Run before a migration and
# after a restore.
#
#   bash ops/verify-agents.sh            # against a local psql
#   PSQL="docker compose -f docker-compose.prod.yml exec -T postgres psql" \
#     bash ops/verify-agents.sh          # against the compose stack
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
DSN="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${PGHOST:-localhost}:5432/${POSTGRES_DB}"
PSQL="${PSQL:-psql \"$DSN\"}"

python3 - "$PSQL" <<'PY'
import json, subprocess, sys, shlex
PSQL = sys.argv[1]
PAIRS = [("Engineering Agent", "ops/flowise/agent-harden-prompt.py"),
         ("Quotation Agent",   "ops/flowise/quotation-agent-build.py"),
         ("Drawing Agent",     "ops/flowise/drawing-agent-build.py")]

def q(sql):
    return subprocess.run(shlex.split(PSQL) + ["-tAc", sql],
                          capture_output=True, text=True).stdout

def live(name):
    fd = q(f"SELECT \"flowData\" FROM chat_flow WHERE name='{name}';").strip()
    if not fd:
        return None
    for n in json.loads(fd)["nodes"]:
        if n["data"]["name"] == "toolAgent":
            return n["data"]["inputs"]["systemMessage"]
    return None

def from_script(path):
    s = open(path).read()
    i = s.index('SYS = """') + len('SYS = """')
    return s[i:s.index('"""', i)]

print(f"  {'AGENT':<20}{'LIVE':>8}{'GIT':>8}   MATCH")
ok = True
for name, path in PAIRS:
    lp, sp = live(name), from_script(path)
    if lp is None:
        print(f"  {name:<20}{'ABSENT':>8}{len(sp):>8}   *** NOT IN DATABASE ***")
        ok = False
        continue
    same = lp.strip() == sp.strip()
    ok &= same
    print(f"  {name:<20}{len(lp):>8}{len(sp):>8}   {'yes' if same else '*** NO ***'}")
print()
print("RESULT:", "all three agents reproducible from git" if ok
      else "MISMATCH - mirror the live prompt into ops/flowise/ before migrating")
sys.exit(0 if ok else 1)
PY
