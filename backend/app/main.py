"""FastAPI app — the ATS Engineering Assistant backend.

Pipeline per query:  question -> understand -> retrieve -> analyze -> LLM -> answer
"""
import html
import json

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

import shutil
import uuid
from pathlib import Path

from . import config, jobs, session
from .analysis import essential_present, requirement_completeness
from .analytics import record_detail
from .resolver import ATS, CONSULTING, resolve
from .prompt import spec_summary, spec_writeup
from .quotation import build_quotation
from .quotation_pdf import render_quotation_pdf
from .catalog import get_profile
from .ingest import ingest_source
from .llm import generate_answer, stream_answer
from .retriever import (all_hits, entity_hits, has_offers, is_analytical,
                        is_comparison, is_data_lookup, is_overview,
                        references_existing_data, retrieve, summarize_retrieval)
from .store import get_collection
from .understand import contextualize, understand

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


def _prepare(question: str, top_k: int | None, history=None):
    """Shared pipeline: UNDERSTAND -> retrieve -> ANALYZE. Returns (hits, analysis,
    grounded). Used by both the streaming and non-streaming endpoints."""
    u = understand(question)
    structured = u.intent in ("specification", "quotation")

    # HYBRID ROUTING (the flagship): for a spec, decide by REQUIREMENT
    # COMPLETENESS, not by a manual mode switch —
    #   * essential sizing input present AND >= HYBRID_THRESHOLD of inputs given
    #     (or the user explicitly said "refer db")  -> Quotation Engineer
    #     (history + engineering rules + validation), and
    #   * otherwise -> Consulting Engineer (ask for the missing inputs, no guess).
    completeness, missing_inputs = 1.0, []
    use_data = False
    if structured:
        profile = get_profile(u.category)
        completeness, missing_inputs = requirement_completeness(profile, u.parameters)
        essential = essential_present(profile, u.parameters)
        refer_db = references_existing_data(question)
        # Quotation is only possible if the category is BUILDABLE — it has
        # engineering rules or at least one stored offer. Otherwise (e.g. an oven
        # with no rules and no history yet) we consult conceptually instead of
        # hitting a dead end.
        # ADAPTABLE = we can actually ENGINEER/scale this category (it has rules,
        # field rules, or a sizing driver with scalable fields). A category with
        # only historical offers but no adaptation logic would merely COPY the
        # nearest project — so we do NOT auto-build it from data. Instead we reason
        # from engineering knowledge (Consulting), treating stored offers as
        # reference evidence, and only build from data when the user explicitly
        # asks ("refer db").
        adaptable = bool(profile and (
            profile.get("rules") or profile.get("field_rules")
            or (profile.get("scale_driver") and profile.get("scalable"))))
        buildable = adaptable or has_offers(u.category)
        wants_quote = u.intent == "quotation"
        use_data = buildable and (
            refer_db
            or (adaptable and essential and completeness >= config.HYBRID_THRESHOLD)
            or (wants_quote and essential))

    # Multi-turn memory: resolve a short/pronoun follow-up ("compare it with the
    # other") against the previous question so retrieval finds the right records.
    search_q = question if structured else contextualize(question, history)

    where = {"category": u.category} if (u.category and use_data) else None
    hits = retrieve(search_q, top_k, where=where)

    mode = None
    data_lookup = False
    if not structured:
        analytical = is_analytical(search_q)
        comparison = (u.intent == "comparison") or is_comparison(search_q)
        named = entity_hits(search_q)
        # Grounding set:
        #  - comparison of NAMED clients -> just those records; else the whole KB;
        #  - a SPECIFIC named client/offer (even if worded like an overview, e.g.
        #    "what did C2C order") -> ONLY that client's records, so the model
        #    isn't handed the whole corpus and can't blend unrelated clients;
        #  - analytics / overview enumeration -> the WHOLE KB;
        #  - otherwise the semantic hits already suffice.
        scoped = False
        if comparison:
            extra = named if len(named) >= 2 else all_hits()
        elif named and not analytical:
            extra, scoped = named, True
        elif analytical or is_overview(search_q):
            extra = all_hits()
        else:
            extra = named
        if extra:
            if scoped:                          # replace: don't dilute with neighbours
                hits = extra
            else:
                seen = {h["id"] for h in extra}
                hits = extra + [h for h in hits if h["id"] not in seen]
        mode = "analytical" if analytical else "comparison" if comparison else None
        # Verify only plain direct lookups — NOT computed analytics/comparisons
        # (their result isn't a literal stored fact, and verify could mangle the
        # table). Those rely on full-data grounding + low temperature instead.
        data_lookup = is_data_lookup(search_q) and mode is None

    # One resolver, two policies (the ONLY place the product split lives):
    #   Consulting Engineer  -> knowledge policy (ask for missing inputs, no guess)
    #   ATS Engineering Expert -> data policy (history + rules + validation)
    if structured and not use_data:
        analysis = resolve(question, hits, u, CONSULTING)
        analysis["completeness"] = round(completeness * 100)
        analysis["completeness_missing"] = missing_inputs
    else:
        analysis = resolve(question, hits, u, ATS)
        if structured:
            analysis["spec_mode"] = "data"
            # Quotation Agent: layer a budgetary quote on top of the data-mode spec
            # (deterministic price + scope + terms). Additive — the spec is unchanged.
            if u.intent == "quotation":
                quote = build_quotation(analysis, dict(u.parameters))
                if quote:
                    analysis["quotation"] = quote

    relevant = [h for h in hits if h["score"] >= config.RELEVANCE_THRESHOLD]
    grounded = use_data if structured else bool(relevant or mode or data_lookup)
    analysis["grounded"] = grounded
    analysis["data_lookup"] = data_lookup           # gates the self-verify pass
    analysis["mode"] = mode                         # analytical / comparison / None
    if mode:
        analysis["intent"] = mode                   # nicer badge + tailored prompt
    return hits, analysis, grounded


