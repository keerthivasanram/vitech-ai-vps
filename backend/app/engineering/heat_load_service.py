"""Heat load for a process tank, a dry-off oven and a curing oven.

Source: the client's own workbook `Heat Load.xlsx` (delivered 2026-09-01),
transcribed in `docs/client-calculation-sheets.md` §2. Three sheets, one shared
conversion (`kW = ROUNDUP(Kcal / 860)`) and one shared set of thermal constants.

This is the rule behind the standing gap recorded in CLAUDE.md — "the oven
computes surface area and sheet weight but reports exhaust as TBD until an ACH
is supplied". An oven's HEAT LOAD no longer needs an ACH: it follows from the
mass being heated and the temperature rise, which is what these sheets compute.

TWO THINGS ARE DELIBERATELY NOT COMPUTED HERE:

  * **The dry-off oven's air term.** Its sheet multiplies the chamber volume by
    `101.325` to get an air mass — that is standard atmospheric PRESSURE in kPa,
    not a density, and the curing-oven sheet uses `1.204 kg/m3` for the same
    quantity. Read as a density it is ~84x too high. This is open question DQ-1;
    until Vitech answers it the air term is omitted unless the caller passes an
    explicit `air_density_kg_m3`, and the result says so. Silently "correcting"
    a client formula would put engineering we invented into a customer document.
  * **Anything the caller did not supply.** A curing oven's load depends on the
    conveyor and jig masses; absent them the steel term covers the shell only
    and the result names what is missing.
"""
import math
from typing import NamedTuple, Optional

from . import standards_service as std

# --- thermal constants, as stated on the sheets ---------------------------
SPECIFIC_HEAT_STEEL = 0.11      # kcal/kg degC
SPECIFIC_HEAT_AIR = 0.24        # kcal/kg degC
SPECIFIC_HEAT_WATER = 1.04      # kcal/kg degC
STEEL_DENSITY_KG_M3 = 7850.0
WATER_DENSITY_KG_L = 1.0
AIR_DENSITY_KG_M3 = 1.204       # the curing-oven sheet's value
KCAL_PER_KW = 860.0

# The tank sheet leaves 200 mm of freeboard: the liquid volume is computed on
# (height - 200), not the full tank height.
TANK_FREEBOARD_MM = 200.0

# Sheet margins: the dry-off oven adds 10% to each term, the curing oven adds
# 15% to the total.
DRY_OFF_MARGIN = 1.10
CURING_MARGIN = 1.15

# Insulation U-values, W/m2K, by panel thickness in mm (curing-oven sheet).
INSULATION_U_BY_THICKNESS_MM = {50: 0.4, 100: 0.35, 150: 0.3}

# The disputed dry-off air factor, kept as data so the question is visible in
# code rather than only in a document. NOT used unless a caller asks for it.
DRY_OFF_SHEET_AIR_FACTOR = 101.325   # DQ-1: kPa, almost certainly a typo


def _roundup(value: float) -> int:
    """`ROUNDUP(x, 0)` as the workbooks use it."""
    return int(math.ceil(value - 1e-9))


def kw_from_kcal(kcal: float) -> int:
    """`kW = ROUNDUP(Kcal / 860, 0)` — the conversion every sheet ends on."""
    return _roundup(kcal / KCAL_PER_KW)


class HeatLoad(NamedTuple):
    """A heat-load result and everything it was built from.

    `kcal` / `kw` are None when a required input was missing; `gaps` then names
    what was not supplied.
    """
    kcal: Optional[float]
    kw: Optional[int]
    components: dict            # named kcal contributions
    gaps: tuple = ()            # inputs that were missing or deliberately omitted
    trail: tuple = ()           # (name, value, formula, standard)


def oven_shell_steel_mass_kg(length_m: float, width_m: float, height_m: float,
                             thickness_mm: float) -> int:
    """Shell steel mass for an oven, per the sheets' own expression:

        ROUNDUP(((L*H)*2 + (W*H)*2 + (L*W)*3) * 7850/1000 * thk_mm, 0)

    The floor/roof term is counted three times (roof, floor and the false
    ceiling / plenum), exactly as the client writes it."""
    area_term = (length_m * height_m) * 2 + (width_m * height_m) * 2 + (length_m * width_m) * 3
    return _roundup(area_term * (STEEL_DENSITY_KG_M3 / 1000.0) * float(thickness_mm))


