"""Helpers shared by more than one router.

Moved verbatim from `main.py` when it was split; the behaviour, and therefore
every byte of every response, is unchanged."""
from ..agent_router import prepare as _prepare
from ..classify import classify_equipment
from ..prompt import spec_summary
from ..prompt import spec_writeup
from ..resolver import ATS
from ..resolver import resolve
from ..retriever import retrieve
from ..schema import QueryUnderstanding
from ..store import get_collection, offer_records
from typing import Optional
import json
import re


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

    # ENGINEERING REVIEW, stated BEFORE the numbers it qualifies. It was
    # originally appended at the end, and llama3.1:8b reliably truncated the
    # tail when printing spec_markdown verbatim (1997 chars in, 1781 out) — so
    # the warning existed in the JSON and never reached the reader. Position is
    # the structural fix; a prompt rule would be the fragile one.
    release = resp.get("release") or {}
    warns = [c.get("message") for c in (resp.get("validation") or [])
             if c.get("level") == "warn"]
    if release.get("status") or warns:
        L.append("**Engineering Review**")
        if release.get("status"):
            L.append(f"- Release status: **{release['status']}**")
        for w in warns:
            L.append(f"- ⚠ {w}")
        if release.get("gaps"):
            L.append(f"- {len(release['gaps'])} field(s) awaiting our engineering: "
                     f"{', '.join(release['gaps'][:6])}"
                     f"{'...' if len(release['gaps']) > 6 else ''}")
        if release.get("questions"):
            L.append(f"- {len(release['questions'])} item(s) for the customer to "
                     f"confirm: {', '.join(release['questions'][:6])}")
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
        L.append("| Parameter | Value | Basis / Calculation |")
        L.append("| --- | --- | --- |")
        for t in spec_rows:
            # Show the derivation (the formula for a calculated value, or the
            # offer it was reused/scaled from) — falling back to the short origin
            # label only if no reason is present. This is what tells the engineer
            # HOW the number was arrived at, e.g. "face area 4x4 x velocity 0.45 ...".
            basis = t.get("reason") or t.get("origin")
            L.append(f"| {esc(t.get('label'))} | {esc(t.get('value'))} | {esc(basis)} |")
        L.append("")

    miss = resp.get("missing_inputs") or []
    if miss:
        L.append(f"**To confirm before detailed design:** {', '.join(miss)}")
        L.append("")

    n_src = len(resp.get("sources") or [])
    basis = f"Grounded in {n_src} historical project(s). " if n_src else ""
    L.append(f"_{basis}Engineer-reviewed draft — not a released design._")
    return "\n".join(L)


def _spec_bom(a: dict) -> dict:
    """Bill of materials for a resolved analysis, or {} if it has no rows."""
    if not (a.get("technical_details") or []):
        return {}
    from ..bom import build_bom
    return build_bom({"category": a.get("category"),
                      "category_label": a.get("category_label"),
                      "geometry": _spec_geometry(a),
                      "technical_details": a.get("technical_details") or []})


def _spec_geometry(a: dict) -> dict:
    """Machine-readable geometry for the 2D drawing generator: the numeric
    envelope (mm) plus the status of every geometry-kind template field. Only
    real numeric dimensions are emitted — a dimension with no client value / rule
    is reported as TBD, never guessed. The drawing consumes this, not the prose
    table. Fills out as engineering calcs land (they output numbers we keep here)."""
    params = (a.get("understanding") or {}).get("parameters") or {}

    def to_mm(key):
        v = params.get(key)
        try:
            return round(float(v) * 1000)   # stored in metres -> mm
        except (TypeError, ValueError):
            return None

    L, W, H = to_mm("length_m"), to_mm("width_m"), to_mm("height_m")
    env = {"length": L, "width": W, "height": H}
    have = [x for x in (L, W, H) if x is not None]
    src = "given" if len(have) == 3 else ("partial" if have else "tbd")

    # Some categories never state L x W x H — a vertical spray tower is
    # specified by tower diameter with its height computed by the rule engine.
    # The ENGINEERING layer owns that model (it also decides WHICH machine the
    # category holds), so the specification and the drawing consume one resolved
    # geometry instead of each deciding for itself.
    from ..engineering.geometry_service import resolve_geometry
    geo = resolve_geometry(a.get("category"), a.get("technical_details") or [], params)
    if len(have) < 3 and geo.envelope:
        env, src = geo.envelope, "derived"
    fields = [
        {"label": t.get("label"), "value": t.get("value"),
         "status": "tbd" if t.get("origin") == "tbd" else "resolved"}
        for t in (a.get("technical_details") or []) if t.get("kind") == "geometry"
    ]
    ready = all(env.get(k) is not None for k in ("length", "width", "height"))
    out = {"envelope_mm": env, "envelope_source": src,
           "ready": ready, "fields": fields}
    # The resolved equipment TYPE travels with the geometry so the renderer never
    # has to infer what it is drawing from spec row labels.
    if geo.equipment_type:
        out["equipment_type"] = geo.equipment_type
    if geo.basis and src == "derived":
        out["basis"] = geo.basis
    if geo.conflicts:
        out["conflicts"] = list(geo.conflicts)
    return out

