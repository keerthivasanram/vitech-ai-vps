"""The Flowise agent tool bridge. Each `operation_id` IS the tool name the
agent sees — never change one without rebuilding the chatflow."""
from fastapi import APIRouter
from ..agent_router import prepare as _prepare
from ..analytics import _label as category_label
from ..analytics import record_detail
from ..analytics import render_lookup_markdown
from ..analytics import wants_price
from ..classify import CONFIDENT
from ..classify import classify_equipment
from ..pricing import inr_display
from ..quotation import build_quotation
from ..resolver import ATS
from ..resolver import resolve
from ..retriever import project_hits
from ..retriever import retrieve
from ..understand import understand
from fastapi import Body
from rag.permissions import Principal
from rag.response_formatter import format_context
from rag.retrieve import available_filters
from rag.retrieve import retrieve_documents
from ..observability import jobs as _jobs, trace as _obs
from .support import _named_requirement, _offers_overview, _spec_bom, _spec_for_drawing, _spec_geometry, _spec_markdown, _spec_text, _tool_q

router = APIRouter()


# --- Tool endpoints for the Flowise Engineering Agent -----------------------
# Flowise Custom Tools POST natural language here; Python does ALL the reasoning
# and returns clean JSON (structured + a deterministic `text`). The Flowise LLM
# narrates the result — it never computes a number itself.

@router.post("/api/tools/spec", operation_id="generate_specification")
def tool_spec(payload: dict = Body(...)):
    """Requirement -> engineering specification (deterministic + structured)."""
    q = _tool_q(payload)
    # GUARD: no equipment named = not a real requirement. Never build a spec
    # skeleton from noise (a bare "generate a spec" must make the agent ASK).
    if not _named_requirement(q):
        return {"ok": False, "need_requirement": True,
                "message": ("No equipment requirement was given. Ask the user WHICH equipment and its "
                            "size/capacity to specify. Do NOT generate a spec, and do NOT invent or pick "
                            "any equipment or number the user did not state.")}
    _obs.note(tool="generate_specification", agent="Engineering")
    job = _jobs.create("specification", requirement=q)
    _, a, _ = _prepare(q, top_k=8, history=[])
    resp = {
        "category": a.get("category"),
        "category_label": a.get("category_label"),
        "mode": a.get("spec_mode"),
        "confidence_pct": a.get("confidence_pct"),
        "confidence_label": a.get("confidence_label"),
        "completeness": a.get("completeness"),
        "missing_inputs": a.get("completeness_missing") or a.get("missing_inputs") or [],
        "given_data": a.get("given_data") or [],
        "technical_details": [
            {"label": t.get("label"), "value": t.get("value"),
             "origin": t.get("origin_label") or t.get("origin"), "source": t.get("source"),
             # the derivation: the actual formula for a calculated value, or which
             # historical offer a value was reused/scaled from. Surfaced so the
             # spec shows HOW each number was arrived at, not just a generic label.
             "reason": t.get("reason"),
             # 'tbd' marks a template field with no value yet (needs engineering
             # input) — the agent must render it as TBD, never fill it in.
             "status": "tbd" if t.get("origin") == "tbd" else "resolved",
             "kind": t.get("kind")}
            for t in (a.get("technical_details") or [])
        ],
        # Engineering review: the sanity checks the engine ran, and whether the
        # document may go to a customer. Confidence says how well-founded the
        # numbers are; this says whether it may leave the building.
        "validation": a.get("validation") or [],
        "release": a.get("release") or {},
        # The same engineering read a second way, by what must be bought and
        # made. Structured only — it is deliberately NOT folded into
        # spec_markdown, which the agent already prints at its length limit.
        "bom": _spec_bom(a),
        # structured geometry for the 2D-drawing generator (numeric mm envelope
        # + per-dimension status); prose table above is for humans, this is for code.
        "geometry": _spec_geometry(a),
        "sources": a.get("source_files") or [],
        "text": _spec_text(a),
    }
    # a ready-to-print spec the agent outputs VERBATIM (data mode); None in
    # knowledge mode, where the agent reasons from engineering knowledge instead.
    resp["spec_markdown"] = _spec_markdown(resp)
    _jobs.finish(job, equipment=a.get("category") or "",
                 confidence_pct=a.get("confidence_pct"),
                 release_status=(a.get("release") or {}).get("status", ""),
                 warning_count=len([c for c in (a.get("validation") or [])
                                    if c.get("level") == "warn"]),
                 tbd_count=len([t for t in (a.get("technical_details") or [])
                                if t.get("origin") == "tbd"]),
                 summary={"rows": len(resp["technical_details"]),
                          "mode": resp.get("mode")})
    return resp

