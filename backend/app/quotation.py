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
    return f"Q-{date.today():%Y%m%d}-DRAFT"


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

    return {
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
