"""Deterministic analytics over the stored offers.

Counting, listing and per-category breakdowns are computed IN CODE, never by the
LLM — a small model miscounts a corpus of records (it sees a semantic subset and
double-counts sub-components). For "how many / which clients / list all X" we
answer exactly from the knowledge base; open-ended analytics still go to the LLM.
"""
import json
import re
from collections import Counter

from .catalog import get_profile, label_for
from .classify import CONFIDENT, classify_equipment
from .retriever import _names_stored_client, entity_hits
from .store import get_collection

_CAT_LABEL = {
    "wet_scrubber": "Wet Scrubber", "paint_booth": "Paint Booth",
    "dust_collector": "Dust Collector", "hot_air_oven": "Hot Air Oven",
    "powder_coating_plant": "Powder Coating Plant", "fume_extraction": "Fume Extraction",
    "pretreatment_plant": "Pretreatment Plant", "blast_booth": "Blast Booth",
    "conveyor": "Conveyor", "ducting": "Ducting",
}


def _label(cat: str) -> str:
    if cat in _CAT_LABEL:
        return _CAT_LABEL[cat]
    p = get_profile(cat)
    return p["label"] if p else (cat or "Other").replace("_", " ").title()


def _records() -> list[dict]:
    col = get_collection()
    if col.count() == 0:
        return []
    out = []
    for m in col.get(include=["metadatas"])["metadatas"]:
        raw = m.get("_raw")
        if raw:
            out.append(json.loads(raw))
    return out


def _driver(rec: dict):
    """A short 'headline' value for listing an offer (airflow, size, etc.)."""
    gd = rec.get("given_data", {}) or {}
    for k in ("air_volume_cfm", "air_volume_cmh"):
        if k in gd:
            unit = "CFM" if k.endswith("cfm") else "CMH"
            return f"{gd[k]} {unit}"
    if gd.get("length_m") and gd.get("width_m"):
        return f"{gd['length_m']} x {gd['width_m']} m"
    return None


_ASKS_CLIENTS = re.compile(r"\b(client|clients|customer|customers)\b", re.I)
_BREAKDOWN = re.compile(
    r"\b(each|every|per)\s+(type|categor\w+|equipment)|by\s+(type|categor\w+)|"
    r"breakdown|all\s+(types?|categor\w+|equipment)|equipment\s+types?\b", re.I)
_LIST = re.compile(r"\b(list|show|name|display|give me)\b", re.I)
_COUNT = re.compile(r"\b(how many|number of|count|total|how much)\b", re.I)


def deterministic_analytics(question: str) -> str | None:
    """Exact answer for count/list/breakdown/client questions, else None."""
    q = (question or "").strip()
    # A question that NAMES a specific stored client/offer is a RECORD lookup,
    # not a corpus aggregate — never answer it with the client list / breakdown
    # (that hijack is why "given data of C2C" used to print all clients).
    if _names_stored_client(q):
        return None
    if not (_ASKS_CLIENTS.search(q) or _COUNT.search(q) or _LIST.search(q)
            or _BREAKDOWN.search(q)):
        return None
    recs = _records()
    if not recs:
        return None
    by_cat = Counter(r.get("category", "other") for r in recs)
    total = sum(by_cat.values())

    # 1) clients / customers
    if _ASKS_CLIENTS.search(q):
        clients = sorted({r.get("client") for r in recs if r.get("client")})
        L = [f"**{len(clients)} clients** are in the knowledge base:", ""]
        L += [f"- {c}" for c in clients]
        return "\n".join(L)

    cat, score = classify_equipment(q)
    specific = cat and score >= CONFIDENT and not _BREAKDOWN.search(q)

    # 2) list all offers of a category
    if _LIST.search(q) and specific:
        rows = [r for r in recs if r.get("category") == cat]
        L = [f"**{len(rows)} {_label(cat)} offer(s):**", ""]
        for r in rows:
            drv = _driver(r)
            L.append(f"- **{r.get('id')}** - {r.get('client', 'n/a')}"
                     + (f" ({drv})" if drv else ""))
        return "\n".join(L)

    # 3) count of a specific category
    if _COUNT.search(q) and specific:
        n = by_cat.get(cat, 0)
        return f"There are **{n} {_label(cat)}** offer(s) in the knowledge base."

    # 4) breakdown by category (or plain total)
    if _BREAKDOWN.search(q) or _COUNT.search(q) or _LIST.search(q):
        L = [f"**{total} offers** in the knowledge base, by equipment type:", ""]
        L += [f"- {_label(c)}: {n}" for c, n in by_cat.most_common()]
        return "\n".join(L)
    return None


# --- per-record detail: exactly the data extracted from one offer file --------

# The user is asking to SEE a specific record's stored/extracted data.
_DETAIL = re.compile(
    r"\b(given\s*data|technical(\s*details?)?|tech\s*details?|details?|"
    r"spec\w*|what\s+did|what\s+was|order(ed)?|scope|supplied|"
    r"the\s+data|extract\w*|stored|fields?|record)\b", re.I)


def _fmt_val(v) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_fmt_val(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(_fmt_val(x) for x in v)
    return str(v)


def _render_fields(category, d: dict) -> list[str]:
    return [f"- **{label_for(category, k)}:** {_fmt_val(v)}" for k, v in d.items()]


def record_detail(question: str) -> str | None:
    """Deterministic view of the data extracted from a NAMED client's offer(s):
    given data + technical details + price schedule, verbatim from the record.
    This both fixes the 'given data of <client>' lookup and shows exactly what we
    store per file. Returns None when no specific record is being asked about."""
    q = (question or "").strip()
    if not _DETAIL.search(q):
        return None
    hits = entity_hits(q)
    if not hits:
        return None
    seen, recs = set(), []
    for h in hits:                                   # de-dup, cap to keep it readable
        if h["id"] not in seen:
            seen.add(h["id"])
            recs.append(h["record"])
    recs = recs[:4]

    out = []
    if len(recs) > 1:
        clients = {r.get("client") for r in recs}
        who = next(iter(clients)) if len(clients) == 1 else "your query"
        out.append(f"Found **{len(recs)} separate offers on file** for {who} — each is "
                   f"its own project (not a comparison). Name a Ref or id to see just one.\n")
    for r in recs:
        cat = r.get("category")
        out.append(f"### {r.get('id')} - {r.get('client', 'n/a')}")
        meta = []
        for k, lbl in (("source_file", "Source file"), ("ref", "Ref"), ("date", "Date")):
            if r.get(k):
                meta.append(f"{lbl}: {r[k]}")
        if meta:
            out.append("_" + "  |  ".join(meta) + "_")
        gd = r.get("given_data") or {}
        if gd:
            out.append("\n**Given data (the requirement):**")
            out += _render_fields(cat, gd)
        td = r.get("technical_details") or {}
        if td:
            out.append("\n**Technical details (the engineered solution):**")
            out += _render_fields(cat, td)
        ps = r.get("price_schedule") or {}
        items = [f"{k}: {ps.get('currency', 'INR')} {v:,}" if isinstance(v, (int, float))
                 else f"{k}: {v}" for k, v in ps.items() if k != "currency"]
        if items:
            out.append("\n**Price schedule:** " + "; ".join(items))
        out.append("")
    return "\n".join(out).strip()
