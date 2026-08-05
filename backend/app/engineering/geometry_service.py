"""Deterministic equipment geometry: the resolved envelope, and the TYPE it came from.

WHY THIS LIVES IN THE ENGINEERING PACKAGE. Geometry is an engineering output, not
a drawing concern. It used to be derived inside `app/drawing/envelope.py`, which
meant the renderer decided what kind of machine it was drawing by pattern-matching
spec ROW LABELS ("tower diameter" -> vertical tower). Two things were wrong with
that: the specification and the drawing could reach different conclusions about
the same resolved spec, and a category's geometry rule was invisible to every
consumer that is not the drawing (the BOM, the package, a future coordinate
layout engine). Geometry is resolved ONCE here, and the specification and the
drawing consume the same answer.

THE TYPE IS PART OF THE ANSWER. A wet scrubber is not one shape. Vitech's own
archive holds two distinct machines under that one category:

  * VERTICAL SPRAY TOWER   - specified by tower diameter; height is a rule output
                             (`compute_wet_scrubber`). Four offers on file.
  * HORIZONTAL BAFFLE UNIT - specified by a stated casing L x W. One offer on file
                             (OFF-C2C-WS-20240921R1), and it records no height.

Drawing one as the other is not a cosmetic error, so the type is resolved
explicitly and published alongside the envelope. Downstream code asks
`geometry["equipment_type"]` instead of re-deciding from prose.

GOLDEN RULE #2 HOLDS THROUGHOUT. Only a value the CLIENT STATED or a RULE
COMPUTED may become a drawn dimension. A value reused from a historical offer is
a different machine's casing and is refused — which is why a horizontal baffle
requirement still yields no envelope today, and honestly says so.

CLIENT-EXTENSION POINT: `_MODELS[category]` — one function per category.
"""
import re
from typing import Callable, NamedTuple, Optional

# Only these origins may feed a drawn envelope. `reused`, `scaled`, `consistent`
# and `interpolated` are deliberately absent: they describe a comparable machine,
# not this one.
TRUSTED_ORIGINS = {"given", "rule", "requirement", "standard"}


class Geometry(NamedTuple):
    """A resolved envelope plus how it was arrived at.

    `envelope` is None when the equipment's size is not yet determined — the
    honest outcome that makes the sheet print "NO DIMENSIONED VIEWS" instead of
    a fabricated box. `basis` explains each axis for the traceability document,
    and `conflicts` carries any contradiction worth an engineer's attention.
    """
    equipment_type: Optional[str]
    envelope: Optional[dict]
    basis: dict
    conflicts: tuple


def _trusted_num(rows: list, *needles: str) -> Optional[float]:
    """First numeric value from a TRUSTED row whose label contains all needles."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if not all(nd in label for nd in needles):
            continue
        origin = str(r.get("origin", "")).lower()
        if not any(t in origin for t in TRUSTED_ORIGINS):
            continue
        m = re.search(r"-?\d+(?:\.\d+)?", str(r.get("value", "")))
        if m:
            return float(m.group())
    return None


def _any_row(rows: list, *needles: str) -> Optional[dict]:
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if all(nd in label for nd in needles):
            return r
    return None


def _triple(rows: list, *needles: str, trusted: bool = True):
    """L/W/H from one stated size row ("3.9L x 4.0W x 8.3H", "900 x 900 x 1400")."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if not all(nd in label for nd in needles):
            continue
        if trusted:
            origin = str(r.get("origin", "")).lower()
            if not any(t in origin for t in TRUSTED_ORIGINS):
                continue
        nums = re.findall(r"\d+(?:\.\d+)?", str(r.get("value", "")))
        if len(nums) >= 3:
            return float(nums[0]), float(nums[1]), float(nums[2]), label
    return None


# --------------------------------------------------------------------------
# Wet scrubber — two machines, two models
# --------------------------------------------------------------------------
TYPE_SPRAY_TOWER = "vertical_spray_tower"
TYPE_HORIZONTAL_BAFFLE = "horizontal_baffle"

# Words in a resolved `scrubber_type` that name a horizontal baffle unit.
_BAFFLE_WORDS = ("horizontal", "baffle")


