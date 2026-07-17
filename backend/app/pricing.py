"""Deterministic budgetary pricing for the Quotation Agent.

Prices are NEVER guessed by the LLM. A budgetary figure is derived from the
company's own historical offers:

  1. take the nearest offer on the sizing driver (airflow, floor area, ...),
  2. scale its order value by that driver,
  3. CROSS-CHECK against a size -> price trend (least-squares) across every
     priced offer in the category,
  4. report the estimate with its basis, method, a +/- range and a confidence.

The offer price schedules are coarse (mostly lump-sum), so this estimates the
SYSTEM order value — not a per-component BOM cost. Output is a budgetary draft
for an engineer to confirm, consistent with the human-in-the-loop rule.
"""
import json
from typing import Any, Optional

from .catalog import get_profile
from .store import get_collection

_CURRENCY_DEFAULT = "INR"
# price schedule keys that already represent an order total, most-canonical first
_TOTAL_KEYS = ("final_price", "grand_total", "total")


def _offer_records(category: str) -> list[dict]:
    """All priced offers of a category, straight from the knowledge base."""
    col = get_collection()
    if col.count() == 0:
        return []
    out = []
    for m in col.get(include=["metadatas"])["metadatas"]:
        raw = m.get("_raw")
        if not raw:
            continue
        r = json.loads(raw)
        if r.get("type") == "offer" and r.get("category") == category:
            out.append(r)
    return out


def _total(ps: dict) -> Optional[float]:
    """Canonical order value of a price schedule (currency stripped)."""
    if not ps:
        return None
    for k in _TOTAL_KEYS:
        v = ps.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    nums = [v for k, v in ps.items() if isinstance(v, (int, float))]
    return float(sum(nums)) if nums else None


def _qty(data: dict) -> int:
    """Quantity from an offer/requirement (default 1). Prices are normalised
    to PER UNIT so a 2-off historical offer doesn't look twice as expensive."""
    q = data.get("qty") or data.get("quantity")
    try:
        q = int(q)
    except (TypeError, ValueError):
        return 1
    return q if q > 0 else 1


def _driver_value(category: str, data: dict) -> tuple[Optional[float], Optional[str]]:
    """The sizing driver value for a requirement/offer (e.g. airflow, floor area)."""
    prof = get_profile(category)
    key = prof.get("scale_driver") if prof else None
    if key and isinstance(data.get(key), (int, float)):
        return float(data[key]), key
    # derived drivers where no single given-data key exists
    if category == "paint_booth":
        l, w = data.get("length_m"), data.get("width_m")
        if isinstance(l, (int, float)) and isinstance(w, (int, float)):
            return float(l) * float(w), "floor_area"
    return None, key


