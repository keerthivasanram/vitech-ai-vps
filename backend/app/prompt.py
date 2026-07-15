"""Prompt builder + deterministic fallback.

Branches on intent: specification/quotation requests get a structured technical
specification in the client's GIVEN DATA -> TECHNICAL DETAILS format, generated
by adapting historical offers (case-based) and refined by engineering rules;
concept/comparison/search questions get a natural answer from the documents.
The LLM explains and formats; it does not invent values.
"""
import json
import re
from typing import Any

from . import config
from .knowledge import directional
from .ledger import provenance_summary

SPEC_SYSTEM = (
    "You are the ATS Engineering Assistant, a senior applications engineer. You "
    "are handed a CLIENT REQUIREMENT and a COMPUTED ENGINEERING ANALYSIS that was "
    "synthesised from the company's own historical project offers. A precise "
    "per-value table with sources is shown to the user separately, so your job is "
    "to write the engineering NARRATIVE that frames it.\n"
    "Write a confident, professional summary (about 4-7 sentences; a couple of "
    "bullets are fine) that:\n"
    "1. restates what the client asked for;\n"
    "2. explains how the design was derived from past work — name the closest "
    "project, say what was reused directly, what was scaled or interpolated to "
    "fit the new requirement, and what follows engineering standards;\n"
    "3. states the confidence honestly and flags any assumptions or missing inputs.\n"
    "Keep it faithful: use only values that appear in the analysis below — don't "
    "invent or re-round numbers, sizes or makes (the table is the source of "
    "truth). Don't claim a perfect or exact match unless the analysis says so, "
    "and don't expose raw JSON field names."
)

CHAT_SYSTEM = (
    "You are the ATS Engineering Assistant — a sharp, friendly senior engineer "
    "at an industrial air-pollution-control and surface-finishing equipment "
    "company (wet scrubbers, paint and powder-coating booths, ovens, conveyors, "
    "AHUs, blowers and related systems). Talk to the user like a helpful expert "
    "colleague.\n\n"
    "How to answer well:\n"
    "- Be natural and conversational, the way a knowledgeable engineer explains "
    "things. Get to the point, but don't be robotic or terse.\n"
    "- Match depth to the question: a quick question gets a quick answer; a "
    "how/why question gets a clear explanation of the key reasoning, with bullets "
    "or numbered steps when they genuinely help.\n"
    "- For technical topics, explain the real engineering — the principle, the "
    "relevant numbers or formula, the materials and standards — so the person "
    "actually learns something.\n\n"
    "Staying accurate (this matters most):\n"
    "- When COMPANY PROJECT DATA is provided below, treat it as the source of "
    "truth: use its real clients, components, sizes, makes and materials, and "
    "mention the source file. Never contradict it or change its numbers.\n"
    "- If the data needed to answer isn't in front of you, answer from your own "
    "engineering knowledge and briefly say it's general knowledge.\n"
    "- If you genuinely don't know, or aren't sure, say so plainly. NEVER invent "
    "a client, project, number, spec or fact to fill a gap — a clear \"I don't "
    "have that\" is always better than a confident guess.\n"
    "- Keep length sensible: for a greeting or vague message reply briefly and "
    "ask what they need; don't volunteer facts, conversions or formulas nobody "
    "asked for.\n"
    "- Be concise by default — a short paragraph or a few bullets. Answer the "
    "question directly; don't pad or restate everything. Expand only if asked.\n"
    "- Quote numbers exactly as they appear in the data. Do NOT add derived or "
    "converted values (e.g. CFM-to-CMH conversions, computed totals) unless the "
    "user asked for them — an added conversion that is wrong reads as a mistake."
)

# --- small talk: handled deterministically (no LLM, no hallucination) -------

_GREETING = re.compile(
    r"^\s*(hi+|hey+|hello+|yo|hiya|howdy|sup|"
    r"good\s+(morning|afternoon|evening|day)|greetings)[\s!.]*$", re.I)
