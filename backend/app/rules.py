"""Engineering Rule Engine — the knowledge in 'knowledge-based'.

These are deterministic engineering rules, not LLM guesses. Every value the
system recommends can be traced to a formula and a governing standard. The
SAME engine is reused by the spec generator now and by the quotation generator
in Phase 2 (materials/airflow drive BOM and price).

Constants are the ATS design standard; tune them in one place.
"""
import math
from typing import Optional

from .schema import ComputedSpec, RuleResult, SpecValue

# --- ATS / NFPA design constants -------------------------------------------
FACE_VELOCITY = 0.45          # m/s across the open face (NFPA 33 range 0.4-0.5)
FAN_CAPACITY = 13000          # m3/h handled by one axial exhaust fan
FILTERS_PER_M2 = 0.6          # dry filter panels per m2 of floor area
DEFAULT_HEIGHT = 4.0          # assumed booth height when not specified

# material / filtration selection by paint process
PROCESS_RULES = {
    "powder":  {"material": "GI",    "filter_type": "dry"},
    "liquid":  {"material": "SS304", "filter_type": "water-wash"},
    "solvent": {"material": "SS304", "filter_type": "water-wash"},
    "water-based": {"material": "GI", "filter_type": "dry"},
}


def _round(x: float, step: int = 10) -> int:
    return int(round(x / step) * step)


def compute_spec(length_m: Optional[float], width_m: Optional[float],
                 height_m: Optional[float] = None,
                 paint_type: Optional[str] = None) -> ComputedSpec:
    """Apply engineering rules to a requirement. Returns computed values, each
    tagged with provenance, plus the rule trail (formula + standard)."""
    spec = ComputedSpec(length_m=length_m, width_m=width_m, height_m=height_m)
    if length_m is None or width_m is None:
        return spec  # not enough to compute a booth; caller handles concept Qs

    height = height_m or DEFAULT_HEIGHT
    spec.height_m = height
    paint = (paint_type or "powder").lower()
    proc = PROCESS_RULES.get(paint, PROCESS_RULES["powder"])

    face_area = width_m * height          # open working face
    floor_area = length_m * width_m
    airflow = face_area * FACE_VELOCITY * 3600
    fans = max(1, math.ceil(airflow / FAN_CAPACITY))
    filters = max(1, math.ceil(floor_area * FILTERS_PER_M2))

    spec.rules = [
        RuleResult(name="Exhaust airflow", value=f"{_round(airflow, 10)} m3/h",
                   formula=f"face area {width_m}x{height} x velocity {FACE_VELOCITY} m/s x 3600",
                   standard="NFPA 33 (face velocity 0.4-0.5 m/s)"),
        RuleResult(name="Exhaust fans", value=str(fans),
                   formula=f"ceil(airflow / {FAN_CAPACITY} m3/h per fan)",
                   standard="ATS fan-sizing standard"),
        RuleResult(name="Dry filters", value=str(filters),
                   formula=f"ceil(floor area {floor_area:g} m2 x {FILTERS_PER_M2}/m2)",
                   standard="ATS overspray-capture standard"),
        RuleResult(name="Construction", value=proc["material"],
                   formula=f"{paint} process -> {proc['material']} / {proc['filter_type']} filtration",
                   standard="ATS material-selection standard"),
    ]

    spec.values = [
        SpecValue(label="Dimensions", value=f"{length_m:g} x {width_m:g} x {height:g} m", origin="rule"),
        SpecValue(label="Exhaust airflow", value=f"{_round(airflow, 10)} m3/h", origin="rule"),
        SpecValue(label="Exhaust fans", value=str(fans), origin="rule"),
        SpecValue(label="Filters", value=f"{filters} ({proc['filter_type']})", origin="rule"),
        SpecValue(label="Construction material", value=proc["material"], origin="rule"),
        SpecValue(label="Paint process", value=paint, origin="rule"),
    ]
    return spec


# === Wet scrubber design rules ============================================
# Field-level engineering rules: given the requirement, compute the key sizing
# values from first principles. Constants are the ATS design standard and are
# CALIBRATED against historical offer OFF-C2C-WS-172 (735 CFM -> 17 nozzles,
# 1.0 HP pump), so the formulas reproduce real designs rather than guess.
WS_LG_RATIO = 5.0             # recirculation liquid-to-gas ratio, L per m3 of gas
WS_NOZZLE_LPM = 6.0           # spray-nozzle throughput at design pressure, L/min
WS_PUMP_HEAD_M = 25.0         # total pump head: nozzle pressure + static + losses
WS_PUMP_EFF = 0.60            # combined pump + motor efficiency
WS_TANK_RETENTION_MIN = 2.5   # recirculation tank retention time, minutes
WS_HEIGHT_PER_DIA = 5.0       # spray-tower height / diameter (gas-liquid contact)
WS_MIN_HEIGHT_M = 3.0
_CFM_TO_CMH = 1.699
_G = 9.81                     # m/s^2


def _air_cmh(params: dict) -> Optional[float]:
    q = params.get("air_volume_cmh")
    if isinstance(q, (int, float)):
        return float(q)
    cfm = params.get("air_volume_cfm")
    return float(cfm) * _CFM_TO_CMH if isinstance(cfm, (int, float)) else None


def compute_wet_scrubber(params: dict) -> dict[str, dict]:
    """Return {technical_field: {value, formula, standard}} for the values that
    engineering formulas can determine. The caller keeps client-supplied values
    authoritative and snaps results to standard sizes."""
    out: dict[str, dict] = {}
    q_cmh = _air_cmh(params)
    if not q_cmh:
        return out

    # Recirculation liquid flow that everything else derives from.
    l_lpm = WS_LG_RATIO * q_cmh / 60.0

    nozzles = max(1, round(l_lpm / WS_NOZZLE_LPM))
    out["spray_nozzle_nos"] = {
        "value": nozzles,
        "formula": (f"recirculation L/G {WS_LG_RATIO} L/m3 x {round(q_cmh)} m3/h "
                    f"= {round(l_lpm)} L/min, / {WS_NOZZLE_LPM:g} L/min per nozzle"),
        "standard": "ATS wet-scrubber spray-coverage standard",
    }

    q_ls = l_lpm / 60000.0                         # L/min -> m3/s
    hp = (1000 * _G * q_ls * WS_PUMP_HEAD_M / WS_PUMP_EFF) / 745.7
    out["pump_capacity_hp"] = {
        "value": hp,
        "formula": (f"P = rho.g.Q.H / eff with Q {round(l_lpm)} L/min, "
                    f"H {WS_PUMP_HEAD_M:g} m, eff {WS_PUMP_EFF:g}"),
        "standard": "Hydraulic pump-power formula",
    }

    out["tank_capacity_litre"] = {
        "value": l_lpm * WS_TANK_RETENTION_MIN,
        "formula": f"{round(l_lpm)} L/min x {WS_TANK_RETENTION_MIN:g} min retention",
        "standard": "ATS recirculation-tank standard",
    }

    d_mm = params.get("tower_diameter_mm")
    if isinstance(d_mm, (int, float)):
        h = max(WS_MIN_HEIGHT_M, WS_HEIGHT_PER_DIA * d_mm / 1000.0)
        out["tower_height_m"] = {
            "value": h,
            "formula": f"{WS_HEIGHT_PER_DIA:g} x tower diameter {d_mm:g} mm (gas-liquid contact height)",
            "standard": "ATS spray-tower height standard",
        }
    return out
