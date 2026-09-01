"""Vitech's STANDARD paint-booth range, as data.

Source: `VITECH_AI_Paint_Booth_Database_V02_Source_Based.pdf` (delivered
2026-09-01), transcribed in `docs/client-calculation-sheets.md` §7. Thirty-five
models across three families, each with the width, depth, height, static
pressure, airflow and motor rating Vitech themselves publish.

WHY THIS MATTERS. Until now the platform engineered every booth from first
principles, even when the customer was asking for something Vitech already
builds and already knows the airflow and motor for. A standard model is a better
answer than a fresh calculation: it is what they actually sell, it is priced,
and it needs no assumptions.

**EVERY NUMBER HERE IS QUOTED, NOT COMPUTED**, and that is deliberate. The
document's own airflow formula rests on a 1.5 m effective filter opening, while
`Standard Booth.xlsx` computes the same booth on the full 2.4 m height — 8,100
CMH against 12,960 for one 3.0 m booth. That contradiction is open question
DQ-10. Citing Vitech's published figure for a Vitech model sidesteps it
entirely: we are reporting their catalogue, not choosing between their formulas.
For the same reason the document's own unconfirmed factors (3-row = 1.4x,
wet = 0.90x) are NOT used to extrapolate a model that is not printed.
"""
from typing import NamedTuple, Optional

from . import standards_service as std

WET = "wet"
DRY_2ROW = "dry_2row"
DRY_3ROW = "dry_3row"

FRONT_OPEN = "front open"
ENCLOSED = "enclosed"


class BoothModel(NamedTuple):
    """One published model. `motor_hp` is None where the sheet prints no rating."""
    model: str
    family: str
    config: str
    width_mm: int
    depth_mm: int
    height_mm: int
    static_mmwc: float
    airflow_cmh: int
    airflow_cfm: int
    motor_hp: Optional[float]


def _m(model, family, config, w, d, static, cmh, cfm, hp):
    return BoothModel(model, family, config, w, d, 2425, static, cmh, cfm, hp)


# --- Wet (water-wash) booths, static 5 mmwc, capture velocity 1.0 m/s ------
_WET = [
    _m("VT/1.5/DTPB/OP", WET, FRONT_OPEN, 1500, 1500, 5, 3645, 2144, 5),
    _m("VT/2.25/DTPB/OP", WET, FRONT_OPEN, 2250, 1500, 5, 5468, 3216, 5),
    _m("VT/3.0/DTPB/OP", WET, FRONT_OPEN, 3000, 1500, 5, 7290, 4288, 7.5),
    _m("VT/3.75/DTPB/OP", WET, FRONT_OPEN, 3750, 1500, 5, 9113, 5360, 7.5),
    _m("VT/4.5/DTPB/OP", WET, FRONT_OPEN, 4500, 1500, 5, 10935, 6432, 10),
    _m("VT/1.5/DTPB/CL", WET, ENCLOSED, 1500, 2250, 5, 3645, 2144, 5),
    _m("VT/2.25/DTPB/CL", WET, ENCLOSED, 2250, 2250, 5, 5468, 3216, 5),
    _m("VT/3.0/DTPB/CL", WET, ENCLOSED, 3000, 2250, 5, 7290, 4288, 7.5),
    _m("VT/3.75/DTPB/CL", WET, ENCLOSED, 3750, 2250, 5, 9113, 5360, 7.5),
    _m("VT/4.5/DTPB/CL", WET, ENCLOSED, 4500, 2250, 5, 10935, 6432, 10),
    # The sheet prints no motor rating for the 7.5 m machine. It stays None
    # rather than being scaled from the 4.5 - that would be our number, not
    # theirs, on a machine nobody has sized.
    _m("VT/7.5/DTPB/CL", WET, ENCLOSED, 7500, 2250, 5, 18225, 10721, None),
]

# --- Dry, 2-row filter. Static 3 front-open / 4 enclosed -------------------
_DRY_2 = [
    _m("VT/1.5/DTPB/OP", DRY_2ROW, FRONT_OPEN, 1500, 1500, 3, 4050, 2382, 2),
    _m("VT/2.25/DTPB/OP", DRY_2ROW, FRONT_OPEN, 2250, 1500, 3, 6075, 3574, 3),
    _m("VT/3.0/DTPB/OP", DRY_2ROW, FRONT_OPEN, 3000, 1500, 3, 8100, 4765, 5),
    _m("VT/3.75/DTPB/OP", DRY_2ROW, FRONT_OPEN, 3750, 1500, 3, 10125, 5956, 5),
    _m("VT/4.5/DTPB/OP", DRY_2ROW, FRONT_OPEN, 4500, 1500, 3, 12150, 7147, 7.5),
    _m("VT/1.5/DTPB/CL", DRY_2ROW, ENCLOSED, 1500, 2250, 4, 4050, 2382, 2),
    _m("VT/2.25/DTPB/CL", DRY_2ROW, ENCLOSED, 2250, 2250, 4, 6075, 3574, 3),
    _m("VT/3.0/DTPB/CL", DRY_2ROW, ENCLOSED, 3000, 2250, 4, 8100, 4765, 5),
    _m("VT/3.75/DTPB/CL", DRY_2ROW, ENCLOSED, 3750, 2250, 4, 10125, 5956, 5),
    _m("VT/4.5/DTPB/CL", DRY_2ROW, ENCLOSED, 4500, 2250, 4, 12150, 7147, 7.5),
]