_THANKS = re.compile(
    r"^\s*(thanks?|thank\s+you|thx|ty|cheers|appreciate\s+it|"
    r"great|nice|cool|awesome|perfect|ok(ay)?|got\s+it|alright)[\s!.]*$", re.I)
_CAPABILITIES = re.compile(
    r"(who\s+are\s+you|what\s+(can|do)\s+you\s+do|what\s+are\s+you|"
    r"how\s+do\s+you\s+work|^\s*help\s*$|capabilit|what\s+can\s+i\s+ask)", re.I)
_HOWRU = re.compile(r"how\s+are\s+you|how'?s\s+it\s+going|how\s+do\s+you\s+do", re.I)

_CAPS = (
    "I'm the **ATS Engineering Assistant**. Working from your company's historical "
    "project offers, I can:\n"
    "- **Generate a technical specification** for new equipment "
    "(e.g. \"wet scrubber for 800 CFM, 750 mm tower, 4 nos\")\n"
    "- **Look up a stored offer** (e.g. \"what did C2C Engineering order?\")\n"
    "- **Explore the knowledge base** (e.g. \"which clients are in the database?\")\n"
    "- **Answer general engineering questions** (scrubbers, booths, ovens, units, formulas)\n"
    "\nWhat would you like to do?"
)


def small_talk(question: str) -> str | None:
    """Return a short canned reply for greetings/thanks/capability questions, or
    None if the message is a real query that should go to the pipeline."""
    q = (question or "").strip()
    if len(q) > 64:               # long messages are real questions, not small talk
        return None
    if _CAPABILITIES.search(q):
        return _CAPS
    if _HOWRU.search(q):
        return ("Doing well, thanks for asking! I'm ready to help with equipment "
                "specifications, offer lookups, or engineering questions. What do you need?")
    if _GREETING.match(q):
        return "Hi! " + _CAPS
    if _THANKS.match(q):
        return "You're welcome! Anything else I can help with?"
    return None

KNOWLEDGE_SPEC_SYSTEM = (
    "You are the ATS Engineering Assistant acting as a SENIOR CONSULTING ENGINEER "
    "for industrial air-pollution-control and surface-finishing equipment. A "
    "senior engineer NEVER guesses dimensions, capacities, quantities, materials, "
    "filter types or model numbers. You produce a CONCEPTUAL engineering "
    "specification (a design framework), not a filled-in datasheet.\n\n"
    "THE ONE RULE — do not break it: Never state a precise engineering value "
    "(dimension, airflow, fan/pump/motor rating, nozzle or gun count, filter "
    "type, material grade, capacity, quantity) UNLESS it is (a) given by the "
    "user, or (b) directly derived from a named engineering formula using the "
    "user's inputs. If it cannot be derived, write **To be determined** and state "
    "exactly what input or calculation is needed. Do NOT invent numbers, "
    "materials or components to look complete — credibility comes from not "
    "pretending to know.\n\n"
    "Separate KNOWN inputs, what can be DERIVED from them, and what is truly "
    "MISSING. Anything the user already gave is a fixed fact — NEVER list it as "
    "'required'. Format the answer in markdown with these sections:\n"
    "## Known Inputs\n"
    "Restate ONLY the values the user actually provided (dimensions, booth type, "
    "application method, throughput, coating type, etc.). These are fixed — do "
    "not ask for any of them again anywhere below.\n"
    "## Engineering Observations\n"
    "2-4 bullets on what the known inputs IMPLY (relationships, not invented "
    "numbers). For example: the booth internal size must exceed the largest "
    "component plus handling/access clearance; a component larger than typical "
    "past designs means the booth and its airflow must be sized up, not reused; "
    "recovery and filtration concepts from similar projects remain applicable "
    "even when dimensions must change.\n"
    "## Preliminary Recommendation\n"
    "A markdown table (columns: Item | Recommendation) of DIRECTIONAL choices — "
    "the design approach, not precise numbers — consistent with the known inputs, "
    "each qualified with 'subject to ...' where it depends on missing data. "
    "Example rows: booth type, construction approach, filtration/recovery "
    "approach, exhaust/fresh-air need, lighting, control panel, access.\n"
    "## Information Required Before Detailed Design\n"
    "A bullet list of ONLY the inputs the user did NOT already provide — e.g. "
    "design face velocity, applicable standard/code, utility availability, site "
    "layout, handling/conveying method, future expansion. Never repeat a Known "
    "Input here.\n"
    "## To Be Determined\n"
    "A markdown table (columns: Value | Required Inputs) — for every value that "
    "needs calculation, list the specific MISSING prerequisites (not values "
    "already known). E.g. Exhaust airflow | booth open-face area (from component "
    "+ clearance), design face velocity, applicable standard.\n\n"
    "If — and only if — the user gave enough to compute a value with a standard "
    "formula, compute it and show the formula and basis; otherwise keep it 'To be "
    "determined'. Use correct units, no LaTeX. Be concise, professional and "
    "honest. This is general engineering guidance, not from company records."
)