def _spec_for_drawing(q: str, analysis: Optional[dict] = None) -> dict:
    """Resolve a requirement into the subset of the spec the drawing consumes.

    `analysis` lets a caller that has ALREADY resolved the requirement hand the
    result in rather than paying for a second resolution. The package builder
    does exactly that: it resolves once and derives the specification, the
    drawing, the BOM and the quotation from that one analysis.

    That is not only faster. The package layer's whole guarantee is that its
    documents cannot disagree because they come from ONE resolution — and
    resolving twice quietly reintroduced the possibility they might, since
    `understand()` can take an LLM path for a requirement the regex cannot fully
    parse. Reusing the analysis makes the guarantee true by construction.
    """
    a = analysis if analysis is not None else _prepare(q, top_k=8, history=[])[1]
    return {
        "category": a.get("category"),
        "category_label": a.get("category_label"),
        "geometry": _spec_geometry(a),
        "technical_details": [
            {"label": t.get("label"), "value": t.get("value"),
             "origin": t.get("origin"), "kind": t.get("kind"),
             # The requirement STATE travels with the row. It is a reading of
             # the provenance the row already carries, so dropping it here only
             # forced every consumer to re-derive the same partition from
             # `origin` — and the drawing layer, which decides what it may put a
             # dimension on, is exactly the consumer that must not guess.
             "state": t.get("state"),
             # `parts` carries a composite field's real sub-values (a powder
             # plant's booth / oven / conveyor module sizes). Dropping it here
             # would force the glyph to re-parse them back out of the display
             # string — a second parser that could drift from the spec.
             **({"parts": t["parts"]} if t.get("parts") else {})}
            for t in (a.get("technical_details") or [])
        ],
    }

def _studio_spec(payload: dict) -> tuple[Optional[dict], str, Optional[dict]]:
    """Studio payload -> (spec, requirement, error). Shared by render and export
    so an exported sheet is built from exactly the same resolution as the one
    on screen."""
    category = str(payload.get("category") or "").strip()
    values = payload.get("values") or {}
    if not category:
        return None, "", {"ok": False, "error": "Select an equipment category."}

    from ..catalog import CATEGORY_PROFILES
    profile = CATEGORY_PROFILES.get(category)
    if not profile:
        return None, "", {"ok": False, "error": f"Unknown category '{category}'."}

    # The studio already HAS structured inputs, so they go straight into the
    # resolver rather than being rendered to a sentence and re-parsed — a
    # round-trip through natural language silently loses values whose phrasing
    # the extractor does not recognise. Same resolver as the chat path, so the
    # drawing can never disagree with the spec; only the input route differs.
    from ..drawing.fields import coerce as coerce_fields
    params = coerce_fields(values)

    question = " ".join([str(profile.get("label") or category).lower()]
                        + [f"{k}={v}" for k, v in params.items()])
    u = QueryUnderstanding(intent="specification", category=category,
                           parameters=dict(params), source="form")
    a = resolve(question, retrieve(question, top_k=8, where={"category": category}),
                u, ATS)
    a["spec_mode"] = "data"
    spec = {
        "category": category,
        "category_label": profile.get("label") or category,
        "geometry": _spec_geometry(a),
        "technical_details": [
            {"label": t.get("label"), "value": t.get("value"),
             "origin": t.get("origin"), "kind": t.get("kind"),
             # `parts` carries a composite field's real sub-values (a powder
             # plant's booth / oven / conveyor module sizes). Dropping it here
             # would force the glyph to re-parse them back out of the display
             # string — a second parser that could drift from the spec.
             **({"parts": t["parts"]} if t.get("parts") else {})}
            for t in (a.get("technical_details") or [])
        ],
    }
    # Anything the engineer typed in by hand on the studio's specification
    # panel. Carried with origin "given" — it is the customer's/engineer's own
    # stated value, exactly like a requirement, and is never presented as
    # something the engine calculated.
    for extra in payload.get("extra_rows") or []:
        label = str(extra.get("label") or "").strip()
        value = str(extra.get("value") or "").strip()
        if label and value:
            spec["technical_details"].append(
                {"label": label, "value": value, "origin": "given",
                 "kind": None, "manual": True})
    return spec, question, None


def _title_block(payload: dict) -> dict:
    """Title-block overrides the studio supplies; blanks keep the defaults."""
    keys = ("title", "client", "ref", "drawn", "checked", "rev", "date", "status")
    return {k: payload[k] for k in keys if payload.get(k)}


# Shared by the data views and the `list_projects` agent tool.
def _offers_overview() -> list[dict]:
    """One summary row per stored offer file (id, client, category, price, ...)."""
    out = []
    for r in offer_records():
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