@router.post("/api/tools/drawing", operation_id="generate_drawing")
def tool_drawing(payload: dict = Body(...)):
    """Requirement -> 2D general-arrangement drawing (deterministic geometry)."""
    from ..drawing.drawing_service import build_drawing
    from ..drawing.spec_parser import looks_like_spec, parse_spec

    q = _tool_q(payload)
    # A pasted specification is drawn AS GIVEN rather than re-resolved, so the
    # sheet matches the document the engineer reviewed.
    if looks_like_spec(q) and (parsed := parse_spec(q)):
        drawing = build_drawing(parsed, sheet_size=str(payload.get("sheet_size") or "A3"))
        drawing["svg_bytes"] = len(drawing.get("svg") or "")
        drawing["from_specification"] = True
        return drawing
    # Same guard as spec/quote: never draw from noise.
    if not _named_requirement(q):
        return {"ok": False, "need_requirement": True,
                "message": ("No equipment requirement was given. Ask the user WHICH equipment and its "
                            "size to draw. Do NOT generate a drawing, and do NOT invent any equipment "
                            "or dimension the user did not state.")}
    _obs.note(tool="generate_drawing", agent="Drawing")
    job = _jobs.create("drawing", requirement=q)
    drawing = build_drawing(_spec_for_drawing(q),
                            sheet_size=str(payload.get("sheet_size") or "A3"))
    _jobs.finish(job, equipment=drawing.get("category") or "",
                 tbd_count=len(drawing.get("tbd") or []),
                 summary={"views": len(drawing.get("views") or []),
                          "scale": drawing.get("scale"),
                          "ready": drawing.get("ready")})
    # The SVG is large and is for the canvas, not the chat: the agent gets the
    # markdown summary and never has to echo vector data.
    drawing["svg_bytes"] = len(drawing.get("svg") or "")
    return drawing


@router.post("/api/tools/quote", operation_id="generate_quotation")
def tool_quote(payload: dict = Body(...)):
    """Requirement -> budgetary quotation (deterministic pricing from history)."""
    q = _tool_q(payload)
    # GUARD: no equipment named = not a real requirement. Never fabricate a quote
    # from database noise (a bare "generate quotation" must make the agent ASK).
    if not _named_requirement(q):
        return {"ok": False, "need_requirement": True,
                "message": ("No equipment requirement was given. Ask the user WHICH equipment and "
                            "its size/capacity to quote (the airflow for a scrubber or dust collector, "
                            "the dimensions for a booth, etc.). Do NOT quote, and do NOT invent or pick "
                            "any equipment or number the user did not state.")}
    _obs.note(tool="generate_quotation", agent="Quotation")
    job = _jobs.create("quotation", requirement=q)
    u = understand(q)
    u.intent = "quotation"
    where = {"category": u.category} if u.category else None
    hits = retrieve(q, top_k=8, where=where)
    a = resolve(q, hits, u, ATS)
    a["spec_mode"] = "data"
    quote = build_quotation(a, dict(u.parameters))
    if not quote:
        _jobs.finish(job, status=_jobs.FAILED, equipment=u.category or "",
                     error="no priced history")
        return {"ok": False,
                "message": f"No priced history to quote {u.category or 'this equipment'} from."}
    _jobs.finish(job, equipment=u.category or "",
                 confidence_pct=quote.get("confidence_pct"),
                 summary={"ref": quote.get("ref"), "price": quote.get("price_display")})
    return {"ok": True, **quote}


@router.post("/api/tools/lookup", operation_id="lookup_project")
def tool_lookup(payload: dict = Body(...)):
    """Named client / offer -> exactly the data extracted from that file(s).

    Price is included ONLY when the user asks about money ("price / cost / quote
    of X"). A plain "details about X" returns the engineering (given data +
    technical details) with no price, so the agent cannot lead with rupees when
    that is not what was asked. The price is still one follow-up away.
    """
    q = _tool_q(payload)
    _obs.note(tool="lookup_project", agent="Engineering")
    price_asked = wants_price(q)
    # force_tech: even when the agent shortened the input to a bare client name,
    # the narrative still leads with the engineering (given data + technical
    # details); price is folded in only when the input actually asked about it.
    text = record_detail(q, force_tech=True)
    recs, seen = [], set()
    for h in project_hits(q):
        if h["id"] in seen:
            continue
        seen.add(h["id"])
        r = h["record"]
        ps = r.get("price_schedule") or {}
        cur = ps.get("currency", "INR")
        # preformatted rupee strings so the agent never regroups a historical price.
        # ALWAYS carried (even when price wasn't asked) so the model has the real
        # figure to hand and can never invent one -- presentation (show/hide) is
        # steered by `price_asked` + the prompt, but the number is always exact.
        ps_display = {k: (inr_display(v) if cur in (None, "INR", "Rs", "Rs.") else f"{cur} {v:,}")
                      for k, v in ps.items()
                      if k != "currency" and isinstance(v, (int, float))}
        recs.append({"id": r.get("id"), "client": r.get("client"),
                     "category": r.get("category"), "source_file": r.get("source_file"),
                     "given_data": r.get("given_data"),
                     "technical_details": r.get("technical_details"),
                     "price_schedule": ps,
                     "price_schedule_display": ps_display})
    if not recs:
        return {"ok": False, "message": "No matching client or offer found."}
    recs = recs[:4]
    return {"ok": True, "text": text, "price_asked": price_asked, "records": recs,
            # rendered in code so the agent prints it verbatim and can never
            # re-dress an archive record as a freshly generated quotation
            "lookup_markdown": render_lookup_markdown(recs, price_asked=price_asked)}


