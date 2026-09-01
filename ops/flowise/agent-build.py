#!/usr/bin/env python3
"""Build the Vitech Engineering Agent chatflow programmatically and insert into
Flowise's Postgres (chat_flow + tool tables). Bypasses the buggy OpenAPI Toolkit UI."""
import json, uuid, copy, subprocess, os

MP = "/opt/flowise-app/node_modules/flowise/marketplaces/chatflows"
WORKSPACE_ID = "6451d383-e17f-4427-9e56-4f87ec05f084"  # Default Workspace

def load(name): return json.load(open(f"{MP}/{name}.json"))
def node_of(tpl, nm): return copy.deepcopy([n for n in tpl["nodes"] if n["data"]["name"] == nm][0])

# ---- 1. The 4 backend tools ----
TOOLS = [
    ("generate_specification", "Turn a customer requirement into a deterministic engineering specification for Vitech industrial air-pollution equipment (wet scrubbers, paint booths, dust collectors, ovens). Returns structured spec with authoritative numbers.", "spec"),
    ("generate_quotation",      "Produce a deterministic budgetary quotation (price, range, confidence) for Vitech equipment from historical offers. Numbers are authoritative.", "quote"),
    ("lookup_project",          "Look up the exact extracted data for a named client or offer reference from Vitech's historical records.", "lookup"),
    ("retrieve_knowledge",      "Search the Vitech engineering knowledge base (past offers, specs, standards) for grounding context. Returns relevant document chunks.", "retrieve"),
    ("list_projects",           "Enumerate ALL of Vitech's stored historical offers at once - use for 'how many projects/offers', 'list all clients', 'which categories', 'what have we quoted'. Returns exact counts, the full client list, category counts, and every project. Numbers are authoritative.", "list"),
]

def tool_func(endpoint):
    return (
        "const fetch = require('node-fetch');\n"
        f"const res = await fetch('http://localhost:8000/api/tools/{endpoint}', {{\n"
        "    method: 'POST',\n"
        "    headers: { 'Content-Type': 'application/json' },\n"
        "    body: JSON.stringify({ question: $question })\n"
        "});\n"
        "return JSON.stringify(await res.json());\n"
    )

tool_ids = {}
tool_sql = []
for name, desc, ep in TOOLS:
    tid = str(uuid.uuid4())
    tool_ids[name] = tid
    schema = json.dumps([{"id": 0, "property": "question", "description": "The customer requirement or query, in natural language", "type": "string", "required": True}])
    func = tool_func(ep)
    color = "linear-gradient(rgb(84,145,210), rgb(84,210,175))"
    def esc(s): return s.replace("'", "''")
    tool_sql.append(
        f"INSERT INTO tool (id,name,description,color,schema,func,\"workspaceId\") VALUES "
        f"('{tid}','{name}','{esc(desc)}','{color}','{esc(schema)}','{esc(func)}','{WORKSPACE_ID}');"
    )

# ---- 2. Node blocks ----
ta_tpl = load("Tool Agent")
chatollama = node_of(load("Local QnA"), "chatOllama")
customtool = node_of(load("OpenAI Assistant"), "customTool")
toolagent  = node_of(ta_tpl, "toolAgent")
buffermem  = node_of(ta_tpl, "bufferMemory")

# ---- 3. Configure ChatOllama ----
chatollama["id"] = "chatOllama_0"; chatollama["data"]["id"] = "chatOllama_0"
chatollama["position"] = {"x": 100, "y": 500}
chatollama["data"]["inputs"]["baseUrl"] = "http://localhost:11434"
chatollama["data"]["inputs"]["modelName"] = "llama3.1:8b"
chatollama["data"]["inputs"]["temperature"] = "0.2"
CHATOLLAMA_OUT = chatollama["data"]["outputAnchors"][0]["id"]

# ---- 4. Buffer memory ----
buffermem["position"] = {"x": 100, "y": 100}
BUFMEM_ID = buffermem["id"]
BUFMEM_OUT = buffermem["data"]["outputAnchors"][0]["id"]

