"""FastAPI app — the ATS Engineering Assistant backend.

Pipeline per query:  question -> understand -> retrieve -> analyze -> LLM -> answer
"""
import html
import json
import re

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

import shutil
import uuid
from pathlib import Path

from . import config, jobs, session
# Routing brain (policy selection, retrieval scoping, analysis + metadata assembly)
# — shared by the /api/query* endpoints and the generate_specification tool.
# Kept under the original private names so the call sites are unchanged.
from .agent_router import prepare as _prepare, build_meta as _meta
from .analytics import record_detail, wants_price
from .analytics import _label as category_label
from .classify import CONFIDENT, classify_equipment
from .resolver import ATS, resolve
from .prompt import spec_summary, spec_writeup
from .pricing import inr_display
from .quotation import build_quotation
from .quotation_pdf import render_quotation_pdf
from .specification_pdf import render_specification_pdf
from .ingest import ingest_source
from .llm import generate_answer, stream_answer
from .retriever import entity_hits, retrieve
from .store import get_collection
from .understand import understand

# Knowledge-base document retrieval (rich metadata filtering) lives in the
# sibling `rag` package — the read side of the document ingestion pipeline.
from rag.retrieve import available_filters, retrieve_documents

app = FastAPI(title="ATS Engineering Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_llm():
    """Pre-load the model in the background so the first query isn't slow."""
    import threading
    from .llm import warmup
    threading.Thread(target=warmup, daemon=True).start()


class QueryRequest(BaseModel):
    question: str
    top_k: int | None = None
    session_id: str | None = None


@app.get("/api/health")
def health():
    try:
        count = get_collection().count()
    except Exception:
        count = 0
    return {
        "status": "ok",
        "documents_indexed": count,
        "llm_model": config.OLLAMA_MODEL,
        "ollama_host": config.OLLAMA_HOST,
        "memory": session.backend(),
    }


@app.get("/api/session/{session_id}")
def session_history(session_id: str):
    return {"session_id": session_id, "messages": session.get_history(session_id, 100)}


@app.delete("/api/session/{session_id}")
def session_clear(session_id: str):
    session.clear(session_id)
    return {"cleared": session_id}


@app.post("/api/ingest")
def run_ingest(reset: bool = True):
    """Kick off batched ingestion in the background and return a job id.
    Poll GET /api/ingest/{job_id} for progress. Scales to thousands of files."""
    job_id = jobs.create_job()

    def work(progress):
        return ingest_source(
            reset=reset,
            batch_size=config.BATCH_SIZE,
            progress=lambda done, _total: progress(done),
        )

    jobs.run(job_id, work)
    return {"job_id": job_id, "source": str(config.DATA_SOURCE),
            "batch_size": config.BATCH_SIZE}


@app.get("/api/ingest/{job_id}")
def ingest_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"error": "unknown job_id"}
    return job


@app.post("/api/query")
def query(req: QueryRequest):
    sid = req.session_id or uuid.uuid4().hex[:12]
    history = session.get_history(sid)
    hits, analysis, grounded = _prepare(req.question, req.top_k, history)

    result = generate_answer(req.question, hits, analysis, history)
    session.append(sid, "user", req.question)
    session.append(sid, "assistant", result["answer"])
    return {**_meta(req.question, sid, hits, analysis, grounded), **result}


@app.post("/api/quotation/pdf")
def quotation_pdf(quote: dict = Body(...)):
    """Render a quotation object (from a quotation-intent response) to a
    downloadable Vitech-format PDF. Deterministic — adds no numbers of its own."""
    data = render_quotation_pdf(quote)
    ref = str(quote.get("ref") or "quotation").replace(" ", "_")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{ref}.pdf"'})


@app.post("/api/specification/pdf")
def specification_pdf(spec: dict = Body(...)):
    """Render a specification object (from a generate_specification response, as
    surfaced by the chat) to a downloadable Vitech-format PDF. Deterministic —
    it prints the engineered rows, adding no numbers of its own. Accepts either
    the structured payload or a {text: "..."} fallback."""
    data = render_specification_pdf(spec)
    name = str(spec.get("category_label") or "specification").replace(" ", "_")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}_specification.pdf"'})


@app.get("/api/offers/by-source/{source_file:path}")
def offer_by_source(source_file: str):
    """Full extracted record whose `source_file` matches — lets the chat open the
    content behind a specification's cited source file in the record inspector.
    Matches on the exact stored name, else on basename (case-insensitive)."""
    target = Path(source_file).name.strip().lower()
    col = get_collection()
    if col.count():
        for m in col.get(include=["metadatas"])["metadatas"]:
            raw = m.get("_raw")
            if not raw:
                continue
            r = json.loads(raw)
            sf = r.get("source_file")
            if sf and Path(str(sf)).name.strip().lower() == target:
                return r
    return {"error": "not found", "source_file": source_file}


