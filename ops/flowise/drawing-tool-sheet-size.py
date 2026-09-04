#!/usr/bin/env python3
"""Give `generate_drawing` a SHEET SIZE input of its own.

    python3 ops/flowise/drawing-tool-sheet-size.py

THE BUG THIS FIXES, which is a golden-rule-#2 breach reaching a customer sheet.

`generate_drawing` took ONE input: the requirement string. `/api/tools/drawing`
has always accepted a separate `sheet_size`, but the tool never offered it — so
when a user asked "can you put it on an A2 sheet?", the model had nowhere to put
"A2" except inside the requirement it re-sent. After a few conversational turns
it stopped appending the words and started substituting the PAPER's dimensions
for the MACHINE's:

    USER : draw a paint booth 5m x 3m x 4m
    ...   (a few turns of questions)
    USER : can you put it on an A2 sheet?
    AGENT: Paint Booth - General Arrangement (DRAFT)
           Envelope: 420 x 297 x 4000 mm          <- A2 IS 420 x 297 mm

A paint booth the size of a sheet of paper, presented as a real GA with a
straight face. Reproduced 4/4 after a five-turn conversation and 0/5 after a
single turn — it needs conversational context to trigger, which is why it
survived every previous verification round: those tested one turn at a time.

WHY THE FIX IS A SCHEMA CHANGE AND NOT A PROMPT RULE. Telling an 8B model
"never put a paper size in the requirement" is asking it to hold a distinction
it demonstrably loses under context pressure. Giving the paper size its own
input means the requirement string never has to carry it — the distinction is
enforced by the shape of the call rather than by the model's attention. Same
reasoning as `lookup_markdown` and the `delete data.svg` line: give the model
less to get wrong.

TRAP, learned the hard way and re-applied here: an optional property the model
omits is UNDEFINED inside the NodeVM, and a bare `$sheet_size` then throws a
ReferenceError. The agent sees an empty tool result and INVENTS an answer —
the worst failure mode, because the call looks successful from outside. Every
optional property must be read as `(typeof $x !== 'undefined' ? $x : null)`.
"""
import json
import re
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__)) + "/../.."
TOOL = "generate_drawing"


def dsn() -> str:
    env = {}
    with open(os.path.join(REPO, ".env")) as fh:
        for line in fh:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return (f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
            f"@localhost:5432/{env['POSTGRES_DB']}")


def psql(sql: str) -> str:
    return subprocess.run(["psql", dsn(), "-tAc", sql],
                          capture_output=True, text=True, check=True).stdout


def esc(s: str) -> str:
    return s.replace("'", "''")


SCHEMA = [
    {"id": 0, "property": "question", "type": "string", "required": True,
     "description": ("The EQUIPMENT requirement in the user's own words, keeping every "
                     "dimension and unit exactly. This describes the MACHINE only. "
                     "A paper size (A4, A3, A2, A1) is NOT part of the requirement - "
                     "it goes in sheet_size. Never put a paper size here.")},
    {"id": 1, "property": "sheet_size", "type": "string", "required": False,
     "description": ("The PAPER size to draw on: A4, A3, A2 or A1. Send it only when "
                     "the user asks for a particular sheet. This is the size of the "
                     "PAPER, never the size of the equipment. Omit it otherwise.")},
]


def main() -> int:
    row = psql(f"SELECT id FROM tool WHERE name='{TOOL}';").strip()
    if not row:
        print(f"FATAL: no '{TOOL}' tool row — run drawing-agent-build.py first")
        return 1
    tool_id = row.splitlines()[0].strip()

    # Keep the service key that is already in the row: it is the credential the
    # agents authenticate to the backend with, and it is not ours to rotate here.
    current = psql(f"SELECT func FROM tool WHERE id='{tool_id}';")
    # Read it out of the header it already sits in, rather than guessing at the
    # shape of a key. The first version required a hyphen and this key uses
    # underscores, so it found nothing — and correctly refused to write.
    found = re.search(r"['\"]X-API-Key['\"]\s*:\s*['\"]([^'\"]+)['\"]", current)
    key = found.group(1) if found else ""
    if not key:
        print("FATAL: could not read the service key out of the existing tool row.")
        print("       Refusing to write a tool that cannot authenticate.")
        return 1

    func = (
        "const fetch = require('node-fetch');\n"
        # An optional property the model omits is UNDEFINED here — see the
        # module docstring. Reading it bare throws inside the NodeVM.
        "const sheet = (typeof $sheet_size !== 'undefined' ? $sheet_size : null);\n"
        "const body = { question: $question };\n"
        # Only a recognised paper size is forwarded. Anything else is dropped
        # rather than passed through: the backend would default it anyway, and
        # a stray value here is more likely to be a stray token than an intent.
        "if (sheet && /^A[1-4]$/i.test(String(sheet).trim())) {\n"
        "    body.sheet_size = String(sheet).trim().toUpperCase();\n"
        "}\n"
        "const res = await fetch('http://localhost:8000/api/tools/drawing', {\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json', 'X-API-Key': '" + key + "' },\n"
        "    body: JSON.stringify(body)\n"
        "});\n"
        "const data = await res.json();\n"
        # The sheet is for the canvas, not the model: 16 kB of vector data
        # swamps an 8B context with something it cannot use.
        "delete data.svg;\n"
        "return JSON.stringify(data);\n"
    )

    subprocess.run(["psql", dsn(), "-v", "ON_ERROR_STOP=1", "-c",
                    f"UPDATE tool SET schema='{esc(json.dumps(SCHEMA))}', "
                    f"func='{esc(func)}' WHERE id='{tool_id}';"], check=True)
    print(f"updated tool '{TOOL}' ({tool_id})")
    print("  + sheet_size (optional, A1-A4, validated, safely accessed)")
    print("  question now says a paper size is NOT part of the requirement")
    print("\nRestart Flowise for the tool row to be re-read, then verify a "
          "MULTI-TURN conversation — one turn is not enough to reproduce this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
