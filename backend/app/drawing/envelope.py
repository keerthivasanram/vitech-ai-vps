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


def _wet_scrubber(rows: list) -> Optional[dict]:
    """A vertical spray tower: the tower diameter IS the footprint, and the
    tower height is a rule output. Both are real resolved numbers."""
    dia_mm = _num(rows, "tower diameter")
    height_m = _num(rows, "tower height")
    if not dia_mm or not height_m:
        return None
    return {"length": round(dia_mm), "width": round(dia_mm),
            "height": round(height_m * 1000)}


_DERIVERS: dict[str, Callable[[list], Optional[dict]]] = {
    "wet_scrubber": _wet_scrubber,
}


def derive_envelope(category: str, rows: list) -> Optional[dict]:
    """Envelope in mm for a category whose requirement omits L/W/H, or None.

    Returns only a COMPLETE envelope — a partial one would put a guessed extent
    on a dimensioned drawing, which is exactly what must never happen.
    """
    fn = _DERIVERS.get(category or "")
    if not fn:
        return None
    env = fn(rows or [])
    if not env or not all(env.get(k) for k in ("length", "width", "height")):
        return None
    return env