# --- Tool endpoints for the Flowise Engineering Agent -----------------------
# Flowise Custom Tools POST natural language here; Python does ALL the reasoning
# and returns clean JSON (structured + a deterministic `text`). The Flowise LLM
# narrates the result — it never computes a number itself.

def _tool_q(payload: dict) -> str:
    for k in ("question", "query", "text", "input", "q"):
        if payload.get(k):
            return str(payload[k])
    return ""


def _named_requirement(q: str) -> bool:
    """True only if `q` is a real equipment requirement: it must name a known
    equipment type AND carry a size/quantity digit. Deterministic (keyword +
    digit), so it can't be fooled by the agent (or understand()'s LLM) inventing
    a bare 'wet scrubber' or a phantom '800 cfm' from a vague 'generate a quote'.
    A genuine spec/quote request always states a number (CFM, mm, dims, temp, qty).
    """
    return bool(classify_equipment(q)[0]) and bool(re.search(r"\d", q or ""))


def _spec_text(a: dict) -> str:
    """A deterministic text summary of a spec/analysis for the agent to narrate."""
    if a.get("spec_mode") == "data":
        return spec_writeup(a) if a.get("technical_details") else spec_summary(a)
    given = "; ".join(f"{g['label']}: {g['value']}" for g in a.get("given_data", [])) or "only the equipment type"
    miss = ", ".join(a.get("completeness_missing") or []) or "none"
    return (f"Known inputs: {given}. Still required before detailed design: {miss}. "
            f"Design from engineering knowledge; do not copy historical values.")


def _spec_markdown(resp: dict) -> str | None:
    """Ready-to-print specification (DATA mode only) — the agent outputs it
    verbatim, same principle as the quotation template. Returns None in knowledge
    mode (no deterministic table; the agent reasons from engineering knowledge).
    """
    tech = resp.get("technical_details") or []
    if not tech:
        return None

    def esc(v):
        return str(v if v is not None else "").replace("|", "/")

    conf = ""
    if resp.get("confidence_pct") is not None:
        conf = f"   |   Confidence: {resp.get('confidence_label', '-')} ({resp['confidence_pct']}%)"
    L: list[str] = []
    L.append("**ENGINEERING SPECIFICATION — DRAFT**")
    L.append(f"Equipment: {resp.get('category_label') or 'Equipment'}{conf}")
    L.append("")

    gd = resp.get("given_data") or []
    if gd:
        L.append("**Customer Requirement**")
        L.append("| Parameter | Value |")
        L.append("| --- | --- |")
        for g in gd:
            L.append(f"| {esc(g.get('label'))} | {esc(g.get('value'))} |")
        L.append("")

    # technical spec = the engineered rows (drop the requirement echoes)
    spec_rows = [t for t in tech if t.get("source") != "requirement"]
    if spec_rows:
        L.append("**Technical Specification**")
        L.append("| Parameter | Value | Basis |")
        L.append("| --- | --- | --- |")
        for t in spec_rows:
            L.append(f"| {esc(t.get('label'))} | {esc(t.get('value'))} | {esc(t.get('origin'))} |")
        L.append("")

    miss = resp.get("missing_inputs") or []
    if miss:
        L.append(f"**To confirm before detailed design:** {', '.join(miss)}")
        L.append("")

    n_src = len(resp.get("sources") or [])
    basis = f"Grounded in {n_src} historical project(s). " if n_src else ""
    L.append(f"_{basis}Engineer-reviewed draft — not a released design._")
    return "\n".join(L)


@app.post("/api/tools/spec", operation_id="generate_specification")
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
             "origin": t.get("origin_label") or t.get("origin"), "source": t.get("source")}
            for t in (a.get("technical_details") or [])
        ],
        "sources": a.get("source_files") or [],
        "text": _spec_text(a),
    }
    # a ready-to-print spec the agent outputs VERBATIM (data mode); None in
    # knowledge mode, where the agent reasons from engineering knowledge instead.
    resp["spec_markdown"] = _spec_markdown(resp)
    return resp


@app.post("/api/tools/quote", operation_id="generate_quotation")
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
    u = understand(q)
    u.intent = "quotation"
    where = {"category": u.category} if u.category else None
    hits = retrieve(q, top_k=8, where=where)
    a = resolve(q, hits, u, ATS)
    a["spec_mode"] = "data"
    quote = build_quotation(a, dict(u.parameters))
    if not quote:
        return {"ok": False,
                "message": f"No priced history to quote {u.category or 'this equipment'} from."}
    return {"ok": True, **quote}


