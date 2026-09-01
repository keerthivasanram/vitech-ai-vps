"""Paint-shop design calculations — transcribed from the client's own document.

Source: client engineering-calculation document (received 2026-08-01), section
"1. Paint shop Plant", covering Cleaning Room, Buffing Booth, Paint Booth,
Flash Off Zone and Paint Drying Room / Oven. Powder coating plant and pollution
control equipment are promised separately and are NOT guessed at here.

The client states each unit's calculation as:

    Exhaust Air Volume : Area x Velocity          (booths / rooms)
    Exhaust Air Volume : Volume x ACH             (drying room / oven)
    Inlet Air volume   : Exhaust +10% / -10% / nil
    Material weight    : Total Surface area (5 Sides - bottom neglected)
    Heat load (oven)   : volume (ft3) / 100, where 100 ft3 = 12 kW; kW x 860 = kCal

Two things the document does NOT give, so they are NOT invented here:
  * the face VELOCITY value  -> `DEFAULT_FACE_VELOCITY` (the existing NFPA 33 /
    ATS constant already used by the paint-booth engine), overridable per call
  * the ACH value for a drying room / oven -> no default at all; without it the
    exhaust volume is simply not returned, and the caller surfaces a TBD

WHICH area is "Area" depends on the draft direction — air passes through a
different plane in each design. That mapping is `_FACE_AREA`, below.
"""
from typing import NamedTuple, Optional

from . import standards_service as std
from .unit_converter import CFM_TO_CMH

# Face velocity across the open working face, m/s. NO LONGER A CONFIRMATION
# SLOT: the client's `Standard Booth.xlsx` (2026-09-01) states 0.5 m/s and
# computes its entire standard-booth table from it, for wet and dry alike. The
# 0.45 this held was the NFPA 33 default, used only while the client's own
# document was silent about it (DQ-2, adopted by the product owner 2026-09-01).
# Overridable per call, and per design via `compute_spec(face_velocity=...)`.
DEFAULT_FACE_VELOCITY = 0.50

# Inlet (make-up) air as a fraction of exhaust, per the client's document.
# Booths run NEGATIVE (inlet < exhaust) so contaminated air cannot escape;
# rooms/zones run POSITIVE (inlet > exhaust) to keep dust out. "nil" = no
# forced make-up air, the unit draws from the shop.
INLET_ADD_10 = 1.10     # "Exhaust air volume x 10% add"
INLET_LESS_10 = 0.90    # "Exhaust air volume x 10% less"
INLET_NIL = None        # "nil"

# Sheet-metal basis for turning a surface AREA into a material WEIGHT. Both
# figures are evidenced, not assumed: the client's costed booth BOM (24.07.2026)
# builds the enclosure from "MS 14 SWG Sheet 2500 x 1250 x 2 thk", i.e. 2 mm
# mild-steel sheet; 7850 kg/m3 is the standard density of mild steel.
SHEET_THICKNESS_MM = 2.0
STEEL_DENSITY_KG_M3 = 7850.0

# Oven heat load, exactly as the client states it: 100 ft3 of oven volume needs
# 12 kW, and 1 kW = 860 kCal.
OVEN_KW_PER_100_FT3 = 12.0
KCAL_PER_KW = 860.0
_FT3_PER_M3 = 35.3147


class Draft:
    """Airflow direction through the enclosure (the client's 'Type' field)."""
    DOWN = "down draft"
    SIDE = "side draft"
    CROSS = "cross draft"


# Which plane the air actually passes through, per draft direction. Air moves:
#   down draft  - vertically, through the PLAN area          -> length x width
#   cross draft - horizontally front-to-rear, through the END -> width x height
#   side draft  - horizontally side-to-side, through the SIDE -> length x height
_FACE_AREA = {
    Draft.DOWN:  lambda L, W, H: (L * W, f"plan area {L:g} x {W:g} m"),
    Draft.CROSS: lambda L, W, H: (W * H, f"end face {W:g} x {H:g} m"),
    Draft.SIDE:  lambda L, W, H: (L * H, f"side face {L:g} x {H:g} m"),
}