# ---- 5. Four custom tool nodes (clone + rewrite ids) ----
tool_nodes = []
tool_refs = []
tool_edges_src = []
for i, (name, desc, ep) in enumerate(TOOLS):
    nid = f"customTool_{i}"
    cn = copy.deepcopy(customtool)
    cn["id"] = nid; cn["data"]["id"] = nid
    cn["position"] = {"x": 100, "y": 800 + i * 120}
    # rewrite id-bearing anchor/param ids
    for p in cn["data"].get("inputParams", []):
        if p.get("id"): p["id"] = p["id"].replace("customTool_0", nid)
    old_out = cn["data"]["outputAnchors"][0]["id"]
    new_out = old_out.replace("customTool_0", nid)
    cn["data"]["outputAnchors"][0]["id"] = new_out
    if cn["data"]["outputAnchors"][0].get("name") == "customTool_0":
        cn["data"]["outputAnchors"][0]["name"] = nid
    cn["data"]["inputs"]["selectedTool"] = tool_ids[name]
    # display the tool name on the node
    cn["data"]["inputs"]["selectedToolName"] = name
    tool_nodes.append(cn)
    tool_refs.append(f"{{{{{nid}.data.instance}}}}")
    tool_edges_src.append((nid, new_out))

# ---- 6. Configure Tool Agent ----
toolagent["id"] = "toolAgent_0"; toolagent["data"]["id"] = "toolAgent_0"
toolagent["position"] = {"x": 700, "y": 400}
SYS = ("You are a senior process/mechanical engineer at Vitech Enviro Systems. You turn a "
       "customer requirement into a technical specification and budgetary quotation for industrial "
       "air-pollution-control equipment (wet scrubbers, paint/powder booths, dust collectors, ovens).\n\n"
       "Workflow every time:\n"
       "1. Identify the equipment type from the requirement.\n"
       "2. Call retrieve_knowledge for similar historical projects and standards.\n"
       "3. Call generate_specification and/or generate_quotation. Their returned numbers are AUTHORITATIVE and DETERMINISTIC.\n"
       "4. Write the answer, combining retrieved engineering knowledge with the tool's calculated values.\n\n"
       "Hard rules:\n"
       "- NEVER invent or alter a dimension, capacity, count, price, or material. Every number MUST come from a tool result. "
       "If a value is not in a tool result, it is 'To Be Determined'.\n"
       "- If a tool reports missing_inputs, ASK the customer for exactly those inputs.\n"
       "- Present every output as an engineer-reviewed DRAFT for human approval.\n"
       "- Never use the word 'Copilot'.")
toolagent["data"]["inputs"]["model"] = "{{chatOllama_0.data.instance}}"
toolagent["data"]["inputs"]["memory"] = f"{{{{{BUFMEM_ID}.data.instance}}}}"
toolagent["data"]["inputs"]["tools"] = tool_refs
toolagent["data"]["inputs"]["systemMessage"] = SYS

# ---- 7. Edges ----
def edge(src, srch, tgt, tgth):
    return {"source": src, "sourceHandle": srch, "target": tgt, "targetHandle": tgth,
            "type": "buttonedge", "id": f"{src}-{srch}-{tgt}-{tgth}"}

edges = [
    edge("chatOllama_0", CHATOLLAMA_OUT, "toolAgent_0", "toolAgent_0-input-model-BaseChatModel"),
    edge(BUFMEM_ID, BUFMEM_OUT, "toolAgent_0", "toolAgent_0-input-memory-BaseChatMemory"),
]
for nid, out in tool_edges_src:
    edges.append(edge(nid, out, "toolAgent_0", "toolAgent_0-input-tools-Tool"))

# ---- 8. Assemble ----
nodes = [chatollama, buffermem, toolagent] + tool_nodes
flowdata = {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.8}}

CHATFLOW_ID = str(uuid.uuid4())
fd = json.dumps(flowdata).replace("'", "''")
chatflow_sql = (
    f"INSERT INTO chat_flow (id,name,\"flowData\",deployed,\"isPublic\",type,\"workspaceId\") VALUES "
    f"('{CHATFLOW_ID}','Engineering Agent','{fd}',true,true,'CHATFLOW','{WORKSPACE_ID}');"
)

# ---- 9. Emit SQL ----
sql = "BEGIN;\n" + "\n".join(tool_sql) + "\n" + chatflow_sql + "\nCOMMIT;\n"
open("/tmp/claude-0/-workspace-vitech-ai-vps/2fb3c1af-40d1-49c9-8b60-da9ebc1093e2/scratchpad/insert_agent.sql", "w").write(sql)
print("CHATFLOW_ID=" + CHATFLOW_ID)
print("tools:", ", ".join(f"{n}={i[:8]}" for n, i in tool_ids.items()))
print("nodes:", [n["id"] for n in nodes])
print("edges:", len(edges))