def _meta(question, sid, hits, analysis, grounded):
    sources = [
        {"id": h["id"], "title": h["title"], "type": h["type"],
         "score": h["score"], "source_file": h["record"].get("source_file")}
        for h in hits
    ]
    # Only cite documents that actually influenced the result:
    #  - data-mode spec -> just the offer it was built from;
    #  - knowledge-mode spec -> none (designed from general knowledge).
    sm = analysis.get("spec_mode")
    if sm == "knowledge":
        sources = []
    elif sm == "data":
        chosen = analysis.get("exact_match") or analysis.get("nearest_match")
        sources = [s for s in sources if s["id"] == chosen] or sources[:1]

    return {
        "session_id": sid,
        "question": question,
        "intent": analysis["intent"],
        "category": analysis["category"],
        "category_label": analysis["category_label"],
        "confidence": analysis.get("confidence_label"),
        "grounded": grounded,
        "retrieval_steps": summarize_retrieval(hits),
        "analysis": analysis,
        "quotation": analysis.get("quotation"),   # budgetary quote (quotation intent)
        "sources": sources,
    }


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


# --- Tool endpoints for the Flowise Engineering Agent -----------------------
# Flowise Custom Tools POST natural language here; Python does ALL the reasoning
# and returns clean JSON (structured + a deterministic `text`). The Flowise LLM
# narrates the result — it never computes a number itself.

def _tool_q(payload: dict) -> str:
    for k in ("question", "query", "text", "input", "q"):
        if payload.get(k):
            return str(payload[k])
    return ""


def _spec_text(a: dict) -> str:
    """A deterministic text summary of a spec/analysis for the agent to narrate."""
    if a.get("spec_mode") == "data":
        return spec_writeup(a) if a.get("technical_details") else spec_summary(a)
    given = "; ".join(f"{g['label']}: {g['value']}" for g in a.get("given_data", [])) or "only the equipment type"
    miss = ", ".join(a.get("completeness_missing") or []) or "none"
    return (f"Known inputs: {given}. Still required before detailed design: {miss}. "
            f"Design from engineering knowledge; do not copy historical values.")


@app.post("/api/tools/spec")
def tool_spec(payload: dict = Body(...)):
    """Requirement -> engineering specification (deterministic + structured)."""
    q = _tool_q(payload)
    _, a, _ = _prepare(q, top_k=8, history=[])
    return {
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


@app.post("/api/tools/quote")
def tool_quote(payload: dict = Body(...)):
    """Requirement -> budgetary quotation (deterministic pricing from history)."""
    q = _tool_q(payload)
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


@app.post("/api/tools/lookup")
def tool_lookup(payload: dict = Body(...)):
    """Named client / offer -> exactly the data extracted from that file(s)."""
    q = _tool_q(payload)
    text = record_detail(q)
    recs, seen = [], set()
    for h in entity_hits(q):
        if h["id"] in seen:
            continue
        seen.add(h["id"])
        r = h["record"]
        recs.append({"id": r.get("id"), "client": r.get("client"),
                     "category": r.get("category"), "source_file": r.get("source_file"),
                     "given_data": r.get("given_data"),
                     "technical_details": r.get("technical_details"),
                     "price_schedule": r.get("price_schedule")})
    if not recs:
        return {"ok": False, "message": "No matching client or offer found."}
    return {"ok": True, "text": text, "records": recs[:4]}


@app.get("/api/offers")
def list_offers():
    """Overview of every stored offer file — powers the Knowledge Base page."""
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
    return {"count": len(out), "offers": out}


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