# --- self-verify: a second pass that strips unsupported claims ---------------

VERIFY_SYSTEM = (
    "You are a careful fact-checker for an engineering assistant. You are given "
    "the DATA the assistant was allowed to use, the QUESTION, and a DRAFT answer. "
    "Return a corrected version of the answer that states ONLY facts supported by "
    "the DATA.\n"
    "- Fix or remove any client name, number, size, material or claim that the "
    "DATA does not support.\n"
    "- If the DATA does not actually contain what was asked, say so plainly "
    "instead of guessing.\n"
    "- Do NOT add new facts that aren't in the DATA.\n"
    "- Keep the helpful tone, wording and markdown formatting where they are "
    "already correct. If the draft is already fully supported, return it "
    "essentially unchanged.\n"
    "Output only the corrected answer text — no preamble, no notes about what you "
    "changed."
)


def verify_messages(question, hits, draft) -> list[dict[str, str]]:
    data = _context(_grounding_hits(hits)) or "(no company data was retrieved)"
    user = (f"DATA:\n{data}\n\n---\n\nQUESTION: {question}\n\n"
            f"DRAFT ANSWER:\n{draft}\n\n---\n\n"
            f"Return the corrected answer.")
    return [{"role": "system", "content": VERIFY_SYSTEM},
            {"role": "user", "content": user}]


def _kb_guidance(category) -> str:
    """Feed the model the structured directional KB for this equipment: correct
    design approach + the inputs each computed value needs. Directions only — the
    KB holds no precise numbers, so the model has nothing fake to copy."""
    kb = directional(category)
    if not kb:
        return ""
    rec = "; ".join(f"{item} -> {r}" for item, r in kb["recommendation"])
    stds = ", ".join(kb.get("standards", [])) or "confirm with customer"
    tbd = "; ".join(f"{v} needs [{', '.join(inp)}]"
                    for v, inp in kb["computed_values"].items())
    return (
        "\n\nDIRECTIONAL KNOWLEDGE for this equipment (directions only, contains "
        "NO precise numbers on purpose — use it, don't add numbers):\n"
        f"- Recommended approach: {rec}\n"
        f"- Applicable standards: {stds}\n"
        f"- For the To Be Determined table, list exactly these values with their "
        f"required inputs: {tbd}"
    )


def knowledge_spec_messages(question, analysis) -> list[dict[str, str]]:
    """Messages for the LLM to DESIGN a conceptual spec from general engineering
    knowledge (no stored-offer matching), anchored by the directional KB."""
    given = "; ".join(f"{g['label']}: {g['value']}" for g in analysis.get("given_data", []))
    cat = analysis.get("category_label") or "the requested equipment"
    missing = analysis.get("completeness_missing") or []
    miss_line = (f"\nInputs still MISSING (lead your 'Information Required' section "
                 f"with exactly these): {', '.join(missing)}" if missing else "")
    user = (
        f"Equipment: {cat}\n"
        f"Inputs the user actually provided: {given or 'only the equipment type'}"
        f"{miss_line}\n\n"
        f"Client request: \"{question}\"\n\n"
        f"Produce the conceptual engineering specification / design framework. "
        f"Treat anything not in the provided inputs (and not derivable by a "
        f"formula from them) as 'To be determined' — do not invent it."
        f"{_kb_guidance(analysis.get('category'))}"
    )
    return [{"role": "system", "content": KNOWLEDGE_SPEC_SYSTEM},
            {"role": "user", "content": user}]