def tank_heat_load(length_mm: float, width_mm: float, height_mm: float,
                   temp_from_c: float, temp_to_c: float,
                   tank_steel_mass_kg: float) -> HeatLoad:
    """Process-tank heat load: heat the liquid, and heat the tank holding it.

    Anchor (the sheet's own worked example): 2250 x 1500 x 1500 mm, 25 -> 75 C,
    750 kg of tank steel -> 264,125 Kcal -> 308 kW.
    """
    dt = float(temp_to_c) - float(temp_from_c)
    volume_m3 = _roundup((length_mm / 1000.0) * (width_mm / 1000.0)
                         * ((height_mm - TANK_FREEBOARD_MM) / 1000.0))
    water_mass = volume_m3 * 1000.0 * WATER_DENSITY_KG_L
    kcal_water = water_mass * SPECIFIC_HEAT_WATER * dt
    kcal_steel = float(tank_steel_mass_kg) * SPECIFIC_HEAT_STEEL * dt
    kcal = kcal_water + kcal_steel
    kw = kw_from_kcal(kcal)
    trail = (
        ("Solution volume", f"{volume_m3} m3",
         f"{length_mm:g} x {width_mm:g} x ({height_mm:g} - {TANK_FREEBOARD_MM:g}) mm, rounded up",
         std.CLIENT_HEAT_LOAD_CALC),
        ("Heat load", f"{kw} kW",
         f"({water_mass:g} kg x {SPECIFIC_HEAT_WATER} x {dt:g}) + "
         f"({float(tank_steel_mass_kg):g} kg x {SPECIFIC_HEAT_STEEL} x {dt:g}) "
         f"= {kcal:g} Kcal / {KCAL_PER_KW:g}", std.CLIENT_HEAT_LOAD_CALC),
    )
    return HeatLoad(kcal, kw,
                    {"solution": kcal_water, "tank_steel": kcal_steel},
                    (), trail)


def dry_off_oven_heat_load(length_m: float, width_m: float, height_m: float,
                           temp_from_c: float, temp_to_c: float,
                           thickness_mm: float,
                           job_mass_kg: Optional[float] = None,
                           jobs_per_hour: Optional[float] = None,
                           air_density_kg_m3: Optional[float] = None) -> HeatLoad:
    """Dry-off oven heat load: shell steel + the hourly job load, +10%.

    The air term is included ONLY when `air_density_kg_m3` is given, because the
    sheet's own factor is dimensionally wrong (DQ-1). Without it the result
    carries a gap saying the air term is outstanding rather than pretending the
    total is complete.
    """
    dt = float(temp_to_c) - float(temp_from_c)
    gaps: list[str] = []

    steel_mass = oven_shell_steel_mass_kg(length_m, width_m, height_m, thickness_mm)
    if job_mass_kg is None or jobs_per_hour is None:
        gaps.append("job mass per hour not supplied; shell steel only")
        job_load = 0.0
    else:
        job_load = float(job_mass_kg) * float(jobs_per_hour)
    total_mass = job_load + steel_mass
    kcal_steel = float(_roundup(total_mass * SPECIFIC_HEAT_STEEL * dt * DRY_OFF_MARGIN))

    components = {"steel_and_load": kcal_steel}
    trail = [("Shell steel mass", f"{steel_mass} kg",
              f"({length_m:g}x{height_m:g})x2 + ({width_m:g}x{height_m:g})x2 + "
              f"({length_m:g}x{width_m:g})x3 m2 x 7.85 x {float(thickness_mm):g} mm",
              std.CLIENT_HEAT_LOAD_CALC),
             ("Steel + load heat", f"{kcal_steel:g} Kcal",
              f"{total_mass:g} kg x {SPECIFIC_HEAT_STEEL} x {dt:g} +10%",
              std.CLIENT_HEAT_LOAD_CALC)]

    if air_density_kg_m3 is None:
        gaps.append("air heat term omitted: the sheet's air density is under query (DQ-1)")
        kcal = kcal_steel
    else:
        air_mass = (length_m * width_m * height_m) * float(air_density_kg_m3)
        kcal_air = float(_roundup(air_mass * SPECIFIC_HEAT_AIR * dt * DRY_OFF_MARGIN))
        components["air"] = kcal_air
        kcal = kcal_steel + kcal_air
        trail.append(("Air heat", f"{kcal_air:g} Kcal",
                      f"{air_mass:g} kg x {SPECIFIC_HEAT_AIR} x {dt:g} +10% "
                      f"(density {float(air_density_kg_m3):g} kg/m3 supplied by caller)",
                      std.CLIENT_HEAT_LOAD_CALC))

    kw = kw_from_kcal(kcal)
    trail.append(("Heat load", f"{kw} kW", f"{kcal:g} Kcal / {KCAL_PER_KW:g}",
                  std.CLIENT_HEAT_LOAD_CALC))
    return HeatLoad(kcal, kw, components, tuple(gaps), tuple(trail))


