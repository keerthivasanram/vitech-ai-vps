"""Pricing intelligence for the Quotation Agent — *how the amount is fixed*.

Golden rule #2 stands: every number here is produced deterministically by code
from tunable constants + the company's own history. The LLM never invents a
price; it only *explains* the basis this module computes.

It layers three independent, deterministic price signals on top of the
history-scaling figure in `pricing.estimate_price` and reconciles them:

  A. HISTORICAL scaling ....... pricing.estimate_price (the headline anchor)
  B. COST-PLUS build-up ....... material + fabrication + bought-outs + overhead
                                + target margin  (the estimator's / competitor's
                                cost-plus method) — from the SEED_* constants
  C. MARKET benchmark ......... the ₹-per-driver band across Vitech's priced
                                offers, and where this quote sits in it
                                (aggressive / market / premium)

The reconciliation keeps the HISTORICAL figure as the recommended headline (so
existing verified quotes are unchanged) and adds a plain-English rationale plus
a "pricing basis" block the agent can present when asked *why this price* or
*how competitors price this*.

CLIENT-EXTENSION POINTS (seeded with industry-plausible defaults — replace with
the real rate card / margin policy when available; nothing else needs to change):
  SEED_MATERIAL_RATES, SEED_DENSITY, SEED_FABRICATION_RATE, SEED_OVERHEAD_PCT,
  SEED_TARGET_MARGIN_PCT, MARGIN_BANDS, SEED_MOTOR_RATE, SEED_PUMP_RATE,
  SEED_BOP_PCT, SEED_STRUCTURE_FACTOR, SEED_KG_PER_DRIVER.
"""
import re
from typing import Any, Optional

from .pricing import (_driver_value, _offer_records, _qty, _round_price,
                      _total, inr_display)

# ── SEED constants (₹, all TUNABLE — refine with the client's real numbers) ──
SEED_MATERIAL_RATES = {          # ₹/kg of fabricated sheet (incl. wastage)
    "SS-316": 480.0, "SS-304": 320.0, "SS": 320.0,
    "MS": 95.0, "PP": 260.0, "GI": 130.0, "default": 150.0,
}
SEED_FABRICATION_RATE = 85.0     # ₹/kg — cutting, forming, welding, finishing labour
SEED_STRUCTURE_FACTOR = 0.35     # supports / frame / stiffeners as a fraction of shell wt
SEED_BOP_PCT = 0.15              # bought-out parts (controls, spray, fasteners) on works cost
SEED_OVERHEAD_PCT = 0.18         # factory + selling overhead on works cost
SEED_TARGET_MARGIN_PCT = 0.20    # default gross margin over total cost
SEED_MOTOR_RATE = 4500.0         # ₹/HP — motor + starter share of bought-outs
SEED_PUMP_RATE = 6000.0          # ₹/HP — circulation pump share

MARGIN_BANDS = {                 # gross-margin policy by market positioning
    "aggressive": 0.12, "market": 0.20, "premium": 0.30,
}

# Specific weight per unit of sizing driver (kg per driver-unit), per category.
# Seeds only — the moment the client shares component weights these get calibrated.
SEED_KG_PER_DRIVER = {
    "wet_scrubber": 0.60,        # kg per CFM
    "dust_collector": 0.22,      # kg per CMH
    "fume_extraction": 0.20,     # kg per CMH
    "paint_booth": 180.0,        # kg per m2 of floor area
    "blast_booth": 210.0,        # kg per m2
    "hot_air_oven": 240.0,       # kg per m2 of floor area
    "powder_coating_plant": 170.0,
}
# Default material of construction per category (drives the ₹/kg rate chosen).
SEED_CATEGORY_MOC = {
    "wet_scrubber": "SS-304", "dust_collector": "MS", "fume_extraction": "MS",
    "paint_booth": "MS", "blast_booth": "MS", "hot_air_oven": "MS",
    "powder_coating_plant": "MS",
}


def _round_rate(v: float) -> int:
    """Round a small per-driver rate (e.g. ₹/CFM) to a readable step — the coarse
    `_round_price` (₹1,000 steps) would collapse a ₹850/CFM rate to ₹1,000 or ₹0."""
    v = max(0.0, float(v))
    if v < 100:
        step = 5
    elif v < 1_000:
        step = 25
    elif v < 10_000:
        step = 250
    else:
        step = 1_000
    return int(round(v / step) * step)


def _material_rate(moc: str) -> float:
    key = (moc or "").upper()
    for tag, rate in SEED_MATERIAL_RATES.items():
        if tag.upper() in key:
            return rate
    return SEED_MATERIAL_RATES["default"]


def _hp_from_analysis(analysis: dict, needle: str) -> float:
    """First numeric HP off a technical-details row whose label mentions `needle`."""
    for t in (analysis.get("technical_details") or []):
        label = str(t.get("label", "")).lower()
        if needle in label and "hp" in label:
            m = re.search(r"[-+]?\d*\.?\d+", str(t.get("value", "")))
            if m:
                try:
                    return float(m.group())
                except ValueError:
                    pass
    return 0.0


