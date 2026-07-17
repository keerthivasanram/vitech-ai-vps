"""Quotation assembly for the Quotation Agent.

A quotation is built ON TOP of the resolver's specification (the single source
of truth) — it re-derives NO engineering value. It layers on:
  * a scope of supply drawn straight from the spec's technical details,
  * a budgetary price (pricing.estimate_price — deterministic, from history),
  * standard commercial terms (templated wording, no invented numbers),
  * a combined confidence (weakest of spec vs price) and the source offers.

Human-in-the-loop: the result is flagged a DRAFT for an engineer to confirm.
"""
from datetime import date
from typing import Any, Optional

from .pricing import estimate_price

# Standard Vitech commercial terms — boilerplate wording only, no numbers invented.
TERMS = [
    ("Prices", "Ex-works; GST extra as applicable."),
    ("Validity", "30 days from date of offer."),
    ("Delivery", "6-8 weeks from technically & commercially clear order."),
    ("Payment", "50% advance along with PO, balance before dispatch."),
    ("Warranty", "12 months from supply against manufacturing defects."),
    ("Erection", "Supervision of erection & commissioning at extra cost unless stated."),
]


def _label(pct: int) -> str:
    return "High" if pct >= 80 else "Medium" if pct >= 60 else "Low"


def _headline(analysis: dict, price: dict) -> str:
    """A short one-line description, e.g. 'Wet Scrubber - 800 CFM x 4'."""
    name = analysis.get("category_label") or "Equipment"
    d = price.get("driver") or {}
    bits = []
    if d.get("value") is not None and d.get("key"):
        unit = d["key"].rsplit("_", 1)[-1].upper() if d["key"] != "floor_area" else "m2"
        val = d["value"]
        val = int(val) if isinstance(val, float) and val.is_integer() else round(val, 2)
        bits.append(f"{val} {unit}")
    if price.get("qty", 1) > 1:
        bits.append(f"x {price['qty']}")
    return f"{name} - {' '.join(bits)}" if bits else name


def _ref() -> str:
    # Structured house format; the running serial comes from the numbering
    # system later — kept as DRAFT so no fake sequence is implied.
    return f"VT/QTN/{date.today():%y%m%d}/DRAFT"


def build_quotation(analysis: dict, params: dict,
                    offers: Optional[list] = None) -> Optional[dict[str, Any]]:
    """Assemble a budgetary quotation from a resolver analysis. None if the
    category has no priced history to quote from."""
    category = analysis.get("category")
    if not category:
        return None
    price = estimate_price(category, params, offers)
    if price is None:
        return None

    # scope of supply = the spec's technical details, verbatim (no re-derivation)
    scope = [{"item": t.get("label"), "spec": t.get("value"), "origin": t.get("origin")}
             for t in (analysis.get("technical_details") or [])]

    # combined confidence = weakest link between the spec and the price
    spec_conf = analysis.get("confidence")           # 0..1 or None
    price_conf = price["confidence"]                 # 0..1
    combined = min(spec_conf, price_conf) if isinstance(spec_conf, (int, float)) else price_conf
    pct = round(combined * 100)

    basis = list(dict.fromkeys(                      # de-dup, keep order
        (price.get("basis") or [])
        + [b for b in [analysis.get("nearest_match")] if b]))

    quote = {
        "ref": _ref(),
        "date": f"{date.today():%d %b %Y}",
        "headline": _headline(analysis, price),
        "category": category,
        "category_label": analysis.get("category_label"),
        "given_data": analysis.get("given_data") or [],
        "scope": scope,
        "price": price,
        # preformatted for the agent to copy verbatim (never re-group digits)
        "price_display": price.get("amount_display"),
        "price_range_display": price.get("range_display"),
        "terms": TERMS,
        "confidence_pct": pct,
        "confidence_label": _label(pct),
        "basis_offers": basis,
        "draft": True,
        "note": "Budgetary draft generated from historical offers - for engineer review before issue.",
    }
    # a complete, ready-to-print quotation the agent outputs VERBATIM — so the
    # layout is deterministic and the LLM never re-assembles (or drops) it.
    quote["quotation_markdown"] = render_quotation_markdown(quote)
    return quote


# --- engineering-grade quotation template pieces (boilerplate, no invented data) ---
COMPANY_NAME = "VITECH ENVIRO SYSTEMS PVT. LTD."
COMPANY_TAGLINE = "Industrial Air-Pollution-Control & Surface-Finishing Solutions"

SCOPE_EXCLUSIONS = [
    "Civil, structural & foundation work",
    "Power cabling, earthing & electrical installation up to the control panel",
    "Compressed-air and water supply piping up to the equipment",
    "Effluent / drainage lines beyond the equipment battery limit",
    "Unloading, storage & shifting at site",
    "Any statutory approvals, consents or NOCs",
]

STANDARD_ASSUMPTIONS = [
    "Ambient temperature up to 40 °C at site",
    "Dust / gas concentration within normal design limits",
    "Single-shift operation",
    "Standard utilities (power, water, compressed air) available at the equipment",
    "Indoor installation on a level, load-bearing floor",
]

COMMERCIAL_NOTES = [
    "Prices are Ex-Works; GST extra as applicable.",
    "Packing, forwarding, transportation, insurance and loading/unloading at actuals unless stated.",
    "Offer validity: 30 days from the date of this quotation.",
]