# --- Dry, 3-row filter -----------------------------------------------------
_DRY_3 = [
    _m("VT/1.5/DTPB/OP", DRY_3ROW, FRONT_OPEN, 1500, 1500, 3, 5670, 3335, 5),
    _m("VT/2.25/DTPB/OP", DRY_3ROW, FRONT_OPEN, 2250, 1500, 3, 8505, 5003, 7.5),
    _m("VT/3.0/DTPB/OP", DRY_3ROW, FRONT_OPEN, 3000, 1500, 3, 11340, 6671, 7.5),
    _m("VT/3.75/DTPB/OP", DRY_3ROW, FRONT_OPEN, 3750, 1500, 3, 14175, 8338, 10),
    _m("VT/4.5/DTPB/OP", DRY_3ROW, FRONT_OPEN, 4500, 1500, 3, 17010, 10006, 10),
    _m("VT/1.5/DTPB/CL", DRY_3ROW, ENCLOSED, 1500, 2250, 4, 5670, 3335, 5),
    _m("VT/2.25/DTPB/CL", DRY_3ROW, ENCLOSED, 2250, 2250, 4, 8505, 5003, 7.5),
    _m("VT/3.0/DTPB/CL", DRY_3ROW, ENCLOSED, 3000, 2250, 4, 11340, 6671, 7.5),
    _m("VT/3.75/DTPB/CL", DRY_3ROW, ENCLOSED, 3750, 2250, 4, 14175, 8338, 10),
    _m("VT/4.5/DTPB/CL", DRY_3ROW, ENCLOSED, 4500, 2250, 4, 17010, 10006, 10),
]

CATALOGUE: list[BoothModel] = _WET + _DRY_2 + _DRY_3

# A customer's stated width has to land on a standard machine to BE one. Vitech
# builds five widths; anything else is a special, and saying so is the useful
# answer.
STANDARD_WIDTHS_MM = (1500, 2250, 3000, 3750, 4500, 7500)
STANDARD_HEIGHT_MM = 2425


def catalogue(family: Optional[str] = None) -> list[BoothModel]:
    """Every published model, or every model in one family."""
    return [m for m in CATALOGUE if family is None or m.family == family]


def by_model(code: str, family: Optional[str] = None) -> Optional[BoothModel]:
    """Look a model up by its code. A code alone is ambiguous across families —
    VT/3.0/DTPB/OP exists as wet, dry 2-row and dry 3-row — so pass the family
    when it is known, or the first match is returned."""
    for m in CATALOGUE:
        if m.model == code and (family is None or m.family == family):
            return m
    return None


def select(width_mm: float,
           family: str = DRY_2ROW,
           config: str = FRONT_OPEN,
           tolerance_mm: float = 100.0) -> Optional[BoothModel]:
    """The standard model matching a stated open-front width, or None.

    Returns None rather than the nearest machine when nothing matches within
    `tolerance_mm`. A booth 200 mm off a standard width is a SPECIAL, and
    quietly rounding a customer's stated size to sell them a catalogue unit is
    how the wrong machine gets built. The caller says "no standard model — this
    is a special" and the engine designs it from first principles instead.
    """
    if width_mm is None:
        return None
    candidates = [m for m in CATALOGUE
                  if m.family == family and m.config == config
                  and abs(m.width_mm - float(width_mm)) <= tolerance_mm]
    if not candidates:
        return None
    return min(candidates, key=lambda m: abs(m.width_mm - float(width_mm)))


def describe(m: BoothModel) -> dict:
    """A model as spec rows, each attributed to the catalogue rather than to a
    calculation — because that is exactly what they are."""
    hp = f"{m.motor_hp:g} HP" if m.motor_hp else "not rated in the catalogue"
    return {
        "model": m.model,
        "rows": [
            ("Standard model", m.model,
             f"Vitech standard range, {m.config} {m.family.replace('_', ' ')}"),
            ("Booth size (W x D x H)", f"{m.width_mm} x {m.depth_mm} x {m.height_mm} mm",
             "published dimensions"),
            ("Exhaust airflow", f"{m.airflow_cmh} m3/h ({m.airflow_cfm} cfm)",
             "published for this model"),
            ("Static pressure", f"{m.static_mmwc:g} mmwc", "published for this model"),
            ("Exhaust blower motor", hp, "published for this model"),
        ],
        "standard": std.CLIENT_BOOTH_CATALOGUE,
    }