# Inlet rule per unit type, from the client's document.
#   cleaning room / buffing booth / flash off zone : "+10% add"
#   paint booth side draft                          : "nil"
#   paint booth cross draft / down draft            : "-10% less"
_INLET_RULE = {
    "cleaning_room": lambda draft: INLET_ADD_10,
    "buffing_booth": lambda draft: INLET_ADD_10,
    "flash_off_zone": lambda draft: INLET_ADD_10,
    "paint_booth": lambda draft: INLET_NIL if draft == Draft.SIDE else INLET_LESS_10,
}

# Units whose material weight includes a SUCTION CHAMBER as well as the
# enclosure ("Booth Total Surface area ... + Suction chamber total area"),
# per the client's document.
_HAS_SUCTION_CHAMBER = {"buffing_booth", "paint_booth"}


class PaintShopCalc(NamedTuple):
    """Everything the client's calculation yields for one paint-shop unit.

    Any field may be None when the input needed for it was not supplied — an
    honest gap the caller renders as TBD, never a filled-in guess.
    """
    exhaust_cmh: Optional[float]
    exhaust_cfm: Optional[float]
    inlet_cmh: Optional[float]
    face_area_m2: Optional[float]
    surface_area_m2: Optional[float]
    material_weight_kg: Optional[float]
    heat_load_kw: Optional[float] = None
    heat_load_kcal: Optional[float] = None
    trail: tuple = ()        # (name, value, formula, standard) per computed row


def normalise_draft(booth_type: Optional[str]) -> Optional[str]:
    """Map free text from a requirement ('wet cross draft', 'Down-Draft') onto a
    Draft constant. Returns None when the text names no recognised direction —
    the caller then keeps the engine's existing default behaviour rather than
    picking a direction on the customer's behalf."""
    b = (booth_type or "").lower().replace("-", " ")
    if "down" in b and "draft" in b:
        return Draft.DOWN
    if "cross" in b and "draft" in b:
        return Draft.CROSS
    if "side" in b and "draft" in b:
        return Draft.SIDE
    return None


def enclosure_surface_area(length_m: float, width_m: float, height_m: float) -> float:
    """'Total Surface area (5 Sides - bottom side neglected)', m2.
    Four walls plus the roof; the floor is excluded exactly as the client states."""
    walls = 2 * (length_m * height_m) + 2 * (width_m * height_m)
    roof = length_m * width_m
    return walls + roof


def sheet_weight_kg(area_m2: float, thickness_mm: float = SHEET_THICKNESS_MM) -> float:
    """Mild-steel sheet weight for a given surface area."""
    return area_m2 * (thickness_mm / 1000.0) * STEEL_DENSITY_KG_M3


def oven_heat_load(length_m: float, width_m: float, height_m: float) -> tuple[float, float]:
    """Oven heat load per the client's rule: volume(ft3)/100 x 12 kW, then
    kW x 860 = kCal. Returns (kW, kCal)."""
    volume_ft3 = (length_m * width_m * height_m) * _FT3_PER_M3
    kw = (volume_ft3 / 100.0) * OVEN_KW_PER_100_FT3
    return kw, kw * KCAL_PER_KW