# scope-of-supply component keywords -> a clean "includes" line
_COMPONENT_KEYWORDS = [
    ("scrubber", "Wet Scrubber unit"), ("booth", "Booth enclosure"), ("oven", "Oven / HAG"),
    ("blower", "Blower"), (" fan", "Fan"), ("pump", "Circulation pump"),
    ("demister", "Demister / eliminator"), ("eliminator", "Demister / eliminator"),
    ("nozzle", "Spray system"), ("spray", "Spray system"), ("tank", "Recirculation tank"),
    ("cartridge", "Filter cartridges"), ("bag", "Filter bags"), ("filter", "Filtration"),
    ("panel", "Control panel"), ("plc", "Control panel (PLC / HMI)"),
    ("conveyor", "Conveyor"), ("duct", "Ducting"), ("heater", "Heating system"),
    ("burner", "Burner / hot-air generator"), ("motor", "Drive motor"),
]


def _scope_includes(scope: list) -> list[str]:
    """Deterministic 'Scope includes' checklist derived from the engineered scope."""
    text = " ".join(f"{s.get('item', '')} {s.get('spec', '')}".lower() for s in scope)
    out: list[str] = []
    for kw, label in _COMPONENT_KEYWORDS:
        if kw.strip() in text and label not in out:
            out.append(label)
    if out:
        out.append("Base frame, supports & standard finish")
    return out


def render_quotation_markdown(quote: dict[str, Any]) -> str:
    """Render a quotation dict as a ready-to-print, engineering-grade Markdown
    quotation. Formatting lives in code (never the model) — the Quotation Agent
    prints this verbatim, so every quote has the same professional structure.

    Customer-facing: no confidence score, budget framed as a ±15% band.
    Company letterhead + serial number come from the PDF template later.
    """
    p = quote.get("price") or {}
    equip = quote.get("headline") or quote.get("category_label") or "Equipment"
    cat_label = quote.get("category_label") or "Equipment"
    L: list[str] = []

    # ── company header ──
    L.append(f"### {COMPANY_NAME}")
    L.append(f"_{COMPANY_TAGLINE}_")
    L.append("")
    L.append("**BUDGETARY QUOTATION — DRAFT**")
    L.append(f"Ref: {quote.get('ref', '-')}   |   Date: {quote.get('date', '-')}")
    L.append("")

    # ── customer block (fill-in for the reviewing engineer) ──
    L.append(f"**Customer:** (to be completed)")
    L.append(f"**Project:** {cat_label} System")
    L.append(f"**Location:** (to be completed)")
    L.append(f"**Attention:** (to be completed)")
    L.append(f"**Prepared by:** Applications Engineering Department")
    L.append("")
    L.append(f"**Equipment:** {equip}")
    L.append("")

    # ── technical specification (the engineered items) ──
    scope = [s for s in (quote.get("scope") or []) if s.get("origin") != "given"]
    if scope:
        L.append("**Technical Specification**")
        L.append("| Item | Specification |")
        L.append("| --- | --- |")
        for s in scope:
            item = str(s.get("item", "")).replace("|", "/")
            spec = str(s.get("spec", "")).replace("|", "/")
            L.append(f"| {item} | {spec} |")
        L.append("")

    # ── scope includes / excludes ──
    inc = _scope_includes(scope)
    if inc:
        L.append("**Scope of Supply — Includes**")
        for c in inc:
            L.append(f"- ✔ {c}")
        L.append("")
    L.append("**Scope Exclusions**")
    for e in SCOPE_EXCLUSIONS:
        L.append(f"- {e}")
    L.append("")

    # ── pricing (no confidence; budget as a ±15% band) ──
    L.append("**Pricing — budgetary, Ex-Works**")
    L.append("| Item | Amount |")
    L.append("| --- | --- |")
    if p.get("unit_price_display"):
        L.append(f"| Unit price | {p['unit_price_display']} |")
    L.append(f"| Quantity | {p.get('qty', 1)} nos |")
    L.append(f"| **Total (Ex-Works)** | **{quote.get('price_display') or p.get('amount_display', '-')}** |")
    L.append("")
    L.append("_Budgetary estimate — expected variation ±15%. GST extra as applicable._")
    L.append("")

    # ── delivery / warranty / payment ──
    L.append("**Delivery**")
    L.append("- 6–8 weeks from receipt of a technically & commercially clear PO and the advance payment.")
    L.append("")
    L.append("**Warranty**")
    L.append("- 12 months from commissioning or 18 months from dispatch, whichever is earlier, against manufacturing defects.")
    L.append("")
    L.append("**Payment**")
    L.append("- 50% advance along with PO; balance against dispatch documents.")
    L.append("")

    # ── commercial notes & assumptions ──
    L.append("**Commercial Notes**")
    for n in COMMERCIAL_NOTES:
        L.append(f"- {n}")
    L.append("")
    L.append("**Assumptions**")
    for a in STANDARD_ASSUMPTIONS:
        L.append(f"- {a}")
    L.append("")

    # ── signatory ──
    L.append(f"**For {COMPANY_NAME}**")
    L.append("Applications Engineering Department")
    L.append("")
    L.append("_Engineer-reviewed draft — not a released offer. Figures derived deterministically from historical offers._")
    return "\n".join(L)
