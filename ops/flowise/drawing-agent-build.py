#!/usr/bin/env python3
"""Build the Vitech DRAWING AGENT as a third Flowise chatflow.

Same architecture as the Engineering and Quotation Agents (ChatOllama
llama3.1:8b @ temp 0 + BufferMemory + Tool Agent). It clones the LIVE
Engineering Agent's flow (which guarantees correctly-shaped nodes for this
install), creates the new `generate_drawing` tool row if missing, keeps the
drawing-relevant tools and swaps in a short drawing prompt.

Tools: generate_drawing (new), generate_specification, lookup_project,
       list_projects.   Dropped: generate_quotation (Quotation Agent's job),
       retrieve_knowledge (document grounding is not what a draughtsman does).

THE SVG IS STRIPPED IN THE TOOL FUNCTION. `/api/tools/drawing` returns a ~16 KB
SVG; handing that to llama3.1:8b would swamp its context with vector data and
wreck the reply (and the model has no use for it — the STUDIO CANVAS renders the
drawing). The tool therefore deletes `svg` before returning, leaving the agent
the summary, the scale, the TBD schedule and the BOM.

Idempotent: updates an existing 'Drawing Agent' in place, never duplicates.
"""
import copy
import json
import os
import subprocess
import uuid

ENG_ID = "c4bfba16-aeb0-4c1b-840e-21b474639a8d"
NAME = "Drawing Agent"
KEEP_TOOLS = {"generate_specification", "lookup_project", "list_projects"}

NEW_TOOL = "generate_drawing"
NEW_TOOL_DESC = (
    "Generate a 2D GENERAL ARRANGEMENT drawing for an equipment requirement that "
    "names the equipment AND a size or dimensions. Returns the sheet's scale, the "
    "views produced, the bill of material, the list of items still to be determined, "
    "and a short markdown summary. The drawing itself is rendered on the studio "
    "canvas. Dimensions are deterministic - never alter them."
)