def _linfit(xs: list[float], ys: list[float]) -> Optional[tuple[float, float, float]]:
    """Least-squares y = a + b*x. Returns (a, b, r2) or None if degenerate."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for y in ys)
    ssr = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ssr / sst if sst > 0 else 0.0
    return a, b, r2


def _round_price(v: float) -> int:
    """Round a budgetary figure to a presentable step (never false precision)."""
    if v <= 0:
        return 0
    if v < 100_000:
        step = 1_000
    elif v < 1_000_000:
        step = 5_000
    else:
        step = 25_000
    return int(round(v / step) * step)


def _label(pct: int) -> str:
    return "High" if pct >= 80 else "Medium" if pct >= 60 else "Low"


def inr_display(n) -> str:
    """Indian-grouped rupee string, e.g. 2550000 -> '₹25,50,000'.

    Preformatted so the number NEVER passes through the LLM's own digit
    grouping (llama3.1 cannot do lakh/crore grouping and mangled it 10x).
    The agent copies this string verbatim.
    """
    n = int(round(n or 0))
    neg, s = n < 0, str(abs(n))
    if len(s) <= 3:
        grp = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grp = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + grp


def estimate_price(category: str, params: dict,
                   offers: Optional[list[dict]] = None) -> Optional[dict[str, Any]]:
    """Budgetary order-value estimate for a requirement, from historical offers.

    Returns None when the category has no priced history to reason from.
    """
    recs = offers if offers is not None else _offer_records(category)
    currency = _CURRENCY_DEFAULT
    pts = []  # (driver_or_None, per_unit_total, id)
    for r in recs:
        gd = r.get("given_data", {}) or {}
        ps = r.get("price_schedule") or {}
        currency = ps.get("currency", currency)
        tot = _total(ps)
        if tot is None:
            continue
        per_unit = tot / _qty(gd)          # normalise to per-unit
        dv, _ = _driver_value(category, gd)
        pts.append((dv, per_unit, r.get("id")))
    if not pts:
        return None

    req_d, dkey = _driver_value(category, params)
    with_driver = [(d, t, i) for d, t, i in pts if d is not None]
    conf = 0.55
    notes = []
    regression = None

    if req_d is not None and with_driver:
        nearest = min(with_driver, key=lambda p: abs(p[0] - req_d))
        n_d, n_t, n_id = nearest
        scaled = n_t * (req_d / n_d) if n_d else n_t
        method = f"Nearest priced offer {n_id} scaled by {dkey}"
        basis = [n_id]

        drivers = [d for d, _, _ in with_driver]
        lo, hi = min(drivers), max(drivers)
        interpolating = lo <= req_d <= hi
        conf += 0.15 if interpolating else -0.10
        if not interpolating:
            notes.append(f"Requested {dkey} is outside the historical range "
                         f"({_round_price(lo)}-{_round_price(hi)}); extrapolated.")

        fit = _linfit([d for d, _, _ in with_driver], [t for _, t, _ in with_driver])
        if fit:
            a, b, r2 = fit
            pred = a + b * req_d
            regression = {"predicted_unit": _round_price(max(pred, 0)),
                          "n": len(with_driver), "r2": round(r2, 3)}
            if pred > 0:
                dev = abs(scaled - pred) / pred
                if dev <= 0.15:
                    conf += 0.15
                elif dev >= 0.40:
                    conf -= 0.10
                    notes.append(f"Scaling and the size/price trend disagree by "
                                 f"{round(dev * 100)}% — treat as indicative only.")
                # blend toward the trend when we have a decent fit
                if r2 >= 0.6:
                    scaled = 0.6 * scaled + 0.4 * pred
                    method += " (blended with size/price trend)"
        if len(with_driver) >= 4:
            conf += 0.05
        estimate = scaled
    else:
        # no usable driver: fall back to the average of priced offers
        totals = [t for _, t, _ in pts]
        estimate = sum(totals) / len(totals)
        method = "Average of priced offers (no sizing driver available)"
        basis = [i for _, _, i in pts]
        conf = 0.45
        notes.append("No numeric sizing driver for this category; figure is a coarse average.")

    conf = max(0.35, min(0.9, conf))
    pct = round(conf * 100)
    req_qty = _qty(params)
    unit = _round_price(estimate)              # per-unit budgetary price
    order = estimate * req_qty                 # order value for the requested qty
    amount = _round_price(order)
    range_low = _round_price(order * 0.85)
    range_high = _round_price(order * 1.15)
    return {
        "amount": amount,                      # headline: order value
        "amount_display": inr_display(amount),
        "unit_price": unit,
        "unit_price_display": inr_display(unit),
        "qty": req_qty,
        "currency": currency,
        "range_low": range_low,
        "range_low_display": inr_display(range_low),
        "range_high": range_high,
        "range_high_display": inr_display(range_high),
        "range_display": f"{inr_display(range_low)} – {inr_display(range_high)}",
        "method": method,
        "driver": {"key": dkey, "value": req_d},
        "regression": regression,              # per-unit predicted, diagnostic
        "n_priced": len(pts),
        "basis": basis,
        "confidence": round(conf, 2),
        "confidence_pct": pct,
        "confidence_label": _label(pct),
        "note": "Budgetary estimate from historical offers - engineer to confirm.",
    }