@app.post("/api/tools/lookup", operation_id="lookup_project")
def tool_lookup(payload: dict = Body(...)):
    """Named client / offer -> exactly the data extracted from that file(s).

    Price is included ONLY when the user asks about money ("price / cost / quote
    of X"). A plain "details about X" returns the engineering (given data +
    technical details) with no price, so the agent cannot lead with rupees when
    that is not what was asked. The price is still one follow-up away.
    """
    q = _tool_q(payload)
    price_asked = wants_price(q)
    # force_tech: even when the agent shortened the input to a bare client name,
    # the narrative still leads with the engineering (given data + technical
    # details); price is folded in only when the input actually asked about it.
    text = record_detail(q, force_tech=True)
    recs, seen = [], set()
    for h in entity_hits(q):
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
    return {"ok": True, "text": text, "price_asked": price_asked, "records": recs[:4]}


# filter keys the agent may pass either nested under "filters" or at top level
_RETRIEVE_FILTER_KEYS = ("equipment_type", "customer", "project", "doc_category",
                         "revision", "offer_number", "date", "section", "kind")


@app.post("/api/tools/retrieve", operation_id="retrieve_knowledge")
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

    hits = retrieve_documents(q, top_k=top_k, filters=filters)
    return {
        "ok": True,
        "query": q,
        "filters": {k: v for k, v in filters.items() if v is not None},
        "count": len(hits),
        "results": [
            {"source_file": h.get("source_file"), "section": h.get("section"),
             "page": h.get("page"), "equipment_type": h.get("equipment_type"),
             "kind": h.get("kind"), "score": h.get("score"), "text": h.get("text")}
            for h in hits
        ],
    }


@app.get("/api/tools/filters", operation_id="list_filters")
def tool_filters():
    """Distinct metadata values present across the knowledge base, so the agent
    (or UI) can pick a filter that actually matches something."""
    return {"ok": True, "filters": available_filters()}


@app.post("/api/tools/list", operation_id="list_projects")
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
        scope = guess if score >= CONFIDENT else None
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
    where = f" for {scope_label}" if scope_label else ""
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
        "categories": categories,
        "projects": projects,
        "top_by_price": top_by_price,
        "highest_project": highest_project,
        "lowest_project": lowest_project,
        "highest_answer": highest_answer,
    }


def _offers_overview() -> list[dict]:
    """One summary row per stored offer file (id, client, category, price, ...)."""
    col = get_collection()
    out = []
    if col.count():
        for m in col.get(include=["metadatas"])["metadatas"]:
            raw = m.get("_raw")
            if not raw:
                continue
            r = json.loads(raw)
            ps = r.get("price_schedule") or {}
            total = None
            for k in ("final_price", "grand_total", "total"):
                if isinstance(ps.get(k), (int, float)):
                    total = ps[k]
                    break
            if total is None:
                nums = [v for k, v in ps.items() if isinstance(v, (int, float))]
                total = sum(nums) if nums else None
            out.append({
                "id": r.get("id"), "category": r.get("category"),
                "client": r.get("client"), "ref": r.get("ref"), "date": r.get("date"),
                "source_file": r.get("source_file"),
                "n_given": len(r.get("given_data") or {}),
                "n_tech": len(r.get("technical_details") or {}),
                "price_total": total, "currency": ps.get("currency", "INR"),
            })
    out.sort(key=lambda x: (x.get("category") or "", x.get("id") or ""))
    return out


@app.get("/api/offers")
def list_offers():
    """Overview of every stored offer file — powers the Knowledge Base page."""
    out = _offers_overview()
    return {"count": len(out), "offers": out}