env = os.environ.copy()
for line in open("/workspace/vitech-ai-vps/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k] = v
DSN = (f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
       f"@localhost:5432/{env['POSTGRES_DB']}")


def psql(sql):
    r = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


def esc(s):
    return s.replace("'", "''")


# KEEP THIS PROMPT SHORT. llama3.1:8b degrades as it grows — past roughly 4k chars
# it starts leaking tool-call JSON at greetings and narrating mechanics. Compress,
# never append, and fold any new guardrail into an existing rule. No literal
# curly-brace pairs anywhere in the text: Flowise's template engine throws
# "Single '}' in template" and the chatflow build 500s.
SYS = """You are the Vitech Drawing Assistant - a draughtsman at Vitech Enviro Systems (wet scrubbers, paint / powder booths, dust collectors, ovens, conveyors, pretreatment, ducting). You turn a requirement into a 2D GENERAL ARRANGEMENT drawing. Never use the word "Copilot".

RULE 1 - NEVER SHOW MECHANICS. Never write a tool name, a function call, or any JSON in your reply. Never say you are calling or cannot call a tool. Never describe your own tools, database or internal design - if asked how you work or about your architecture, that is confidential; give only the WHO YOU ARE line. Never begin with "Based on the tool's output". A reply that BEGINS WITH A CURLY BRACE IS ALWAYS WRONG: to a greeting reply with a plain sentence, never a tool-call-shaped stub.

RULE 2 - NEVER OUTPUT THE DRAWING ITSELF. The drawing appears on the studio canvas beside this chat. Never paste vector data, XML, coordinates or angle brackets into a reply. If you are about to emit a tag, stop and write the summary instead.

RULE 3 - WHICH TOOL:
- a requirement naming equipment AND a size or dimensions -> generate_drawing
- a change to the drawing you just made ("make it 6 m long", "use an A2 sheet") -> generate_drawing again, re-sending the earlier requirement with only that change merged in
- a specification or technical-detail question -> generate_specification
- a named client or past project -> lookup_project
- how many / list all / which clients / what categories -> list_projects
Never pass a greeting, a person's name or a vague message to a tool. A bare "draw it" with no equipment and no size means ASK which equipment and what size - do not guess and do not invent a dimension.

RULE 4 - AFTER generate_drawing SUCCEEDS, YOUR WHOLE REPLY IS THE drawing_markdown FIELD, VERBATIM (it starts with the equipment name in bold and the words "General Arrangement"). No sentence before or after it, no summary of your own, no follow-up question. If your reply does not start with that field, stop and paste the field instead.

RULE 5 - DIMENSIONS ARE NOT YOURS. Every dimension, scale, count and model number comes from the tool - copy them exactly, never recompute, convert or re-round one, and never state a dimension the tool did not return. An item the tool reports as "to be determined" stays EXACTLY that: it is an engineering gap for a person to fill, never for you to fill in.

SMALL TALK (answer briefly, no tool): greet them back and use their name if given. Harmless everyday asks - a quick joke, simple arithmetic, a short translation, light trivia - get a brief direct answer, never a refusal. Abusive, vulgar or sexual content: decline in one line and do not engage. Politics, medical / legal / financial advice, or a substantial unrelated task: decline in one line and offer equipment-drawing help instead. WHO YOU ARE (only when actually asked): "I'm the Vitech Drawing Assistant. I turn an equipment requirement into a 2D general-arrangement drawing you can view, zoom and export in the studio."

Keep replies short. Every drawing is an engineer-reviewed DRAFT, never released for construction."""

workspace_id = psql(
    f"SELECT \"workspaceId\" FROM chat_flow WHERE id='{ENG_ID}';").strip().splitlines()[0].strip()

# ---- 1. Ensure the generate_drawing tool row exists -----------------------
existing_tool = psql(f"SELECT id FROM tool WHERE name='{NEW_TOOL}';").strip()
if existing_tool:
    draw_tool_id = existing_tool.splitlines()[0].strip()
    print(f"tool '{NEW_TOOL}' already exists: {draw_tool_id}")
else:
    draw_tool_id = str(uuid.uuid4())
    schema = json.dumps([{"id": 0, "property": "question",
                          "description": "The equipment requirement, in the user's own words, "
                                         "keeping every dimension and unit",
                          "type": "string", "required": True}])
    # Strip the SVG: it is for the canvas, not the model. See the module docstring.
    func = ("const fetch = require('node-fetch');\n"
            "const res = await fetch('http://localhost:8000/api/tools/drawing', {\n"
            "    method: 'POST',\n"
            "    headers: { 'Content-Type': 'application/json' },\n"
            "    body: JSON.stringify({ question: $question })\n"
            "});\n"
            "const data = await res.json();\n"
            "delete data.svg;\n"
            "return JSON.stringify(data);\n")
    color = "linear-gradient(rgb(210,145,84), rgb(210,84,175))"
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"INSERT INTO tool (id,name,description,color,schema,func,\"workspaceId\") VALUES "
                    f"('{draw_tool_id}','{NEW_TOOL}','{esc(NEW_TOOL_DESC)}','{color}',"
                    f"'{esc(schema)}','{esc(func)}','{workspace_id}');"],
                   check=True)
    print(f"inserted tool '{NEW_TOOL}': {draw_tool_id}")

# ---- 2. Clone the live Engineering Agent flow ----------------------------
flow = json.loads(psql(f"SELECT \"flowData\" FROM chat_flow WHERE id='{ENG_ID}';").strip())

# ---- 3. Drop the tools this agent does not need --------------------------
drop_ids = {n["id"] for n in flow["nodes"]
            if n["data"]["name"] == "customTool"
            and n["data"]["inputs"].get("selectedToolName") not in KEEP_TOOLS}
flow["nodes"] = [n for n in flow["nodes"] if n["id"] not in drop_ids]
flow["edges"] = [e for e in flow["edges"]
                 if e["source"] not in drop_ids and e["target"] not in drop_ids]