_STRUCTURED = {"specification", "quotation"}


def _flat(d, prefix=""):
    """Flatten a nested dict/list into 'a key value' pairs for readable context."""
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            label = str(k).replace("_", " ")
            if isinstance(v, (dict, list)):
                out.extend(_flat(v, label))
            else:
                out.append(f"{label} {v}")
    elif isinstance(d, list):
        for v in d:
            if isinstance(v, (dict, list)):
                out.extend(_flat(v, prefix))
            else:
                out.append(str(v))
    return out


def _doc_summary(rec) -> str:
    """A compact, human-readable rendering of an offer record — far easier for a
    small local model to use than a raw JSON dump."""
    head = rec.get("title") or rec.get("id", "Project")
    bits = [f"Project {rec.get('id', '?')} — {head}"]
    if rec.get("client"):
        bits.append(f"client {rec['client']}")
    if rec.get("source_file"):
        bits.append(f"source {rec['source_file']}")
    lines = ["• " + ", ".join(bits)]
    if rec.get("given_data"):
        lines.append("    Requirement: " + "; ".join(_flat(rec["given_data"])))
    if rec.get("technical_details"):
        lines.append("    Engineered: " + "; ".join(_flat(rec["technical_details"])))
    for sec in ("price_schedule", "essential_equipment", "commercial_terms"):
        if rec.get(sec):
            lines.append(f"    {sec.replace('_', ' ').title()}: " + "; ".join(_flat(rec[sec]))[:600])
    return "\n".join(lines)


def _grounding_hits(hits):
    """Company data on-topic enough to feed a conversational answer (soft bar),
    capped at MAX_GROUNDING_DOCS (highest-scoring first) so the prompt never
    balloons to the whole corpus."""
    rel = [h for h in hits if h.get("score", 0) >= config.GROUNDING_THRESHOLD]
    rel.sort(key=lambda h: h.get("score", 0), reverse=True)
    return rel[:config.MAX_GROUNDING_DOCS]


def _context(hits):
    return "\n\n".join(_doc_summary(h["record"]) for h in hits)


def spec_messages(question, analysis) -> list[dict[str, str]]:
    """Messages for the LLM to narrate a computed specification. The LLM is fed
    the EXACT decided values, so quoting them is safe; it must not add new ones."""
    given = "; ".join(f"{g['label']}: {g['value']}" for g in analysis.get("given_data", []))
    decided = "\n".join(
        f"- {it['label']}: {it['value']}  ({it['origin_label']}"
        f"{'; ' + it['reason'] if it.get('reason') else ''})"
        for it in analysis.get("technical_details", []))
    chosen = analysis.get("exact_match") or analysis.get("nearest_match") or "n/a"
    m = analysis.get("match") or {}
    conf = (f"{analysis.get('confidence_pct')}% ({analysis.get('confidence_label')})")
    assume = "; ".join(f"{a['label']}={a['value']}" for a in analysis.get("assumptions", [])) or "none"
    missing = ", ".join(analysis.get("missing_inputs", [])) or "none"
    notes = " ".join(analysis.get("confidence_notes", [])) or "none"
    user = (
        f"Equipment category: {analysis.get('category_label')}\n"
        f"Closest historical project: {chosen}"
        + (f" (engineering match {m['overall']}%)" if m.get("overall") is not None else "")
        + "\n\n"
        f"CLIENT REQUIREMENT (given data):\n{given or 'not fully specified'}\n\n"
        f"DECIDED TECHNICAL VALUES (use these exact values only):\n{decided}\n\n"
        f"Confidence: {conf}. Assumptions: {assume}. Missing inputs: {missing}. "
        f"Notes: {notes}.\n\n"
        f"Client request was: \"{question}\".\n\n"
        f"Write the engineering narrative that frames this specification."
    )
    return [{"role": "system", "content": SPEC_SYSTEM},
            {"role": "user", "content": user}]