def _wet_scrubber(rows: list, params: dict) -> Geometry:
    """Resolve which scrubber this is, then apply that type's geometry model.

    The TYPE is decided by the engineering values, not by prose, and a client
    requirement outranks a reused description. Stating a tower diameter IS
    specifying a vertical tower; the archive's baffle wording came from whichever
    offer happened to be nearest and describes a different machine.
    """
    dia_mm = _trusted_num(rows, "tower diameter")
    height_m = _trusted_num(rows, "tower height")
    type_row = _any_row(rows, "scrubber type")
    says_baffle = any(w in str((type_row or {}).get("value", "")).lower()
                      for w in _BAFFLE_WORDS)
    conflicts: list = []

    if dia_mm:
        # --- vertical spray tower -----------------------------------------
        # The tower diameter is the footprint and the height is a rule output.
        # Both are real resolved numbers, so the envelope is fully determined.
        if says_baffle and str((type_row or {}).get("origin", "")).lower() not in TRUSTED_ORIGINS:
            conflicts.append(
                "Client specified a tower diameter (vertical spray tower) but the "
                f"nearest historical design is described as "
                f"\"{str(type_row.get('value'))[:48]}\" - confirm the scrubber type.")
        if not height_m:
            return Geometry(TYPE_SPRAY_TOWER, None,
                            {"height": "not resolved - tower height rule did not run"},
                            tuple(conflicts))
        return Geometry(
            TYPE_SPRAY_TOWER,
            {"length": round(dia_mm), "width": round(dia_mm),
             "height": round(height_m * 1000)},
            {"length": "tower diameter (client requirement)",
             "width": "tower diameter (client requirement)",
             "height": "tower height (engineering rule)"},
            tuple(conflicts))

    # --- horizontal baffle unit -------------------------------------------
    # Specified by a stated casing size. The archive records only W x L for this
    # machine and no height, and the one offer that carries it is reuse — a
    # different unit's casing. Both facts are reported rather than papered over,
    # because a fabricated height would put an invented line on a drawing.
    trip = _triple(rows, "scrubber dimension")
    if trip:
        L, W, H, label = trip
        unit = 1.0 if "mm" in label else 1000.0
        return Geometry(TYPE_HORIZONTAL_BAFFLE,
                        {"length": round(L * unit), "width": round(W * unit),
                         "height": round(H * unit)},
                        {"length": "stated casing length", "width": "stated casing width",
                         "height": "stated casing height"}, tuple(conflicts))

    if says_baffle or _any_row(rows, "scrubber dimension"):
        conflicts.append(
            "Horizontal baffle scrubber casing height is not engineered - Vitech "
            "has supplied no height rule for this type, and the archived casing "
            "belongs to a different unit.")
        return Geometry(TYPE_HORIZONTAL_BAFFLE, None,
                        {"height": "no engineering rule supplied for this type"},
                        tuple(conflicts))
    return Geometry(None, None, {}, tuple(conflicts))


# --------------------------------------------------------------------------
# Dust collector
# --------------------------------------------------------------------------
def _dust_collector(rows: list, params: dict) -> Geometry:
    """A collector's casing size when the CLIENT stated it.

    There is deliberately no fallback that sizes a casing from airflow: that
    needs an air-to-cloth ratio, a bag pitch and hopper proportions, and Vitech's
    pollution-control calculation document has not arrived. A size taken from a
    historical offer stays refused — it is a different machine's casing.
    """
    trip = _triple(rows, "collector size")
    if not trip:
        return Geometry("bag_filter", None,
                        {"envelope": "casing size not stated by the client"}, ())
    L, W, H, label = trip
    unit = 1.0 if "mm" in label else 1000.0
    return Geometry("bag_filter",
                    {"length": round(L * unit), "width": round(W * unit),
                     "height": round(H * unit)},
                    {"length": "stated casing length", "width": "stated casing width",
                     "height": "stated casing height"}, ())


# --------------------------------------------------------------------------
# Ducting
# --------------------------------------------------------------------------
def _ducting(rows: list, params: dict) -> Geometry:
    """A duct run drawn DEVELOPED: the client's total run length by the section
    computed from their own transport-velocity standard."""
    from .unit_converter import air_cmh
    airflow = air_cmh(params)
    try:
        length_m = float(params.get("layout_length_m"))
    except (TypeError, ValueError):
        return Geometry("round_duct", None, {"length": "run length not stated"}, ())
    if not airflow or length_m <= 0 or airflow <= 0:
        return Geometry("round_duct", None, {"section": "airflow not stated"}, ())

    from .design_standards import select_duct
    dia = (select_duct(airflow).detail or {}).get("diameter_mm")
    if not dia:
        return Geometry("round_duct", None, {"section": "duct selection did not resolve"}, ())
    return Geometry("round_duct",
                    {"length": round(length_m * 1000), "width": round(dia),
                     "height": round(dia)},
                    {"length": "client-stated run length",
                     "width": "duct diameter (transport-velocity standard)",
                     "height": "duct diameter (transport-velocity standard)"}, ())


_MODELS: dict[str, Callable[[list, dict], Geometry]] = {
    "wet_scrubber": _wet_scrubber,
    "dust_collector": _dust_collector,
    "ducting": _ducting,
}


def resolve_geometry(category: str, rows: Optional[list] = None,
                     params: Optional[dict] = None) -> Geometry:
    """The resolved geometry for a category whose requirement omits L/W/H.

    Returns a COMPLETE envelope or none at all — a partial one would put a
    guessed extent on a dimensioned drawing, which is exactly what must never
    happen. Categories that state their dimensions directly need no model here;
    they are handled by the caller before this is consulted.
    """
    fn = _MODELS.get(category or "")
    if not fn:
        return Geometry(None, None, {}, ())
    geo = fn(rows or [], params or {})
    if geo.envelope and not all(geo.envelope.get(k) for k in ("length", "width", "height")):
        return Geometry(geo.equipment_type, None, geo.basis, geo.conflicts)
    return geo


def derive_envelope(category: str, rows: Optional[list] = None,
                    params: Optional[dict] = None) -> Optional[dict]:
    """Envelope-only convenience wrapper (the pre-existing contract)."""
    return resolve_geometry(category, rows, params).envelope
