"""Derive a drawable envelope for categories that never state L x W x H.

A paint booth requirement gives its dimensions directly, so `_spec_geometry`
reads them straight off the requirement. A wet scrubber does not: the customer
states an airflow and a tower diameter, and the height is a rule output. The
envelope is nonetheless fully determined — just not by three literal inputs.

This module closes that gap WITHOUT loosening golden rule #2: it only ever
composes numbers the engine already resolved (a client-given dimension or a
rule-computed one), never a shape constant or an assumed proportion. If the
values it needs are missing, it returns None and the drawing shows TBD.

CLIENT-EXTENSION POINT: `_DERIVERS[category]` — one function per category.
"""
import re
from typing import Callable, Optional

# Only these origins may feed an envelope: a value the client stated, or one the
# rule engine computed. A value merely REUSED from a historical offer is not a
# dimension of THIS machine, so it must not become its drawn size.
_TRUSTED_ORIGINS = {"given", "rule", "requirement"}


def _num(rows: list, *needles: str, trusted_only: bool = True) -> Optional[float]:
    """First numeric value whose label contains all needles (case-insensitive)."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if not all(nd in label for nd in needles):
            continue
        if trusted_only:
            origin = str(r.get("origin", "")).lower()
            # accept both raw origins and the display labels
            if not any(t in origin for t in _TRUSTED_ORIGINS):
                continue
        m = re.search(r"-?\d+(?:\.\d+)?", str(r.get("value", "")))
        if m:
            return float(m.group())
    return None


def _triple(rows: list, *needles: str) -> Optional[tuple[float, float, float]]:
    """L/W/H out of a single stated size row ("3.9L x 4.0W x 8.3H", "900 x 900
    x 1400"), in the row's own units, from a TRUSTED row only."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if not all(nd in label for nd in needles):
            continue
        origin = str(r.get("origin", "")).lower()
        if not any(t in origin for t in _TRUSTED_ORIGINS):
            continue
        nums = re.findall(r"\d+(?:\.\d+)?", str(r.get("value", "")))
        if len(nums) >= 3:
            return float(nums[0]), float(nums[1]), float(nums[2])
    return None


def _wet_scrubber(rows: list, params: dict) -> Optional[dict]:
    """A vertical spray tower: the tower diameter IS the footprint, and the
    tower height is a rule output. Both are real resolved numbers."""
    dia_mm = _num(rows, "tower diameter")
    height_m = _num(rows, "tower height")
    if not dia_mm or not height_m:
        return None
    return {"length": round(dia_mm), "width": round(dia_mm),
            "height": round(height_m * 1000)}


def _dust_collector(rows: list, params: dict) -> Optional[dict]:
    """A collector's casing size when the CLIENT stated it.

    There is deliberately no fallback that sizes a casing from airflow: doing
    that needs an air-to-cloth ratio, a bag pitch and hopper proportions, and
    Vitech has not supplied their pollution-control calculation document yet.
    Until it lands, a size that came from a historical offer stays refused —
    it is a different machine's casing — and the sheet honestly says TBD.
    """
    trip = _triple(rows, "collector size")
    if not trip:
        return None
    unit_mm = 1.0 if "mm" in _size_label(rows, "collector size") else 1000.0
    L, W, H = (round(v * unit_mm) for v in trip)
    return {"length": L, "width": W, "height": H}


def _ducting(rows: list, params: dict) -> Optional[dict]:
    """A duct run drawn DEVELOPED: the client's total run length by the duct
    section computed from their own transport-velocity standard.

    Both numbers are real — the length is client-given and the diameter comes
    from `design_standards.select_duct`, the same selection the booth spec
    uses. The run is shown straight because no routing is engineered yet, and
    the sheet says so (see the ducting glyph's standing label).
    """
    from ..engineering.unit_converter import air_cmh
    airflow = air_cmh(params)
    try:
        length_m = float(params.get("layout_length_m"))
    except (TypeError, ValueError):
        return None
    if not airflow or length_m <= 0 or airflow <= 0:
        return None

    from ..engineering.design_standards import select_duct
    dia = (select_duct(airflow).detail or {}).get("diameter_mm")
    if not dia:
        return None
    return {"length": round(length_m * 1000), "width": round(dia),
            "height": round(dia)}


def _size_label(rows: list, *needles: str) -> str:
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if all(nd in label for nd in needles):
            return label
    return ""


_DERIVERS: dict[str, Callable[[list, dict], Optional[dict]]] = {
    "wet_scrubber": _wet_scrubber,
    "dust_collector": _dust_collector,
    "ducting": _ducting,
}


def derive_envelope(category: str, rows: list,
                    params: Optional[dict] = None) -> Optional[dict]:
    """Envelope in mm for a category whose requirement omits L/W/H, or None.

    Returns only a COMPLETE envelope — a partial one would put a guessed extent
    on a dimensioned drawing, which is exactly what must never happen.
    """
    fn = _DERIVERS.get(category or "")
    if not fn:
        return None
    env = fn(rows or [], params or {})
    if not env or not all(env.get(k) for k in ("length", "width", "height")):
        return None
    return env