# filter keys the agent may pass either nested under "filters" or at top level
_RETRIEVE_FILTER_KEYS = ("equipment_type", "customer", "project", "doc_category",
                         "revision", "offer_number", "date", "section", "kind")


@router.post("/api/tools/retrieve", operation_id="retrieve_knowledge")
def tool_retrieve(payload: dict = Body(...)):
    """Search the engineering knowledge base (ingested reference documents:
    standards, catalogs, past-offer source files) with an optional metadata
    filter applied BEFORE semantic search. This is the Engineering Agent's
    'search ChromaDB' step — it grounds the narrative, while the numbers still
    come from /api/tools/spec. Never reasons over the numbers itself.

    Body: {"question": "...", "top_k": 6,
           "filters": {"equipment_type": "wet_scrubber", "section": "technical_specification"}}
    (filter keys may also be passed at the top level for convenience).
    """
    q = _tool_q(payload)
    filters = dict(payload.get("filters") or {})
    for key in _RETRIEVE_FILTER_KEYS:
        if payload.get(key) is not None:
            filters[key] = payload[key]
    try:
        top_k = max(1, min(int(payload.get("top_k", 6)), 20))
    except (TypeError, ValueError):
        top_k = 6

    role = payload.get("role") or "engineer"
    hits = retrieve_documents(q, top_k=top_k, filters=filters,
                              principal=Principal(role=role))
    ctx = format_context(hits)
    return {
        "ok": True,
        "query": q,
        "filters": {k: v for k, v in filters.items() if v is not None},
        "count": len(hits),
        "results": [
            {"source_file": h.get("source_file"), "section": h.get("section"),
             "page": h.get("page"), "equipment_type": h.get("equipment_type"),
             "kind": h.get("kind"), "score": h.get("score"),
             "rerank_score": h.get("rerank_score"), "text": h.get("text")}
            for h in hits
        ],
        # structured, de-duplicated sources + a numbered context block the agent
        # can quote from and cite by [n].
        "citations": ctx["citations"],
        "context": ctx["context"],
    }


@router.get("/api/tools/filters", operation_id="list_filters")
def tool_filters():
    """Distinct metadata values present across the knowledge base, so the agent
    (or UI) can pick a filter that actually matches something."""
    return {"ok": True, "filters": available_filters()}