def cost_plus_estimate(category: str, params: dict,
                       analysis: dict) -> Optional[dict[str, Any]]:
    """Bottom-up cost-plus price for ONE unit, with a transparent build-up.

    Returns None when the category has no weight basis (no driver / geometry).
    """
    driver_val, dkey = _driver_value(category, params)
    kg_per = SEED_KG_PER_DRIVER.get(category)
    if driver_val is None or not kg_per:
        return None

    shell_kg = driver_val * kg_per
    total_kg = shell_kg * (1 + SEED_STRUCTURE_FACTOR)

    moc = SEED_CATEGORY_MOC.get(category, "MS")
    material = total_kg * _material_rate(moc)
    fabrication = total_kg * SEED_FABRICATION_RATE

    motor_hp = _hp_from_analysis(analysis, "motor") or _hp_from_analysis(analysis, "blower")
    pump_hp = _hp_from_analysis(analysis, "pump")
    bought_out = motor_hp * SEED_MOTOR_RATE + pump_hp * SEED_PUMP_RATE

    works = material + fabrication + bought_out
    bop = works * SEED_BOP_PCT
    works += bop
    overhead = works * SEED_OVERHEAD_PCT
    cost = works + overhead
    margin = SEED_TARGET_MARGIN_PCT
    price = cost * (1 + margin)

    def row(label, amount):
        return {"label": label, "amount": round(amount),
                "display": inr_display(amount)}

    breakdown = [
        row(f"Material ({moc}, ~{round(total_kg)} kg @ {inr_display(_material_rate(moc))}/kg)", material),
        row(f"Fabrication (~{round(total_kg)} kg @ {inr_display(SEED_FABRICATION_RATE)}/kg)", fabrication),
    ]
    if bought_out:
        breakdown.append(row(f"Bought-outs (motor {motor_hp or 0} HP, pump {pump_hp or 0} HP)", bought_out))
    breakdown += [
        row(f"Bought-out parts allowance ({round(SEED_BOP_PCT*100)}%)", bop),
        row(f"Factory & selling overhead ({round(SEED_OVERHEAD_PCT*100)}%)", overhead),
        row(f"Margin ({round(margin*100)}%)", price - cost),
    ]
    unit = _round_price(price)
    return {
        "unit_price": unit,
        "unit_price_display": inr_display(unit),
        "est_weight_kg": round(total_kg),
        "material_of_construction": moc,
        "margin_pct": round(margin * 100),
        "cost_ex_margin": _round_price(cost),
        "breakdown": breakdown,
        "note": ("Indicative cost model from seeded rates — refine SEED_* rates in "
                 "pricing_intelligence.py with the actual rate card."),
    }