def insulation_loss_kw(length_m: float, width_m: float, height_m: float,
                       delta_t: float, thickness_mm: int) -> Optional[int]:
    """Steady-state loss through the insulated envelope, kW.

        area = ROUNDUP((L*H) + (W*H) + (L*W))     # the sheet's own area term
        kW   = ROUNDUP(area x dT x U / 1000)

    Returns None for a thickness the client has given no U-value for — the
    ladder is 50 / 100 / 150 mm and nothing is interpolated between them."""
    u = INSULATION_U_BY_THICKNESS_MM.get(int(thickness_mm))
    if u is None:
        return None
    area = _roundup((length_m * height_m) + (width_m * height_m) + (length_m * width_m))
    return _roundup(area * float(delta_t) * u / 1000.0)


def curing_oven_heat_load(length_m: float, width_m: float, height_m: float,
                          temp_from_c: float, temp_to_c: float,
                          thickness_mm: float,
                          conveyor_mass_kg: Optional[float] = None,
                          job_mass_kg: Optional[float] = None,
                          insulation_thickness_mm: Optional[int] = None) -> HeatLoad:
    """Curing-oven heat load: shell + conveyor + job steel, plus the air, +15%.

    Conveyor and job masses are the customer's/design's, not ours to invent: when
    either is absent it contributes nothing and the gap is reported, so a total
    is never presented as complete when it is not.
    """
    dt = float(temp_to_c) - float(temp_from_c)
    gaps: list[str] = []

    steel_mass = oven_shell_steel_mass_kg(length_m, width_m, height_m, thickness_mm)
    if conveyor_mass_kg is None:
        gaps.append("conveyor mass not supplied")
    if job_mass_kg is None:
        gaps.append("job + jig mass not supplied")
    moving_mass = float(conveyor_mass_kg or 0.0) + float(job_mass_kg or 0.0)
    kcal_steel = float(_roundup((steel_mass + moving_mass) * SPECIFIC_HEAT_STEEL * dt))

    air_mass = (length_m * width_m * height_m) * AIR_DENSITY_KG_M3
    kcal_air = float(_roundup(air_mass * SPECIFIC_HEAT_AIR * dt))

    kcal = (kcal_steel + kcal_air) * CURING_MARGIN
    kw = kw_from_kcal(kcal)

    components = {"steel_and_load": kcal_steel, "air": kcal_air}
    trail = [("Shell steel mass", f"{steel_mass} kg",
              f"({length_m:g}x{height_m:g})x2 + ({width_m:g}x{height_m:g})x2 + "
              f"({length_m:g}x{width_m:g})x3 m2 x 7.85 x {float(thickness_mm):g} mm",
              std.CLIENT_HEAT_LOAD_CALC),
             ("Steel heat", f"{kcal_steel:g} Kcal",
              f"({steel_mass} + {moving_mass:g}) kg x {SPECIFIC_HEAT_STEEL} x {dt:g}",
              std.CLIENT_HEAT_LOAD_CALC),
             ("Air heat", f"{kcal_air:g} Kcal",
              f"{air_mass:g} kg x {SPECIFIC_HEAT_AIR} x {dt:g} "
              f"(density {AIR_DENSITY_KG_M3} kg/m3)", std.CLIENT_HEAT_LOAD_CALC),
             ("Heat load", f"{kw} kW",
              f"({kcal_steel:g} + {kcal_air:g}) Kcal +15% / {KCAL_PER_KW:g}",
              std.CLIENT_HEAT_LOAD_CALC)]

    if insulation_thickness_mm is not None:
        loss = insulation_loss_kw(length_m, width_m, height_m, dt, insulation_thickness_mm)
        if loss is None:
            gaps.append(f"no U-value on file for {insulation_thickness_mm} mm insulation")
        else:
            components["insulation_loss_kw"] = loss
            trail.append(("Insulation loss", f"{loss} kW",
                          f"envelope area x {dt:g} K x U "
                          f"{INSULATION_U_BY_THICKNESS_MM[int(insulation_thickness_mm)]} W/m2K",
                          std.CLIENT_HEAT_LOAD_CALC))

    return HeatLoad(kcal, kw, components, tuple(gaps), tuple(trail))