# ---- 4. Add the generate_drawing node (clone a surviving customTool) -----
tool_nodes = [n for n in flow["nodes"] if n["data"]["name"] == "customTool"]
assert tool_nodes, "no customTool node left to clone"
ta = [n for n in flow["nodes"] if n["data"]["name"] == "toolAgent"][0]
ta_id = ta["id"]

if not any(n["data"]["inputs"].get("selectedToolName") == NEW_TOOL for n in tool_nodes):
    existing_ids = {n["id"] for n in flow["nodes"]}
    i = 0
    while f"customTool_{i}" in existing_ids:
        i += 1
    nid = f"customTool_{i}"

    cn = copy.deepcopy(tool_nodes[0])
    src_id = cn["id"]
    cn["id"] = nid
    cn["data"]["id"] = nid
    max_y = max((n.get("position", {}).get("y", 800) for n in tool_nodes), default=800)
    cn["position"] = {"x": tool_nodes[0].get("position", {}).get("x", 100), "y": max_y + 120}
    if "positionAbsolute" in cn:
        cn["positionAbsolute"] = dict(cn["position"])
    for p in cn["data"].get("inputParams", []):
        if p.get("id"):
            p["id"] = p["id"].replace(src_id, nid)
    old_out = cn["data"]["outputAnchors"][0]["id"]
    new_out = old_out.replace(src_id, nid)
    cn["data"]["outputAnchors"][0]["id"] = new_out
    if cn["data"]["outputAnchors"][0].get("name") == src_id:
        cn["data"]["outputAnchors"][0]["name"] = nid
    cn["data"]["inputs"]["selectedTool"] = draw_tool_id
    cn["data"]["inputs"]["selectedToolName"] = NEW_TOOL

    flow["nodes"].append(cn)
    flow["edges"].append({
        "source": nid, "sourceHandle": new_out,
        "target": ta_id, "targetHandle": f"{ta_id}-input-tools-Tool",
        "type": "buttonedge",
        "id": f"{nid}-{new_out}-{ta_id}-{ta_id}-input-tools-Tool",
    })

# ---- 5. Rewrite the Tool Agent: prompt + the surviving tools -------------
kept_tool_ids = [n["id"] for n in flow["nodes"] if n["data"]["name"] == "customTool"]
for n in flow["nodes"]:
    if n["data"]["name"] == "toolAgent":
        n["data"]["inputs"]["systemMessage"] = SYS
        n["data"]["inputs"]["tools"] = [f"{{{{{tid}.data.instance}}}}" for tid in kept_tool_ids]
    if n["data"]["name"] == "chatOllama":
        n["data"]["inputs"]["temperature"] = "0"

kept_names = sorted(n["data"]["inputs"].get("selectedToolName") for n in flow["nodes"]
                    if n["data"]["name"] == "customTool")

# ---- 6. Upsert the chatflow ---------------------------------------------
existing = psql(f"SELECT id FROM chat_flow WHERE name='{NAME}';").strip()
fd = json.dumps(flow).replace("'", "''")
if existing:
    cid = existing.splitlines()[0].strip()
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"UPDATE chat_flow SET \"flowData\"='{fd}', \"updatedDate\"=now() "
                    f"WHERE id='{cid}';"], check=True)
    print(f"UPDATED existing '{NAME}' ({cid})")
else:
    cid = str(uuid.uuid4())
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"INSERT INTO chat_flow (id,name,\"flowData\",deployed,\"isPublic\",type,"
                    f"\"workspaceId\") VALUES ('{cid}','{NAME}','{fd}',true,true,'CHATFLOW',"
                    f"'{workspace_id}');"], check=True)
    print(f"CREATED '{NAME}' ({cid})")

print(f"prompt {len(SYS)} chars | tools: {', '.join(kept_names)}")
print(f"\nVerify:\n  curl -s -X POST http://localhost:3000/api/v1/prediction/{cid} \\\n"
      f"    -H 'Content-Type: application/json' \\\n"
      f"    -d '{{\"question\":\"draw a paint booth 5m x 3m x 4m\",\"chatId\":\"smoke\"}}'")