_TASK_HINTS = {
    "analytical": (
        "\n\nThis is an analytical question. Use ONLY the data above. Work the "
        "figures out carefully — count, sum or average across the projects as "
        "needed — and show a short breakdown of how you reached the number. If "
        "the data doesn't contain what's needed, say so plainly rather than guess."),
    "comparison": (
        "\n\nCompare the relevant items SIDE BY SIDE as a markdown table: one "
        "column per item (client/project) and one row per attribute (equipment "
        "type, key sizes, materials, make, quantity, etc.). After the table, add "
        "a 1-2 sentence takeaway. Use only the data above; leave a cell blank if "
        "the data doesn't have that value."),
}


def build_messages(question, hits, analysis, history=None) -> list[dict[str, str]]:
    """Conversational (non-spec) message builder, with company data grounding."""
    relevant = _grounding_hits(hits)
    hint = _TASK_HINTS.get(analysis.get("mode"), "")
    if relevant:
        user = (
            f"COMPANY PROJECT DATA (use where relevant, cite the source file):\n\n"
            f"{_context(relevant)}\n\n---\n\n"
            f"Question: {question}{hint}"
        )
    else:
        user = (
            f"Question: {question}\n\n(No company project data was found for this — "
            f"answer from general engineering knowledge and note that it is general.)"
        )
    msgs = [{"role": "system", "content": CHAT_SYSTEM}]
    for h in (history or [])[-6:]:   # prior turns for multi-turn context
        role = h.get("role")
        if role in ("user", "assistant") and h.get("content"):
            msgs.append({"role": role, "content": str(h["content"])[:600]})
    msgs.append({"role": "user", "content": user})
    return msgs


# --- deterministic fallback (no LLM) ---------------------------------------

def fallback_answer(question, hits, analysis) -> str:
    if analysis.get("intent") not in _STRUCTURED:
        relevant = _grounding_hits(hits)
        if relevant:
            return _chat_fallback(relevant, analysis)
        # general-knowledge question — needs the LLM
        return ("This is a general question I'd answer from general engineering "
                "knowledge, but the local LLM is not reachable right now. Start "
                "Ollama and ask again.")
    if not hits:
        return "No relevant offer documents were found. Try ingesting data or rephrasing."
    return _spec_fallback(analysis)


def _chat_fallback(hits, analysis):
    L = ["**Relevant documents**", ""]
    for h in hits[:4]:
        rec = h["record"]
        note = rec.get("notes") or rec.get("title") or ""
        src = f" ({rec.get('source_file')})" if rec.get("source_file") else ""
        L.append(f"• **{h['id']}**{src}: {note}")
    L.append("")
    L.append("> Note: local LLM not warm yet — showing the source documents.")
    return "\n".join(L)


