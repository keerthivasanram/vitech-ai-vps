#!/usr/bin/env python3
"""Add the 5th Custom Tool — list_projects — to the LIVE Engineering Agent.

The original 4 tools (agent-build.py) are point lookups/computations; none can
answer "how many / list all / which clients / what categories". This adds a
customTool node wired to POST http://localhost:8000/api/tools/list.

Idempotent: skips the tool insert if a tool named 'list_projects' already
exists, and skips the node/edge if the chatflow already references it.
"""
import json, uuid, copy, subprocess, os

CHATFLOW_ID = "c4bfba16-aeb0-4c1b-840e-21b474639a8d"
TOOL_NAME = "list_projects"
TOOL_DESC = ("Enumerate ALL of Vitech's stored historical offers at once — use for "
             "'how many projects/offers', 'list all clients', 'which categories', "
             "'what have we quoted'. Returns exact counts, the full client list, "
             "category counts, and every project. Numbers are authoritative.")
ENDPOINT = "list"  # -> http://localhost:8000/api/tools/list

env = os.environ.copy()
for line in open("/workspace/vitech-ai-vps/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k] = v
DSN = f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@localhost:5432/{env['POSTGRES_DB']}"


def psql(sql, capture=True):
    r = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


def esc(s):
    return s.replace("'", "''")


# ---- 1. Ensure the tool row exists (reuse if already present) ----
existing = psql(f"SELECT id FROM tool WHERE name='{TOOL_NAME}';").strip()
if existing:
    tool_id = existing.splitlines()[0].strip()
    print(f"tool '{TOOL_NAME}' already exists: {tool_id}")
else:
    tool_id = str(uuid.uuid4())
    workspace_id = psql(
        f"SELECT \"workspaceId\" FROM chat_flow WHERE id='{CHATFLOW_ID}';").strip().splitlines()[0].strip()
    schema = json.dumps([{"id": 0, "property": "question",
                          "description": "The user's question, in natural language",
                          "type": "string", "required": True}])
    func = ("const fetch = require('node-fetch');\n"
            f"const res = await fetch('http://localhost:8000/api/tools/{ENDPOINT}', {{\n"
            "    method: 'POST',\n"
            "    headers: { 'Content-Type': 'application/json' },\n"
            "    body: JSON.stringify({ question: $question })\n"
            "});\n"
            "return JSON.stringify(await res.json());\n")
    color = "linear-gradient(rgb(84,145,210), rgb(84,210,175))"
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"INSERT INTO tool (id,name,description,color,schema,func,\"workspaceId\") VALUES "
                    f"('{tool_id}','{TOOL_NAME}','{esc(TOOL_DESC)}','{color}',"
                    f"'{esc(schema)}','{esc(func)}','{workspace_id}');"],
                   check=True)
    print(f"inserted tool '{TOOL_NAME}': {tool_id}")

# ---- 2. Load live flow ----
flow = json.loads(psql(f"SELECT \"flowData\" FROM chat_flow WHERE id='{CHATFLOW_ID}';").strip())

# already wired?
if any(n["data"].get("inputs", {}).get("selectedTool") == tool_id for n in flow["nodes"]):
    print("chatflow already references list_projects — nothing to do.")
    raise SystemExit(0)

# ---- 3. Clone an existing customTool node from the live flow ----
tool_nodes = [n for n in flow["nodes"] if n["data"]["name"] == "customTool"]
assert tool_nodes, "no customTool node to clone"
existing_ids = {n["id"] for n in flow["nodes"]}
i = 0
while f"customTool_{i}" in existing_ids:
    i += 1
nid = f"customTool_{i}"

cn = copy.deepcopy(tool_nodes[0])
src_id = cn["id"]
cn["id"] = nid
cn["data"]["id"] = nid
# shift position below the last tool node so it doesn't overlap
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
cn["data"]["inputs"]["selectedTool"] = tool_id
cn["data"]["inputs"]["selectedToolName"] = TOOL_NAME

# ---- 4. Wire into the Tool Agent (edge + tools list) ----
ta = [n for n in flow["nodes"] if n["data"]["name"] == "toolAgent"][0]
ta_id = ta["id"]
tref = f"{{{{{nid}.data.instance}}}}"
tools = ta["data"]["inputs"].get("tools") or []
if tref not in tools:
    tools.append(tref)
ta["data"]["inputs"]["tools"] = tools

flow["nodes"].append(cn)
flow["edges"].append({
    "source": nid, "sourceHandle": new_out,
    "target": ta_id, "targetHandle": f"{ta_id}-input-tools-Tool",
    "type": "buttonedge",
    "id": f"{nid}-{new_out}-{ta_id}-{ta_id}-input-tools-Tool",
})

# ---- 5. Persist ----
new_fd = json.dumps(flow).replace("'", "''")
subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                f"UPDATE chat_flow SET \"flowData\"='{new_fd}', \"updatedDate\"=now() "
                f"WHERE id='{CHATFLOW_ID}';"],
               check=True)
print(f"wired {nid} (list_projects) into {ta_id}; tools now: {len(tools)}")
