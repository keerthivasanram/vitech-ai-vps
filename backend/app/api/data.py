"""Read-only views over the knowledge base.

ORDER MATTERS: `/api/offers/by-source/{path}` must stay registered BEFORE
`/api/offers/{offer_id}`, or the literal path would be captured as an id."""
from fastapi import APIRouter
from ..analytics import _label as category_label
from ..store import get_collection, offer_records
from fastapi.responses import HTMLResponse
from pathlib import Path
import html
import json

from .support import _offers_overview

router = APIRouter()


@router.get("/api/offers/by-source/{source_file:path}")
def offer_by_source(source_file: str):
    """Full extracted record whose `source_file` matches — lets the chat open the
    content behind a specification's cited source file in the record inspector.
    Matches on the exact stored name, else on basename (case-insensitive)."""
    target = Path(source_file).name.strip().lower()
    for r in offer_records():
        sf = r.get("source_file")
        if sf and Path(str(sf)).name.strip().lower() == target:
            return r
    return {"error": "not found", "source_file": source_file}


@router.get("/api/offers")
def list_offers():
    """Overview of every stored offer file — powers the Knowledge Base page."""
    out = _offers_overview()
    return {"count": len(out), "offers": out}


@router.get("/api/knowledge/overview")
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

    from ..catalog import CATEGORY_PROFILES
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


@router.get("/api/offers/{offer_id}")
def get_offer(offer_id: str):
    """Full extracted record for one file — powers the Knowledge Base detail view."""
    for r in offer_records():
        if r.get("id") == offer_id:
            return r
    return {"error": "not found", "id": offer_id}

@router.get("/api/records")
def records():
    """All stored offer records (rebuilt from Chroma `_raw` metadata)."""
    out = list(offer_records())      # copy: sorting the shared cache would corrupt it
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


@router.get("/records", response_class=HTMLResponse)
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
