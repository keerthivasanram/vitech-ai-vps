"""Per-equipment engineering formulas — the knowledge in 'knowledge-based'.

These are deterministic engineering rules, not LLM guesses: every value traces
to a formula (here), a unit basis (unit_converter), a governing standard
(standards_service), and a material rule (material_service). The same engine
feeds the spec generator and the quotation BOM.

The DESIGN CONSTANTS below are the ATS design standard and the primary surface
the client tunes/overrides ("the client will provide details") — they are
calibrated against real historical offers (e.g. wet scrubber against
OFF-C2C-WS-172: 735 CFM -> 17 nozzles, 1.0 HP pump) so the formulas reproduce
actual designs rather than guess. Change a constant in ONE place here.
"""
from typing import Optional

from ..schema import ComputedSpec, RuleResult, SpecValue
from . import standards_service as std
from .calculation_engine import count_ceil, count_round, round_to_step
from .material_service import select_paint_process
from .unit_converter import air_cmh

# --- Paint booth design constants (NFPA 33 / ATS) --------------------------
FACE_VELOCITY = 0.45          # m/s across the open face (NFPA 33 range 0.4-0.5)
FAN_CAPACITY = 13000          # m3/h handled by one axial exhaust fan
FILTERS_PER_M2 = 0.6          # dry filter panels per m2 of floor area
DEFAULT_HEIGHT = 4.0          # assumed booth height when not specified

# --- Wet scrubber design constants (ATS, calibrated to OFF-C2C-WS-172) -----
WS_LG_RATIO = 5.0             # recirculation liquid-to-gas ratio, L per m3 of gas
WS_NOZZLE_LPM = 6.0           # spray-nozzle throughput at design pressure, L/min
WS_PUMP_HEAD_M = 25.0         # total pump head: nozzle pressure + static + losses
WS_PUMP_EFF = 0.60            # combined pump + motor efficiency
WS_TANK_RETENTION_MIN = 2.5   # recirculation tank retention time, minutes
WS_HEIGHT_PER_DIA = 5.0       # spray-tower height / diameter (gas-liquid contact)
WS_MIN_HEIGHT_M = 3.0
_G = 9.81                     # m/s^2


def compute_spec(length_m: Optional[float], width_m: Optional[float],
                 height_m: Optional[float] = None,
                 paint_type: Optional[str] = None,
                 booth_type: Optional[str] = None) -> ComputedSpec:
    """Apply engineering rules to a paint-booth requirement. Returns computed
    values, each tagged with provenance, plus the rule trail (formula + standard).
    booth_type is honoured so a liquid booth's filtration/material stays coherent
    with the actual booth design (dry-filter unless a water-wash booth)."""
    spec = ComputedSpec(length_m=length_m, width_m=width_m, height_m=height_m)
    if length_m is None or width_m is None:
        return spec  # not enough to compute a booth; caller handles concept Qs

    height = height_m or DEFAULT_HEIGHT
    spec.height_m = height
    paint = (paint_type or "powder").lower()
    proc = select_paint_process(paint_type, booth_type)

    face_area = width_m * height          # open working face
    floor_area = length_m * width_m
    airflow = face_area * FACE_VELOCITY * 3600
    fans = count_ceil(airflow / FAN_CAPACITY)
    filters = count_ceil(floor_area * FILTERS_PER_M2)

    spec.rules = [
        RuleResult(name="Exhaust airflow", value=f"{round_to_step(airflow, 10)} m3/h",
                   formula=f"face area {width_m}x{height} x velocity {FACE_VELOCITY} m/s x 3600",
                   standard=std.NFPA_33_FACE_VELOCITY),
        RuleResult(name="Exhaust fans", value=str(fans),
                   formula=f"ceil(airflow / {FAN_CAPACITY} m3/h per fan)",
                   standard=std.ATS_FAN_SIZING),
        RuleResult(name="Dry filters", value=str(filters),
                   formula=f"ceil(floor area {floor_area:g} m2 x {FILTERS_PER_M2}/m2)",
                   standard=std.ATS_OVERSPRAY_CAPTURE),
        RuleResult(name="Construction", value=proc["material"],
                   formula=f"{paint} process -> {proc['material']} / {proc['filter_type']} filtration",
                   standard=std.ATS_MATERIAL_SELECTION),
    ]

    spec.values = [
        SpecValue(label="Dimensions", value=f"{length_m:g} x {width_m:g} x {height:g} m", origin="rule"),
        SpecValue(label="Exhaust airflow", value=f"{round_to_step(airflow, 10)} m3/h", origin="rule"),
        SpecValue(label="Exhaust fans", value=str(fans), origin="rule"),
        SpecValue(label="Filters", value=f"{filters} ({proc['filter_type']})", origin="rule"),
        SpecValue(label="Construction material", value=proc["material"], origin="rule"),
        SpecValue(label="Paint process", value=paint, origin="rule"),
    ]
    return spec


def compute_wet_scrubber(params: dict) -> dict[str, dict]:
    """Return {technical_field: {value, formula, standard}} for the values that
    engineering formulas can determine. The caller keeps client-supplied values
    authoritative and snaps results to standard sizes."""
    out: dict[str, dict] = {}
    q_cmh = air_cmh(params)
    if not q_cmh:
        return out

    # Recirculation liquid flow that everything else derives from.
    l_lpm = WS_LG_RATIO * q_cmh / 60.0

    nozzles = count_round(l_lpm / WS_NOZZLE_LPM)
    out["spray_nozzle_nos"] = {
        "value": nozzles,
        "formula": (f"recirculation L/G {WS_LG_RATIO} L/m3 x {round(q_cmh)} m3/h "
                    f"= {round(l_lpm)} L/min, / {WS_NOZZLE_LPM:g} L/min per nozzle"),
        "standard": std.ATS_SPRAY_COVERAGE,
    }

    q_ls = l_lpm / 60000.0                         # L/min -> m3/s
    hp = (1000 * _G * q_ls * WS_PUMP_HEAD_M / WS_PUMP_EFF) / 745.7
    out["pump_capacity_hp"] = {
        "value": hp,
        "formula": (f"P = rho.g.Q.H / eff with Q {round(l_lpm)} L/min, "
                    f"H {WS_PUMP_HEAD_M:g} m, eff {WS_PUMP_EFF:g}"),
        "standard": std.HYDRAULIC_PUMP_POWER,
    }

    out["tank_capacity_litre"] = {
        "value": l_lpm * WS_TANK_RETENTION_MIN,
        "formula": f"{round(l_lpm)} L/min x {WS_TANK_RETENTION_MIN:g} min retention",
        "standard": std.ATS_RECIRC_TANK,
    }

    d_mm = params.get("tower_diameter_mm")
    if isinstance(d_mm, (int, float)):
        h = max(WS_MIN_HEIGHT_M, WS_HEIGHT_PER_DIA * d_mm / 1000.0)
        out["tower_height_m"] = {
            "value": h,
            "formula": f"{WS_HEIGHT_PER_DIA:g} x tower diameter {d_mm:g} mm (gas-liquid contact height)",
            "standard": std.ATS_SPRAY_TOWER_HEIGHT,
        }
    return out