@app.get("/api/knowledge/overview")
def knowledge_overview():
    """Structured view of the engineering knowledge base — the deterministic
    'Database Organization' surface for the Knowledge Base page. Every count is
    computed from what is actually stored (no invented numbers).

    - collections: the platform's content buckets (Historical Projects is the
      populated corpus today; the rest are structured and ingestion-ready).
    - equipment: the offer corpus organised by equipment category, with counts.
    - stats + facets: totals, distinct clients/manufacturers, date coverage.
    """
    col = get_collection()
    metas = col.get(include=["metadatas"])["metadatas"] if col.count() else []
    offers = [m for m in metas if m.get("type") == "offer"]
    documents = [m for m in metas if m.get("type") == "document"]

    # equipment breakdown of the offer corpus
    cats: dict[str, int] = {}
    for m in offers:
        c = m.get("category")
        if c:
            cats[c] = cats.get(c, 0) + 1
    equipment = [{"key": c, "label": category_label(c), "count": n}
                 for c, n in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))]

    # facets
    clients = sorted({m.get("client") for m in offers if m.get("client")})
    manufacturers = sorted({m.get("vendor") for m in offers if m.get("vendor")})
    dates = sorted(m.get("date") for m in offers if m.get("date"))

    # document collections (type=document) grouped by doc_category, if any ingested
    doc_by_cat: dict[str, int] = {}
    for m in documents:
        dc = m.get("doc_category") or m.get("kind") or "document"
        doc_by_cat[dc] = doc_by_cat.get(dc, 0) + 1

    from .catalog import CATEGORY_PROFILES
    n_rules = len(CATEGORY_PROFILES)

    last_offer = dates[-1] if dates else None
    collections = [
        {"key": "historical_projects", "label": "Historical Projects", "count": len(offers),
         "state": "live", "icon": "📁", "last_updated": last_offer,
         "desc": "Real client offers extracted into the platform — the grounding corpus, organised by equipment."},
        {"key": "specifications", "label": "Specifications", "count": 0,
         "state": "on_demand", "icon": "📐", "last_updated": None,
         "desc": "Generated on demand by the Engineering Agent from rules + history."},
        {"key": "quotations", "label": "Quotations", "count": 0,
         "state": "on_demand", "icon": "🧾", "last_updated": None,
         "desc": "Generated on demand by the Quotation Agent — deterministic pricing."},
        {"key": "standards", "label": "Standards", "count": doc_by_cat.get("standard", 0),
         "state": "ingest", "icon": "📖", "last_updated": None,
         "desc": "Design codes & industry standards — ready for document ingestion."},
        {"key": "vendor_catalogues", "label": "Vendor Catalogues", "count": doc_by_cat.get("catalogue", 0),
         "state": "ingest", "icon": "📚", "last_updated": None,
         "desc": "Component & equipment catalogues from suppliers — ready for ingestion."},
        {"key": "drawings", "label": "Drawings", "count": doc_by_cat.get("drawing", 0),
         "state": "roadmap", "icon": "✏️", "last_updated": None,
         "desc": "CAD / GA drawings — the CAD Engineering Agent is on the roadmap."},
        {"key": "rules", "label": "Engineering Rules", "count": n_rules,
         "state": "engine", "icon": "⚙️", "last_updated": None,
         "desc": "Equipment profiles + sizing rules baked into the deterministic engine."},
    ]

    return {
        "collections": collections,
        "equipment": equipment,
        "stats": {
            "records": len(offers),
            "documents": len(documents),
            "clients": len(clients),
            "manufacturers": len(manufacturers),
            "equipment_types": len(equipment),
            "date_from": dates[0] if dates else None,
            "date_to": dates[-1] if dates else None,
        },
        "manufacturers": manufacturers,
        # the Chroma metadata schema this corpus is organised by
        "metadata_fields": ["Equipment", "Category", "Manufacturer", "Project / Client",
                            "Reference", "Date", "Document Type", "Source"],
    }


@app.get("/api/offers/{offer_id}")
def get_offer(offer_id: str):
    """Full extracted record for one file — powers the Knowledge Base detail view."""
    col = get_collection()
    if col.count():
        for m in col.get(include=["metadatas"])["metadatas"]:
            raw = m.get("_raw")
            if raw:
                r = json.loads(raw)
                if r.get("id") == offer_id:
                    return r
    return {"error": "not found", "id": offer_id}


# --- file uploads (extraction pipeline is the next phase) -------------------
UPLOAD_DIR = config.BASE_DIR / "uploads"
_KIND = {"pdf": "PDF document", "dxf": "CAD (DXF)", "dwg": "CAD (DWG)",
         "png": "Image", "jpg": "Image", "jpeg": "Image",
         "xlsx": "Spreadsheet", "docx": "Document"}