def spec_writeup(analysis) -> str:
    """Deterministic, ChatGPT-style specification write-up built straight from the
    analysed values. No LLM, so the prose can NEVER contradict the numbers (fixes
    the '12 m tower height' bug), and we control sources + quantity wording."""
    cat = analysis.get("category_label", "Equipment")
    chosen = analysis.get("exact_match") or analysis.get("nearest_match")
    sims = analysis.get("similar_offers") or []
    src = next((s.get("source_file") for s in sims if s.get("id") == chosen), None)
    gd = analysis.get("given_data") or []
    td = analysis.get("technical_details") or []
    params = (analysis.get("understanding") or {}).get("parameters") or {}
    qty = params.get("qty")

    L = [f"## {cat} — Recommended Specification", ""]

    if gd:
        L.append("**Customer Requirements**")
        L += [f"- ✓ {g['label']}: {g['value']}" for g in gd]
        L.append("")

    # Engineering Assessment — the decision engine's snapshot.
    ku = analysis.get("knowledge_used") or {}
    comp = analysis.get("completeness")
    miss = analysis.get("completeness_missing") or []
    warns = sum(1 for c in (analysis.get("validation") or []) if c.get("level") == "warn")
    L.append("**Engineering Assessment**")
    if comp is not None:
        L.append(f"- Requirement completeness: {comp}%")
    L.append(f"- Historical support: {ku.get('historical_projects', 0)} ATS project(s)")
    L.append(f"- Applicable engineering rules: {ku.get('rules', 0)}")
    L.append(f"- Validation checks flagged: {warns}")
    L.append(f"- Missing inputs: {', '.join(miss) if miss else 'None'}")
    L.append("")

    # Clarify ambiguous quantity (e.g. '4 Nos' = 4 complete units, each 1 tower).
    if isinstance(qty, (int, float)) and qty > 1:
        q = int(qty) if float(qty).is_integer() else qty
        L.append(f"> **Quantity:** {q} complete {cat.lower()} units are required. The "
                 f"specification below is **per unit** — each unit has its own tower, "
                 f"pump, spray nozzles and tank as listed.")
        L.append("")

    if td:
        L.append("**Recommended specification (per unit)**")
        for it in td:
            reason = it.get("reason", "")
            L.append(f"- **{it['label']}:** {it['value']}" + (f" — {reason}" if reason else ""))
        L.append("")

    val = analysis.get("validation") or []
    if val:
        L.append("**Engineering checks**")
        icons = {"ok": "✓", "warn": "⚠", "info": "•"}
        L += [f"- {icons.get(c['level'], '•')} {c['message']}" for c in val]
        L.append("")

    L.append("**Basis & confidence**")
    if chosen:
        L.append(f"Based primarily on historical project **{chosen}** — the closest "
                 f"comparable {cat.lower()} on file. Client-requirement values come "
                 f"straight from your input; others are computed by engineering rules "
                 f"or reused from that project. With limited comparable projects on "
                 f"file, treat this as a starting point for engineering review.")
    factors = analysis.get("confidence_factors") or []
    if factors:
        L.append("")
        L += [f"- {f['label']}: {f['value']}" for f in factors]
    cp, cl = analysis.get("confidence_pct"), analysis.get("confidence_label")
    if cp is not None:
        notes = " ".join(analysis.get("confidence_notes") or [])
        L.append("")
        L.append(f"**Overall confidence: {cp}% ({cl}).**{(' ' + notes) if notes else ''}")
    prov = provenance_summary(td)
    if prov:
        L.append("")
        L.append(f"_Provenance: {prov}_")
    if src:
        L.append("")
        L.append(f"_Source: {src}_")
    return "\n".join(L)


def spec_summary(analysis):
    """Deterministic short framing for a structured spec (no LLM, never wrong).
    The visual table/panel carries the exact per-value detail."""
    cat = analysis.get("category_label", "Equipment")
    chosen = analysis.get("exact_match") or analysis.get("nearest_match")
    ku = analysis.get("knowledge_used") or {}
    b = ku.get("breakdown", {})
    if not analysis.get("technical_details"):
        return (f"No close historical {cat.lower()} project was found for this requirement. "
                "Add more offers or provide more inputs.")
    n_proj = ku.get("historical_projects", 0)
    parts = [f"**{cat} specification** synthesised from {n_proj} historical "
             f"project{'s' if n_proj != 1 else ''} "
             f"({ku.get('components_compared', 0)} components compared)."]
    seg = [f"{b[k]} {k.lower()}" for k in
           ("Engineering Rule", "Inferred", "Recommended", "Historical Consensus",
            "Reused", "From Requirement")
           if b.get(k)]
    if seg:
        tail = f"; closest design {chosen}." if chosen else "."
        parts.append("Decisions — " + ", ".join(seg) + tail)
    kb = next((f["value"] for f in analysis.get("confidence_factors", [])
               if f["label"] == "Knowledge-backed decisions"), None)
    if kb:
        parts.append(f"{kb} decisions are evidence-backed.")
    m = analysis.get("match")
    if m and m.get("overall") is not None:
        parts.append(f"Engineering match {m['overall']}%, confidence "
                     f"{analysis['confidence_pct']}% ({analysis['confidence_label']}).")
    if analysis.get("confidence_notes"):
        parts.append("Confidence reduced: " + " ".join(analysis["confidence_notes"]))
    if analysis.get("assumptions"):
        parts.append(f"{len(analysis['assumptions'])} value(s) assumed from historical consensus.")
    parts.append("Full traceable breakdown, assumptions and confidence factors are shown below.")
    return " ".join(parts)