def market_benchmark(category: str, params: dict,
                     offers: Optional[list[dict]] = None) -> Optional[dict[str, Any]]:
    """The ₹-per-driver band across priced offers, and where a per-unit price
    for this requirement would sit in it."""
    recs = offers if offers is not None else _offer_records(category)
    req_d, dkey = _driver_value(category, params)
    rates = []                                   # per-unit ₹ per driver-unit
    for r in recs:
        gd = r.get("given_data", {}) or {}
        tot = _total(r.get("price_schedule") or {})
        if tot is None:
            continue
        d, _ = _driver_value(category, gd)
        if d and d > 0:
            rates.append((tot / _qty(gd)) / d)
    if len(rates) < 2 or req_d is None:
        return None
    rates.sort()
    n = len(rates)

    def pct(p):                                  # simple percentile
        return rates[min(n - 1, int(p * n))]

    lo, mid, hi = rates[0], rates[n // 2], rates[-1]
    p33, p66 = pct(1 / 3), pct(2 / 3)
    driver_qty = req_d * _qty(params)
    band_low = _round_price(lo * driver_qty)
    band_high = _round_price(hi * driver_qty)
    unit_word = "m2" if dkey == "floor_area" else (dkey or "unit").rsplit("_", 1)[-1].upper()
    return {
        "driver_key": dkey,
        "unit_word": unit_word,
        "rate_low": lo, "rate_median": mid, "rate_high": hi,
        "rate_low_display": f"{inr_display(_round_rate(lo))}/{unit_word}",
        "rate_median_display": f"{inr_display(_round_rate(mid))}/{unit_word}",
        "rate_high_display": f"{inr_display(_round_rate(hi))}/{unit_word}",
        "band_low": band_low, "band_high": band_high,
        "band_display": f"{inr_display(band_low)} – {inr_display(band_high)}",
        "n": n, "_p33": p33, "_p66": p66,
    }


def _position(unit_rate: float, market: dict) -> str:
    if unit_rate <= market["_p33"]:
        return "aggressive"
    if unit_rate <= market["_p66"]:
        return "market"
    return "premium"


def analyse_pricing(category: str, params: dict, analysis: dict, price: dict,
                    offers: Optional[list[dict]] = None) -> dict[str, Any]:
    """Reconcile historical (headline), cost-plus and market signals.

    `price` is the dict from pricing.estimate_price — its figure stays the
    recommended headline so verified quotes do not move.
    """
    recs = offers if offers is not None else _offer_records(category)
    qty = _qty(params)
    hist_unit = price.get("unit_price")
    hist_order = price.get("amount")

    methods: dict[str, Any] = {
        "historical": {
            "unit_price": hist_unit,
            "unit_price_display": price.get("unit_price_display"),
            "amount": hist_order,
            "amount_display": price.get("amount_display"),
            "basis": price.get("basis") or [],
            "method": price.get("method"),
        }
    }
    flags: list[str] = []

    cost = cost_plus_estimate(category, params, analysis)
    if cost:
        cost["amount"] = _round_price(cost["unit_price"] * qty)
        cost["amount_display"] = inr_display(cost["amount"])
        methods["cost_plus"] = cost
        if hist_unit and cost["unit_price"]:
            dev = (cost["unit_price"] - hist_unit) / hist_unit
            if abs(dev) >= 0.30:
                flags.append(
                    f"Cost-plus model ({cost['unit_price_display']}/unit) and history "
                    f"({price.get('unit_price_display')}/unit) differ by {round(dev*100)}% — "
                    f"check the seeded rates or the historical basis.")

    market = market_benchmark(category, params, recs)
    position = None
    if market:
        req_d, _ = _driver_value(category, params)
        unit_rate = (hist_unit / req_d) if (hist_unit and req_d) else market["rate_median"]
        position = _position(unit_rate, market)
        market["this_rate"] = _round_rate(unit_rate)
        market["this_rate_display"] = f"{inr_display(_round_rate(unit_rate))}/{market['unit_word']}"
        market["position"] = position
        methods["market"] = market
        if hist_order and (hist_order < market["band_low"] or hist_order > market["band_high"]):
            flags.append(
                f"Headline {price.get('amount_display')} is outside the market band "
                f"{market['band_display']} for this size.")

    rationale = _rationale(price, methods, position)
    out = {
        "recommended": hist_order,
        "recommended_display": price.get("amount_display"),
        "recommended_basis": "historical",
        "position": position,
        "suggested_margin_band": MARGIN_BANDS,
        "methods": methods,
        "flags": flags,
        "rationale": rationale,
    }
    out["basis_markdown"] = render_basis_markdown(price, out)
    return out


def _rationale(price: dict, methods: dict, position: Optional[str]) -> str:
    bits = [f"Recommended {price.get('amount_display')} is anchored on Vitech's own "
            f"history ({price.get('method', 'nearest priced offer scaled by size')})."]
    cp = methods.get("cost_plus")
    if cp:
        bits.append(f"A bottom-up cost-plus build-up at {cp['margin_pct']}% margin lands at "
                    f"{cp['amount_display']} (indicative, seeded rates).")
    mk = methods.get("market")
    if mk:
        bits.append(f"Across {mk['n']} priced offers the market rate runs "
                    f"{mk['rate_low_display']} to {mk['rate_high_display']}; this quote sits "
                    f"{position.upper()} at {mk.get('this_rate_display')}.")
    return " ".join(bits)


def render_basis_markdown(price: dict, intel: dict) -> str:
    """Internal 'how the amount was fixed' note the agent presents on request.

    Not part of the customer quotation — it exposes margin / cost / market
    reasoning for the sales engineer, all deterministic.
    """
    m = intel["methods"]
    L = ["### Pricing Basis (internal — how the amount was fixed)", ""]
    L.append(f"**Recommended (budgetary):** {intel['recommended_display']}  ·  "
             f"basis: history-anchored" + (f", {intel['position']} vs market"
                                           if intel.get("position") else ""))
    L.append("")
    h = m["historical"]
    L.append(f"**A. Historical scaling** — {h.get('amount_display')} "
             f"({h.get('method', 'nearest priced offer scaled by size')}"
             + (f"; basis {', '.join(h['basis'])}" if h.get("basis") else "") + ")")
    cp = m.get("cost_plus")
    if cp:
        L.append("")
        L.append(f"**B. Cost-plus build-up** — {cp['amount_display']} "
                 f"(≈{cp['est_weight_kg']} kg {cp['material_of_construction']}, "
                 f"{cp['margin_pct']}% margin):")
        L.append("")
        L.append("| Cost element | Amount |")
        L.append("| --- | --- |")
        for b in cp["breakdown"]:
            L.append(f"| {b['label']} | {b['display']} |")
        L.append(f"| **Unit price** | **{cp['unit_price_display']}** |")
    mk = m.get("market")
    if mk:
        L.append("")
        L.append(f"**C. Market benchmark** — across {mk['n']} priced offers the rate runs "
                 f"{mk['rate_low_display']} (median {mk['rate_median_display']}) to "
                 f"{mk['rate_high_display']}. For this size that is a market band of "
                 f"{mk['band_display']}; this quote is **{mk['position']}** at "
                 f"{mk['this_rate_display']}.")
    if intel.get("flags"):
        L.append("")
        L.append("**Watch-outs**")
        for f in intel["flags"]:
            L.append(f"- {f}")
    L.append("")
    L.append("_Figures are deterministic (history + seeded cost/market rates); a budgetary "
             "draft for engineer review, not a released price._")
    return "\n".join(L)