def _file_kind(name: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return _KIND.get(ext, (ext.upper() + " file") if ext else "File")


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)):
    """Store an uploaded offer/CAD file. Automatic extraction is a later phase —
    for now the file is saved and queued."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / Path(file.filename).name       # strip any path components
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "filename": dest.name, "size": dest.stat().st_size,
            "kind": _file_kind(dest.name), "status": "uploaded"}


@app.get("/api/uploads")
def list_uploads():
    UPLOAD_DIR.mkdir(exist_ok=True)
    files = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            files.append({"filename": p.name, "size": p.stat().st_size,
                          "kind": _file_kind(p.name), "status": "uploaded"})
    return {"count": len(files), "files": files}


@app.post("/api/query/stream")
def query_stream(req: QueryRequest):
    """Same pipeline, but streams the answer token-by-token (Server-Sent Events).
    Emits {type:'token',v:...} chunks, then a {type:'done', payload:{...}} event
    with the full analysis/sources/flags once generation finishes."""
    sid = req.session_id or uuid.uuid4().hex[:12]
    history = session.get_history(sid)
    hits, analysis, grounded = _prepare(req.question, req.top_k, history)
    meta = _meta(req.question, sid, hits, analysis, grounded)

    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    def gen():
        final = {"answer": ""}
        for ev in stream_answer(req.question, hits, analysis, history):
            if ev["type"] == "token":
                yield sse(ev)
            else:                                   # type == "final"
                final = {k: v for k, v in ev.items() if k != "type"}
        session.append(sid, "user", req.question)
        session.append(sid, "assistant", final.get("answer", ""))
        yield sse({"type": "done", "payload": {**meta, **final}})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no",
                                      "Cache-Control": "no-cache"})


@app.get("/api/records")
def records():
    """All stored offer records (rebuilt from Chroma `_raw` metadata)."""
    col = get_collection()
    out = []
    for m in col.get(include=["metadatas"])["metadatas"]:
        raw = m.get("_raw")
        if raw:
            out.append(json.loads(raw))
    out.sort(key=lambda r: (r.get("category", ""), r.get("id", "")))
    return {"count": len(out), "records": out}


# --- a simple visual table view of the knowledge base -----------------------

def _render(value) -> str:
    if isinstance(value, dict):
        rows = "".join(
            f"<tr><td class='k'>{html.escape(str(k).replace('_', ' '))}</td>"
            f"<td>{_render(v)}</td></tr>"
            for k, v in value.items())
        return f"<table class='kv'>{rows}</table>"
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            cols = list({k for x in value for k in x})
            head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
            body = "".join(
                "<tr>" + "".join(f"<td>{_render(x.get(c, ''))}</td>" for c in cols) + "</tr>"
                for x in value)
            return f"<table class='lst'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        return "<br>".join(_render(x) for x in value)
    return html.escape(str(value))


@app.get("/records", response_class=HTMLResponse)
def records_page():
    data = records()
    cards = []
    for r in data["records"]:
        meta = " · ".join(filter(None, [
            f"<b>{html.escape(r.get('category', ''))}</b>",
            html.escape(r.get("client", "")),
            html.escape(r.get("ref", "")),
            html.escape(r.get("date", "")),
            html.escape(r.get("source_file", "")),
        ]))
        sections = []
        for key in ("given_data", "essential_equipment", "technical_details",
                    "price_schedule", "customer_scope_exclusions", "commercial_terms"):
            if r.get(key):
                sections.append(f"<h4>{key.replace('_', ' ').title()}</h4>{_render(r[key])}")
        cards.append(
            f"<div class='card'><div class='hd'>{html.escape(r.get('id', ''))} "
            f"<span class='ttl'>{html.escape(r.get('title', ''))}</span></div>"
            f"<div class='meta'>{meta}</div>{''.join(sections)}</div>")

    page = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>ATS Knowledge Base</title><style>
body{{background:#0b0f14;color:#e6edf3;font-family:Inter,Segoe UI,system-ui,sans-serif;margin:0;padding:24px;}}
h1{{font-size:22px;}} h4{{margin:14px 0 6px;color:#4f9cf9;font-size:13px;text-transform:uppercase;letter-spacing:.5px;}}
.card{{background:#131a23;border:1px solid #243140;border-radius:12px;padding:18px;margin:0 0 18px;}}
.hd{{font-weight:700;font-size:16px;}} .ttl{{color:#8b9aa9;font-weight:400;margin-left:8px;}}
.meta{{color:#8b9aa9;font-size:13px;margin:6px 0 10px;}}
table{{border-collapse:collapse;font-size:13px;margin:4px 0;}}
table.kv td,table.lst td,table.lst th{{border:1px solid #243140;padding:5px 9px;vertical-align:top;text-align:left;}}
table.kv td.k{{color:#8b9aa9;white-space:nowrap;width:200px;}}
table.lst th{{background:#1a232e;color:#8b9aa9;}}
.count{{color:#8b9aa9;}}
</style></head><body>
<h1>ATS Knowledge Base <span class='count'>— {data['count']} stored offers</span></h1>
{''.join(cards)}
</body></html>"""
    return page