def _spec_fallback(analysis):
    cat = analysis.get("category_label", "Equipment")
    L = [f"**{cat} — Technical Specification**", ""]

    if analysis["given_data"]:
        L.append("**REQUIREMENT**")
        for g in analysis["given_data"]:
            L.append(f"  • {g['label']}: {g['value']}")
        L.append("")

    m = analysis.get("match")
    chosen = analysis["exact_match"] or analysis["nearest_match"]
    if m and chosen:
        L.append(f"**ENGINEERING MATCH** — {chosen}: **{m['overall']}%** overall")
        sub = []
        if m["driver"] is not None:
            sub.append(f"{m['driver_label']} {m['driver']}%")
        if m["dimension"] is not None:
            sub.append(f"dimension {m['dimension']}%")
        if m["process"] is not None:
            sub.append(f"process {m['process']}%")
        sub.append(f"historical similarity {m['historical']}%")
        L.append("  (" + " · ".join(sub) + ")")
        L.append("")

    if analysis["similar_offers"]:
        L.append("**ALTERNATIVES CONSIDERED**")
        for s in analysis["similar_offers"]:
            mark = " ◄ chosen" if s["id"] == chosen else ""
            L.append(f"  • {s['id']}: {s['difference']}{mark}")
        L.append("")

    if analysis["technical_details"]:
        L.append("**ENGINEERING DECISIONS**")
        for it in analysis["technical_details"]:
            L.append(f"  • {it['label']}: **{it['value']}**")
            L.append(f"      {it['origin_label']} — {it['reason']}")
        L.append("")

    ku = analysis.get("knowledge_used")
    if ku:
        L.append("**KNOWLEDGE REASONING SUMMARY**")
        L.append(f"  {ku['historical_projects']} historical projects · {ku['rules']} engineering rules · "
                 f"{ku['standards']} standards · {ku['components_compared']} components compared · "
                 f"{ku['decisions']} decisions")
        if ku.get("breakdown"):
            L.append("  Decisions: " + " · ".join(f"{v} {k}" for k, v in ku["breakdown"].items()))
    if analysis.get("knowledge_contribution"):
        L.append("  Knowledge contribution: " + " · ".join(
            f"{c['source']} {c['pct']}%" for c in analysis["knowledge_contribution"]))
    if ku or analysis.get("knowledge_contribution"):
        L.append("")

    if analysis.get("missing_inputs"):
        L.append("**MISSING INPUTS**: " + ", ".join(analysis["missing_inputs"]))
        L.append("")

    L.append(f"**CONFIDENCE: {analysis['confidence_pct']}%** ({analysis['confidence_label']})")
    for c in analysis.get("criteria", []):
        L.append(f"  {'✓' if c['ok'] else '✗'} {c['label']}")
    if analysis.get("source_files"):
        L.append(f"\n_Evidence: {', '.join(analysis['source_files'])}_")
    L.append("")
    L.append("> Note: the local LLM did not respond in time — this spec was "
             "produced by the deterministic engineering reasoning layer.")
    return "\n".join(L)