def compute_paint_shop_unit(unit: str,
                            length_m: Optional[float],
                            width_m: Optional[float],
                            height_m: Optional[float],
                            draft: Optional[str] = None,
                            face_velocity: float = DEFAULT_FACE_VELOCITY,
                            ach: Optional[float] = None) -> PaintShopCalc:
    """Run the client's paint-shop calculation for one unit.

    `unit` is one of: cleaning_room, buffing_booth, paint_booth, flash_off_zone,
    paint_drying_room, paint_drying_oven.

    Airflow basis differs by unit, exactly as the document splits them:
      * enclosures (rooms/booths/zones) -> Area x Velocity
      * drying room / oven              -> Volume x ACH  (needs `ach`; no default)
    """
    trail: list[tuple] = []
    if length_m is None or width_m is None or height_m is None:
        return PaintShopCalc(None, None, None, None, None, None, trail=tuple(trail))

    L, W, H = float(length_m), float(width_m), float(height_m)
    is_thermal = unit in ("paint_drying_room", "paint_drying_oven")

    # --- Exhaust air volume ------------------------------------------------
    exhaust = None
    face_area = None
    if is_thermal:
        if ach is not None:
            volume = L * W * H
            exhaust = volume * float(ach)
            trail.append(("Exhaust air volume", f"{round(exhaust)} m3/h",
                          f"volume {L:g} x {W:g} x {H:g} = {volume:g} m3 x {ach:g} ACH",
                          std.CLIENT_PAINT_SHOP_CALC))
    else:
        area_fn = _FACE_AREA.get(draft)
        if area_fn:
            face_area, area_desc = area_fn(L, W, H)
        else:
            # No draft direction stated: keep the engine's long-standing default
            # (the open working face, width x height) rather than choosing a
            # direction the customer never specified.
            face_area, area_desc = W * H, f"open face {W:g} x {H:g} m"
        exhaust = face_area * face_velocity * 3600
        trail.append(("Exhaust air volume", f"{round(exhaust)} m3/h",
                      f"{area_desc} = {face_area:g} m2 x velocity {face_velocity:g} m/s x 3600",
                      std.CLIENT_PAINT_SHOP_CALC))

    # --- Inlet (make-up) air volume ---------------------------------------
    inlet = None
    if exhaust is not None:
        rule = _INLET_RULE.get(unit)
        factor = rule(draft) if rule else None
        if factor is not None:
            inlet = exhaust * factor
            pct = "10% add" if factor > 1 else "10% less"
            trail.append(("Inlet air volume", f"{round(inlet)} m3/h",
                          f"exhaust {round(exhaust)} m3/h {pct}",
                          std.CLIENT_PAINT_SHOP_CALC))
        elif unit == "paint_booth" and draft == Draft.SIDE:
            trail.append(("Inlet air volume", "nil",
                          "side-draft paint booth draws make-up air from the shop",
                          std.CLIENT_PAINT_SHOP_CALC))

    # --- Material weight from 5-side surface area -------------------------
    surface = enclosure_surface_area(L, W, H)
    desc = f"4 walls + roof of {L:g} x {W:g} x {H:g} m (floor excluded)"
    if unit in _HAS_SUCTION_CHAMBER:
        # The client counts the suction chamber's own 5-sided area as well. Its
        # size is a separate design output, so it is NOT assumed here — the
        # enclosure area is reported and the chamber is flagged in the formula.
        desc += "; suction chamber area additional (sized separately)"
    weight = sheet_weight_kg(surface)
    trail.append(("Enclosure surface area", f"{surface:.1f} m2", desc,
                  std.CLIENT_PAINT_SHOP_CALC))
    trail.append(("Enclosure sheet weight", f"{round(weight)} kg",
                  f"{surface:.1f} m2 x {SHEET_THICKNESS_MM:g} mm MS sheet "
                  f"x {STEEL_DENSITY_KG_M3:g} kg/m3",
                  std.MS_SHEET_BASIS))

    # --- Oven thermal load -------------------------------------------------
    kw = kcal = None
    if unit == "paint_drying_oven":
        kw, kcal = oven_heat_load(L, W, H)
        trail.append(("Heat load", f"{kw:.1f} kW",
                      f"volume {(L * W * H) * _FT3_PER_M3:.0f} ft3 / 100 x "
                      f"{OVEN_KW_PER_100_FT3:g} kW",
                      std.CLIENT_OVEN_HEAT_LOAD))
        trail.append(("Heat load (kCal)", f"{round(kcal)} kCal",
                      f"{kw:.1f} kW x {KCAL_PER_KW:g}",
                      std.CLIENT_OVEN_HEAT_LOAD))

    return PaintShopCalc(
        exhaust_cmh=exhaust,
        exhaust_cfm=(exhaust / CFM_TO_CMH) if exhaust is not None else None,
        inlet_cmh=inlet,
        face_area_m2=face_area,
        surface_area_m2=surface,
        material_weight_kg=weight,
        heat_load_kw=kw,
        heat_load_kcal=kcal,
        trail=tuple(trail),
    )
