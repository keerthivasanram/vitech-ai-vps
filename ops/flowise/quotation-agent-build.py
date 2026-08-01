#!/usr/bin/env python3
"""Build the Vitech QUOTATION AGENT as a second Flowise chatflow.

Same architecture as the Engineering Agent (ChatOllama llama3.1:8b + BufferMemory
+ Tool Agent), but specialised for budgetary quotations. It clones the LIVE
Engineering Agent's flow (guarantees correctly-shaped nodes for this install),
keeps only the quotation-relevant tools, and swaps in a quotation system prompt.

Tools kept (reusing the SAME shared tool rows — no new tool rows created):
  generate_quotation, lookup_project, retrieve_knowledge, list_projects
Dropped: generate_specification (that's the Engineering Agent's job).

Idempotent: if a chatflow named 'Quotation Agent' already exists it is UPDATED
in place (same id), never duplicated.
"""
import json, uuid, copy, subprocess, os

ENG_ID = "c4bfba16-aeb0-4c1b-840e-21b474639a8d"
NAME = "Quotation Agent"
KEEP_TOOLS = {"generate_quotation", "lookup_project", "retrieve_knowledge", "list_projects"}

env = os.environ.copy()
for line in open("/workspace/vitech-ai-vps/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k] = v
DSN = f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@localhost:5432/{env['POSTGRES_DB']}"


def psql(sql):
    r = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


# NOTE: keep this prompt SHORT. llama3.1:8b degrades when it grows (>~4k chars it
# starts leaking tool-call JSON at greetings and narrating mechanics). Compress; do
# not append. No literal { } pairs in the text (Flowise's template build 500s on them).
SYS = """You are the Vitech Quotation Assistant - a sales / applications engineer at Vitech Enviro Systems (wet scrubbers, paint / powder booths, dust collectors, ovens, conveyors, pretreatment, ducting). You turn a requirement into a BUDGETARY QUOTATION grounded in Vitech's historical offers. Never use the word "Copilot".

RULE 1 - NEVER SHOW MECHANICS. Never write a tool name, a function call, or any JSON in your reply. Never say you are calling or cannot call a tool. Never describe your own tools, database or internal design either - if asked how you work or your architecture, that is confidential; give only the WHO YOU ARE line. Never begin with "Based on the tool's output". Use a tool silently and state the result as your own finding in plain English, or simply answer. A reply that BEGINS WITH A CURLY BRACE IS ALWAYS WRONG: to a greeting, reply with a plain sentence (e.g. "Hello! I'm the Vitech Quotation Assistant..."), never a tool-call-shaped stub such as a greet call with empty parameters.

RULE 2 - PRICES COME FROM TOOLS, NEVER YOU. Every price, range, dimension, capacity and quantity comes from a tool result - never invent or recompute one. Print the tool's ready-made "..._display" strings VERBATIM (price_display, price_range_display, unit_price_display, price_schedule_display); never regroup digits.

RULE 3 - WHICH TOOL:
- A REQUIREMENT the user states - equipment plus a size, capacity, dimension or quantity -> generate_quotation. This still holds when they call it a specification, spec, datasheet or requirement, and when they name a client. Stating a requirement is NEVER a lookup.
- lookup_project ONLY when they ask what Vitech quoted BEFORE for a client or offer reference they name.
- how many / list / which clients / compare / highest / lowest / top N by price -> list_projects
- what our records or standards say -> retrieve_knowledge
Never use a tool for greetings, "who are you", a name, thanks or chit-chat.

RULE 4 - AFTER generate_quotation SUCCEEDS, YOUR WHOLE REPLY IS THE quotation_markdown FIELD, VERBATIM (it starts with "### VITECH ENVIRO SYSTEMS PVT. LTD."). No sentence before or after, no summary, no follow-up question. If your reply does not start with "###", stop and paste that field. The customer quotation never shows margin, cost, market band or confidence.

RULE 4b - AFTER lookup_project SUCCEEDS, YOUR WHOLE REPLY IS THE lookup_markdown FIELD, VERBATIM (it starts with "### Historical Project"). No sentence before or after. NEVER write the Vitech company name as a heading yourself and never re-format an archive record to look like a quotation - a past offer is not a new quote.

RULE 5 - PRICING BASIS, ONLY WHEN ASKED. If asked WHY the price, how it was fixed, the margin, the cost break-up, or how it compares to the market or competitors, re-run generate_quotation and present the pricing_basis_markdown field VERBATIM instead of the customer quote (pricing_rationale is its one-line summary). Report only what those fields contain - never invent a margin, cost, rate or percentage, and never show confidence or regression internals.

RULE 6 - TECHNICAL QUESTIONS ARE NOT YOURS. For an engineering question (how or why something works, design, sizing, materials, standards, formulas, face velocity, what a value "should be", troubleshooting, technology choice) do NOT answer and do NOT call a tool - reply in ONE sentence that the Engineering Agent handles those. But a stated REQUIREMENT is not a technical question - RULE 3 wins, quote it. You handle prices, quotations, historical offers and commercial terms.

SMALL TALK (answer warmly, 1-2 lines, no tool): greet back, use their name if given, and answer harmless everyday chat naturally - "how's it going", a quick joke, simple arithmetic (e.g. "12 + 30"), a short translation, light trivia - a direct answer, never a refusal. Abusive, vulgar or sexual/adult content: decline in one line, do not engage. WHO YOU ARE (only if actually asked): "I'm the Vitech Quotation Assistant - I turn a requirement into a budgetary quotation from Vitech's historical offers, and can look up and compare past quotations."

QUOTATION WORK:
- CARRY THE REQUIREMENT FORWARD. A bare "generate quotation" / "quote it" / "proceed" AFTER a requirement was already stated earlier in this chat means quote THAT requirement - re-send it to the tool in the user's original words. Only ask what to quote when no requirement has been stated anywhere in this chat; never invent one or add a number they did not state.
- Pass the requirement in the user's own words, keeping every number, unit and quantity. Then RULE 4.
- REVISE / CHANGE QTY or SIZE: re-send the earlier requirement in this chat with only their change merged in, quote again, RULE 4.
- COMPARE: quote or look up each; give each Total (its price_display string) and say which is higher - do not compute differences.
- HIGHEST / LOWEST / RANK: use list_projects' ready fields (highest_answer, top_by_price); never sort yourself.
- You know no client, count or price from memory - call a tool first; never output a placeholder client or an invented figure.
- CLIENT-SPECIFIC: if they state a requirement for a named client, QUOTE it; use lookup_project only for that client's PAST offers. If a tool returns need_requirement or missing_inputs, ask for exactly those.

Every quotation is an engineer-reviewed DRAFT."""

# ---- clone the live Engineering Agent flow ----
flow = json.loads(psql(f"SELECT \"flowData\" FROM chat_flow WHERE id='{ENG_ID}';").strip())
workspace_id = psql(f"SELECT \"workspaceId\" FROM chat_flow WHERE id='{ENG_ID}';").strip().splitlines()[0].strip()
flow = copy.deepcopy(flow)

# keep only the quotation tool nodes
drop_ids = {n["id"] for n in flow["nodes"]
            if n["data"]["name"] == "customTool"
            and n["data"]["inputs"].get("selectedToolName") not in KEEP_TOOLS}
flow["nodes"] = [n for n in flow["nodes"] if n["id"] not in drop_ids]
flow["edges"] = [e for e in flow["edges"]
                 if e["source"] not in drop_ids and e["target"] not in drop_ids]

# ---- swap BufferMemory -> RedisBackedChatMemory for PERSISTENT session memory ----
# RedisBackedChatMemory is a BaseChatMemory (Tool-Agent compatible, unlike AgentMemory)
# and its connect-credential is OPTIONAL — with none set it defaults to localhost:6379,
# which is exactly the Redis the pod already runs. This makes a chat's memory survive a
# Flowise restart (BufferMemory is in-process only). Session is keyed on the request chatId.
def _to_redis_memory(flow):
    bm = next((n for n in flow["nodes"] if n["data"]["name"] == "bufferMemory"), None)
    if not bm:
        return                              # already redis / nothing to convert
    nid = "redisBackedChatMemory_0"
    out_anchor = (f"{nid}-output-RedisBackedChatMemory-"
                  f"RedisBackedChatMemory|BaseChatMemory|BaseMemory")
    d = bm["data"]
    d["id"] = nid
    d["label"] = "Redis-Backed Chat Memory"
    d["name"] = "RedisBackedChatMemory"
    d["type"] = "RedisBackedChatMemory"
    d["version"] = 2
    d["description"] = "Stores the conversation in the Redis server (persists across restarts)"
    d["baseClasses"] = ["RedisBackedChatMemory", "BaseChatMemory", "BaseMemory"]
    d["credential"] = ""                    # optional — no credential -> localhost:6379
    d["inputs"] = {"sessionId": "", "memoryKey": "chat_history"}
    d["inputParams"] = [
        {"label": "Connect Credential", "name": "credential", "type": "credential",
         "optional": True, "credentialNames": ["redisCacheApi", "redisCacheUrlApi"],
         "id": f"{nid}-input-credential-credential"},
        {"label": "Session Id", "name": "sessionId", "type": "string", "default": "",
         "additionalParams": True, "optional": True, "id": f"{nid}-input-sessionId-string"},
        {"label": "Session Timeouts", "name": "sessionTTL", "type": "number",
         "additionalParams": True, "optional": True, "id": f"{nid}-input-sessionTTL-number"},
        {"label": "Memory Key", "name": "memoryKey", "type": "string", "default": "chat_history",
         "additionalParams": True, "id": f"{nid}-input-memoryKey-string"},
        {"label": "Window Size", "name": "windowSize", "type": "number",
         "additionalParams": True, "optional": True, "id": f"{nid}-input-windowSize-number"},
    ]
    d["outputAnchors"] = [{"id": out_anchor, "name": "RedisBackedChatMemory",
                           "label": "RedisBackedChatMemory",
                           "type": "RedisBackedChatMemory | BaseChatMemory | BaseMemory"}]
    old_id = bm["id"]
    bm["id"] = nid
    for e in flow["edges"]:                  # repoint the memory -> agent edge
        if e["source"] == old_id:
            e["source"] = nid
            e["sourceHandle"] = out_anchor
        if e.get("data") and isinstance(e["data"], dict):
            pass
    # fix edge id string if it embeds the old node id
    for e in flow["edges"]:
        if isinstance(e.get("id"), str) and old_id in e["id"]:
            e["id"] = e["id"].replace(old_id, nid)


# NOTE: RedisBackedChatMemory (cross-restart persistence) was attempted here but a
# programmatically-built node instance made the Tool Agent throw
# "memory.getChatMessages is not a function" at prediction time (Flowise fell back to a
# stub instead of the real class). BufferMemory already gives correct per-session memory
# (keyed on the request chatId) — it is just in-process, so it resets on a Flowise restart.
# To make it durable, add a "Redis-Backed Chat Memory" node in the Flowise UI (its
# connect-credential is optional -> localhost:6379) and connect it to the Tool Agent's
# memory input; the UI wires the node instance correctly. Keeping BufferMemory for now.
# _to_redis_memory(flow)   # <- intentionally NOT called

# rewrite the tool agent: prompt + tools list (only the kept nodes)
kept_tool_ids = [n["id"] for n in flow["nodes"] if n["data"]["name"] == "customTool"]
for n in flow["nodes"]:
    if n["data"]["name"] == "toolAgent":
        n["data"]["inputs"]["systemMessage"] = SYS
        n["data"]["inputs"]["tools"] = [f"{{{{{tid}.data.instance}}}}" for tid in kept_tool_ids]
    if n["data"]["name"] == "chatOllama":
        n["data"]["inputs"]["temperature"] = "0"

kept_names = sorted(n["data"]["inputs"].get("selectedToolName") for n in flow["nodes"]
                    if n["data"]["name"] == "customTool")

# ---- upsert the chatflow ----
existing = psql(f"SELECT id FROM chat_flow WHERE name='{NAME}';").strip()
fd = json.dumps(flow).replace("'", "''")
if existing:
    cid = existing.splitlines()[0].strip()
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"UPDATE chat_flow SET \"flowData\"='{fd}', \"updatedDate\"=now() WHERE id='{cid}';"],
                   check=True)
    print(f"UPDATED existing '{NAME}' ({cid})")
else:
    cid = str(uuid.uuid4())
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    f"INSERT INTO chat_flow (id,name,\"flowData\",deployed,\"isPublic\",type,\"workspaceId\") "
                    f"VALUES ('{cid}','{NAME}','{fd}',true,true,'CHATFLOW','{workspace_id}');"],
                   check=True)
    print(f"CREATED '{NAME}' ({cid})")

print("tools:", ", ".join(kept_names))
print("QUOTATION_AGENT_ID=" + cid)
