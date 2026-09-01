#!/usr/bin/env python3
"""Add a Custom Tool to a LIVE Flowise chatflow — generalised, idempotent.

`agent-add-list-tool.py` did this for one hard-coded tool. This is the same
proven mechanism (clone a working customTool node from the flow itself, so the
node shape always matches THIS Flowise install) with the tool, the endpoint, the
schema and the target chatflow as arguments.

    python3 ops/flowise/add-tool.py --tool check_voc_safety \
        --chatflow "Engineering Agent" --endpoint voc --schema voc \
        --description "..."

THE SERVICE KEY IS NEVER WRITTEN HERE. It is read out of an existing tool row,
so this script carries no secret and can live in git — the same reason
`set-service-key.sh` exists. If no tool row has a key yet, run that first.

Idempotent twice over: an existing tool row of the same name is reused, and a
chatflow that already references it is left alone.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import uuid

REPO = "/workspace/vitech-ai-vps"

# Input schemas by name. A tool whose inputs are NUMBERS gets them as typed
# properties rather than one prose string: axis and unit assignment is exactly
# what an 8B model gets wrong, and the endpoint would then have to re-parse
# prose it had already been given structured.
SCHEMAS = {
    "question": [{"id": 0, "property": "question", "type": "string", "required": True,
                  "description": "The user's question, in natural language"}],
    "voc": [
        # NOT required: Flowise validates the schema before calling us, and a
        # model that fills every typed input but omits the prose question would
        # otherwise be rejected with "input did not match expected schema".
        {"id": 0, "property": "question", "type": "string", "required": False,
         "description": "The user's question, verbatim"},
        {"id": 1, "property": "paint_consumption_l_hr", "type": "number", "required": False,
         "description": "Paint consumption in litres per hour, if the user stated it"},
        {"id": 2, "property": "voc_percent", "type": "number", "required": False,
         "description": "VOC content of the paint as a percentage, if stated"},
        {"id": 3, "property": "density_kg_l", "type": "number", "required": False,
         "description": "Paint density in kg per litre, if stated"},
        {"id": 4, "property": "airflow_cmh", "type": "number", "required": False,
         "description": "Booth exhaust airflow in m3/h, if stated"},
    ],
    "heat_load": [
        # NOT required: Flowise validates the schema before calling us, and a
        # model that fills every typed input but omits the prose question would
        # otherwise be rejected with "input did not match expected schema".
        {"id": 0, "property": "question", "type": "string", "required": False,
         "description": "The user's question, verbatim"},
        {"id": 1, "property": "equipment", "type": "string", "required": True,
         "description": "One of: tank, dry_off_oven, curing_oven"},
        {"id": 2, "property": "length", "type": "number", "required": True,
         "description": "Length — mm for a tank, metres for an oven"},
        {"id": 3, "property": "width", "type": "number", "required": True,
         "description": "Width — mm for a tank, metres for an oven"},
        {"id": 4, "property": "height", "type": "number", "required": True,
         "description": "Height — mm for a tank, metres for an oven"},
        {"id": 5, "property": "temp_from_c", "type": "number", "required": True,
         "description": "Starting temperature in Celsius"},
        {"id": 6, "property": "temp_to_c", "type": "number", "required": True,
         "description": "Final temperature in Celsius"},
        {"id": 7, "property": "tank_steel_mass_kg", "type": "number", "required": False,
         "description": "Tank only: mass of the tank steel in kg"},
        {"id": 8, "property": "job_mass_kg", "type": "number", "required": False,
         "description": "Oven only: mass of one job with its basket or jig, kg"},
        {"id": 9, "property": "jobs_per_hour", "type": "number", "required": False,
         "description": "Dry-off oven only: number of jobs per hour"},
        {"id": 10, "property": "conveyor_mass_kg", "type": "number", "required": False,
         "description": "Curing oven only: conveyor mass in kg"},
        {"id": 11, "property": "insulation_thickness_mm", "type": "number", "required": False,
         "description": "Curing oven only: insulation thickness, 50 / 100 / 150 mm"},
    ],
}


def dsn() -> str:
    env = {}
    with open(f"{REPO}/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return (f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
            f"@localhost:5432/{env['POSTGRES_DB']}")


def psql(sql: str) -> str:
    r = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


def run(sql: str) -> None:
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c", sql], check=True)


def esc(s: str) -> str:
    return s.replace("'", "''")


def service_key() -> str:
    """Lift the service key out of a tool row that already carries one."""
    for row in psql("SELECT func FROM tool;").split("\n"):
        m = re.search(r"'X-API-Key':\s*'([^']+)'", row)
        if m:
            return m.group(1)
    raise SystemExit("no tool row carries an X-API-Key — run "
                     "ops/flowise/set-service-key.sh first")


def chatflow_id(name_or_id: str) -> str:
    if re.fullmatch(r"[0-9a-f-]{36}", name_or_id):
        return name_or_id
    out = psql(f"SELECT id FROM chat_flow WHERE name='{esc(name_or_id)}';").strip()
    if not out:
        raise SystemExit(f"no chatflow named {name_or_id!r}")
    return out.splitlines()[0].strip()


def ensure_tool(name: str, desc: str, endpoint: str, schema_key: str) -> str:
    existing = psql(f"SELECT id FROM tool WHERE name='{esc(name)}';").strip()
    if existing:
        print(f"  tool '{name}' already exists")
        return existing.splitlines()[0].strip()

    tool_id = str(uuid.uuid4())
    workspace = psql("SELECT \"workspaceId\" FROM tool LIMIT 1;").strip().splitlines()[0].strip()
    schema = SCHEMAS[schema_key]
    # EVERY optional property must be read through a `typeof` guard. Flowise
    # substitutes `$prop` only for properties the model actually supplied, so a
    # bare `$question` on a call that omitted it throws
    # "ReferenceError: $question is not defined" INSIDE the sandbox - the agent
    # then sees an empty tool result and invents an answer, which is the worst
    # possible failure. Cost a debugging round; do not "simplify" it away.
    body = ", ".join(
        (f"{p['property']}: ${p['property']}" if p.get("required")
         else f"{p['property']}: (typeof ${p['property']} !== 'undefined' ? ${p['property']} : null)")
        for p in schema)
    func = ("const fetch = require('node-fetch');\n"
            f"const res = await fetch('http://localhost:8000/api/tools/{endpoint}', {{\n"
            "    method: 'POST',\n"
            "    headers: { 'Content-Type': 'application/json', "
            f"'X-API-Key': '{service_key()}' }},\n"
            f"    body: JSON.stringify({{ {body} }})\n"
            "});\n"
            "return JSON.stringify(await res.json());\n")
    run("INSERT INTO tool (id,name,description,color,schema,func,\"workspaceId\") VALUES "
        f"('{tool_id}','{esc(name)}','{esc(desc)}',"
        "'linear-gradient(rgb(84,145,210), rgb(84,210,175))',"
        f"'{esc(json.dumps(schema))}','{esc(func)}','{workspace}');")
    print(f"  inserted tool '{name}': {tool_id}")
    return tool_id


def wire(flow_id: str, tool_id: str, tool_name: str) -> bool:
    flow = json.loads(psql(f"SELECT \"flowData\" FROM chat_flow WHERE id='{flow_id}';").strip())
    if any(n["data"].get("inputs", {}).get("selectedTool") == tool_id for n in flow["nodes"]):
        print(f"  chatflow already references {tool_name}")
        return False

    tool_nodes = [n for n in flow["nodes"] if n["data"]["name"] == "customTool"]
    if not tool_nodes:
        raise SystemExit("no customTool node to clone in this chatflow")
    ids = {n["id"] for n in flow["nodes"]}
    i = 0
    while f"customTool_{i}" in ids:
        i += 1
    nid = f"customTool_{i}"

    node = copy.deepcopy(tool_nodes[0])
    src = node["id"]
    node["id"] = node["data"]["id"] = nid
    max_y = max((n.get("position", {}).get("y", 800) for n in tool_nodes), default=800)
    node["position"] = {"x": tool_nodes[0].get("position", {}).get("x", 100), "y": max_y + 120}
    if "positionAbsolute" in node:
        node["positionAbsolute"] = dict(node["position"])
    for p in node["data"].get("inputParams", []):
        if p.get("id"):
            p["id"] = p["id"].replace(src, nid)
    out_old = node["data"]["outputAnchors"][0]["id"]
    out_new = out_old.replace(src, nid)
    node["data"]["outputAnchors"][0]["id"] = out_new
    if node["data"]["outputAnchors"][0].get("name") == src:
        node["data"]["outputAnchors"][0]["name"] = nid
    node["data"]["inputs"]["selectedTool"] = tool_id
    node["data"]["inputs"]["selectedToolName"] = tool_name

    agent = [n for n in flow["nodes"] if n["data"]["name"] == "toolAgent"][0]
    ref = f"{{{{{nid}.data.instance}}}}"
    tools = agent["data"]["inputs"].get("tools") or []
    if ref not in tools:
        tools.append(ref)
    agent["data"]["inputs"]["tools"] = tools

    flow["nodes"].append(node)
    flow["edges"].append({
        "source": nid, "sourceHandle": out_new,
        "target": agent["id"], "targetHandle": f"{agent['id']}-input-tools-Tool",
        "type": "buttonedge",
        "id": f"{nid}-{out_new}-{agent['id']}-{agent['id']}-input-tools-Tool",
    })
    run(f"UPDATE chat_flow SET \"flowData\"='{json.dumps(flow).replace(chr(39), chr(39)*2)}', "
        f"\"updatedDate\"=now() WHERE id='{flow_id}';")
    print(f"  wired {nid} ({tool_name}); the agent now has {len(tools)} tools")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", required=True, help="operation_id / tool name")
    ap.add_argument("--chatflow", required=True, help="chatflow name or id")
    ap.add_argument("--endpoint", required=True, help="path under /api/tools/")
    ap.add_argument("--description", required=True)
    ap.add_argument("--schema", default="question", choices=sorted(SCHEMAS))
    a = ap.parse_args()

    DSN = dsn()
    print(f"{a.tool} -> {a.chatflow}")
    tid = ensure_tool(a.tool, a.description, a.endpoint, a.schema)
    wire(chatflow_id(a.chatflow), tid, a.tool)