@router.post("/api/tools/list", operation_id="list_projects")
def tool_list_projects(payload: dict = Body(...)):
    """Enumerate stored Vitech offers — answers 'how many / list all / which
    clients / what categories / what have we quoted' deterministically.

    The 4 other tools are point lookups; this one returns the whole set so the
    agent never has to guess a count or invent a client. Numbers are exact.

    An EQUIPMENT FILTER is applied in Python when the question (or an explicit
    `category`/`equipment_type` field) names an equipment type — e.g. "how many
    clients in paint booth". golden rule #2: Python decides the scope and counts
    it; the model NEVER filters a corpus in its head (that is the bug where
    "clients in paint booth" dumped all 33 offers and invented "30 clients").
    """
    offers = _offers_overview()
    # full-corpus category breakdown is always returned, so "what categories /
    # equipment types do we have" (an unfiltered question) still works.
    all_cats: dict[str, int] = {}
    for o in offers:
        c = o.get("category")
        if c:
            all_cats[c] = all_cats.get(c, 0) + 1
    categories = [{"category": c, "count": n}
                  for c, n in sorted(all_cats.items(), key=lambda kv: (-kv[1], kv[0]))]

    # deterministic scope: explicit field wins, else classify from the question.
    q = _tool_q(payload)
    scope = payload.get("category") or payload.get("equipment_type")
    if not scope:
        guess, score = classify_equipment(q)
        # scope on a confident classification, OR when the category is named
        # literally (e.g. "how many clients for conveyor" — 'conveyor' classifies
        # weakly but is stated outright, and must not return all 33).
        if guess and (score >= CONFIDENT or guess.replace("_", " ") in q.lower()):
            scope = guess
    scope = scope if scope in all_cats else None   # only filter on a real category
    scoped = [o for o in offers if o.get("category") == scope] if scope else offers
    scope_label = category_label(scope) if scope else None

    clients = sorted({o["client"] for o in scoped if o.get("client")})
    projects = [{
        "id": o.get("id"), "client": o.get("client"), "category": o.get("category"),
        "ref": o.get("ref"), "date": o.get("date"),
        "price_total": o.get("price_total"),
        "price_total_display": inr_display(o["price_total"]) if o.get("price_total") else None,
    } for o in scoped]

    # DETERMINISTIC per-client project counts (golden rule #2: Python counts the
    # corpus, the LLM only reads). Without this the agent tried to tally repeat
    # clients in its head and answered "no client has more than one" — WRONG,
    # e.g. C2C/Meccanotecnica/Yonex each have 2 offers on file. `repeat_clients`
    # (>=2 projects) plus a ready-to-print sentence means the model never counts.
    where = f" for {scope_label}" if scope_label else ""
    from collections import Counter as _Counter
    _client_counts = _Counter(o["client"] for o in scoped if o.get("client"))
    client_project_counts = [{"client": c, "projects": n}
                             for c, n in _client_counts.most_common()]
    repeat_clients = [r for r in client_project_counts if r["projects"] >= 2]
    max_projects = client_project_counts[0]["projects"] if client_project_counts else 0
    if repeat_clients:
        _parts = ", ".join(f"{r['client']} ({r['projects']} projects)" for r in repeat_clients)
        repeat_clients_answer = (
            f"{len(repeat_clients)} client(s) have more than one project on record{where}: "
            f"{_parts}. The most for any single client is {max_projects}."
        )
    else:
        repeat_clients_answer = (
            f"No client has more than one project on record{where} — every client "
            f"appears once.")

    # DETERMINISTIC RANKING (golden rule #2: Python ranks, the LLM only reads).
    # The model must never sort/compare prices itself — llama3.1:8b gets it wrong
    # and invents figures. We hand it the answer pre-computed and pre-formatted.
    priced = sorted(
        (p for p in projects if isinstance(p.get("price_total"), (int, float))),
        key=lambda p: p["price_total"], reverse=True,
    )
    ranked = [{
        "rank": i + 1, "client": p["client"], "category": p["category"],
        "ref": p.get("ref"), "price_total": p["price_total"],
        "price_total_display": p["price_total_display"],
    } for i, p in enumerate(priced)]
    top_by_price = ranked[:10]
    highest_project = ranked[0] if ranked else None
    lowest_project = ranked[-1] if ranked else None
    # A ready-to-print sentence so the model has nothing to compute or reword.
    highest_answer = (
        f"{highest_project['client']} has the highest quotation cost{where}: "
        f"{highest_project['price_total_display']} "
        f"({highest_project['category']}, ref {highest_project['ref']})."
        if highest_project else f"No priced offers on record{where}."
    )
    # Ready-to-print count/client sentence so the model reports the exact scope.
    if scope_label:
        answer = (f"We have {len(scoped)} {scope_label} offer(s) on record, "
                  f"for {len(clients)} client(s).")
    else:
        answer = (f"There are {len(offers)} offers on record across "
                  f"{len(categories)} equipment categories, for "
                  f"{len(clients)} clients.")

    return {
        "ok": True,
        "scope": scope,
        "scope_label": scope_label,
        "answer": answer,
        "count": len(scoped),
        "total_offers": len(offers),
        "n_clients": len(clients),
        "clients": clients,
        "client_project_counts": client_project_counts,
        "repeat_clients": repeat_clients,
        "repeat_clients_answer": repeat_clients_answer,
        "categories": categories,
        "projects": projects,
        "top_by_price": top_by_price,
        "highest_project": highest_project,
        "lowest_project": lowest_project,
        "highest_answer": highest_answer,
    }


@router.post("/api/tools/bom", operation_id="generate_bom_tool")
def tool_bom(payload: dict = Body(...)):
    """Requirement -> bill of materials, for the agents.

    A THIN BRIDGE to `/api/bom`, and it exists for a security reason rather than
    a functional one: `auth/policy.py` lets the service principal reach
    `^/api/tools/` and nothing else, so a leaked agent key cannot ingest, upload
    or read the database. Pointing an agent at `/api/bom` directly would have
    meant widening that rule for every route it guards. One wrapper is cheaper
    than a hole.

    `/api/bom` keeps `operation_id=generate_bom` for the UI; the Flowise tool row
    is named `generate_bom`, which is what the agent actually sees.
    """
    from .bom import bom_endpoint
    return bom_endpoint(payload)
