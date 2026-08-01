"""Vitech engineering standards — the client's design rules, as executable data.

Source: "Engineering Standards Package for ATS Engineering Specification
Generator" (client, 2026-08-01). This module replaces the seeded placeholders
the client's spec review flagged (`FILTERS_PER_M2`, a single global
`FACE_VELOCITY`, the hard water-based -> GI mapping) with their actual standards,
and turns fields that were "To be determined" into calculated selections.

DATA first, then the SELECTION functions that consume it — so a standard can be
revised in one obvious place without touching the calculations.
"""
import math
from typing import NamedTuple, Optional

# ===========================================================================
# 1. BOOTH TYPE VOCABULARY  — canonical types and their design face velocity
# ===========================================================================
class BoothType(NamedTuple):
    key: str
    label: str
    velocity: float                 # m/s, the single design value
    velocity_range: tuple           # (min, max) as published
    filtration: str                 # dry | water-wash | powder


BOOTH_TYPES: dict[str, BoothType] = {
    "cross_draft":      BoothType("cross_draft", "Dry Filter Cross Draft", 0.45, (0.45, 0.45), "dry"),
    "side_draft":       BoothType("side_draft", "Dry Filter Side Draft", 0.45, (0.45, 0.45), "dry"),
    "semi_down_draft":  BoothType("semi_down_draft", "Dry Filter Semi Down Draft", 0.45, (0.45, 0.45), "dry"),
    "full_down_draft":  BoothType("full_down_draft", "Dry Filter Full Down Draft", 0.35, (0.30, 0.35), "dry"),
    "water_wash":       BoothType("water_wash", "Water Wash Booth", 0.50, (0.50, 0.50), "water-wash"),
    "powder":           BoothType("powder", "Powder Coating Booth", 0.55, (0.50, 0.60), "powder"),
    "pressurized":      BoothType("pressurized", "Pressurized Paint Booth", 0.35, (0.30, 0.35), "dry"),
}

# Synonym -> canonical key. Longest match wins, so "semi down draft" is not
# swallowed by "down draft". "side down draft" appears in the historical archive
# and is NOT a standard type — it resolves to side draft and is flagged.
_BOOTH_SYNONYMS: list[tuple[str, str]] = [
    ("semi down draft", "semi_down_draft"), ("semi downdraft", "semi_down_draft"),
    ("full down draft", "full_down_draft"), ("full downdraft", "full_down_draft"),
    ("side down draft", "side_draft"),      # non-standard archive wording
    ("down draft", "full_down_draft"), ("downdraft", "full_down_draft"),
    ("cross draft", "cross_draft"), ("cross flow", "cross_draft"),
    ("side draft", "side_draft"),
    ("water curtain", "water_wash"), ("water wash", "water_wash"),
    ("water wall", "water_wash"), ("wet ", "water_wash"),
    ("powder", "powder"),
    ("positive pressure", "pressurized"), ("pressurized", "pressurized"),
    ("pressurised", "pressurized"),
]
NON_STANDARD_WORDINGS = ("side down draft",)
DEFAULT_BOOTH = "cross_draft"

# ===========================================================================
# 2. PAINT ARRESTING FILTER STANDARD
# ===========================================================================
FILTER_SIZES = [
    {"key": "600x600", "label": "600 x 600 x 50 mm", "area_m2": 0.36},
    {"key": "610x610", "label": "610 x 610 x 50 mm", "area_m2": 0.372},
    {"key": "1200x600", "label": "1200 x 600 x 50 mm", "area_m2": 0.72},
]
PREFERRED_FILTER = "600x600"
FILTER_MEDIA_VELOCITY = 1.0             # m/s; recommended band 0.8-1.2
FILTER_MEDIA_VELOCITY_RANGE = (0.8, 1.2)
FILTER_PRESSURE_DROP = {                # Pa, initial -> final
    "paint_arrestor": (25, 125),
    "pre_filter": (40, 150),
    "ceiling_filter": (60, 180),
}

# ===========================================================================
# 3. LIGHTING STANDARD
# ===========================================================================
TARGET_LUX = {
    "manual_painting": 750,
    "inspection": 1000,
    "powder": 750,
    "general": 500,
}
FIXTURES = [
    {"key": "led_20", "label": "20 W weatherproof LED", "lumens": 2200, "watts": 20},
    {"key": "led_40", "label": "40 W weatherproof LED", "lumens": 4400, "watts": 40},
    {"key": "led_60", "label": "60 W weatherproof LED", "lumens": 6600, "watts": 60},
]
PREFERRED_FIXTURE = "led_40"

# ===========================================================================
# 4. EXHAUST DUCT STANDARD
# ===========================================================================
TRANSPORT_VELOCITY = {"paint_fume": 18.0, "powder": 20.0, "solvent": 18.0}
STANDARD_DUCT_DIA_MM = [100, 125, 150, 200, 250, 300, 350, 400, 450, 500, 550,
                        600, 700, 800, 900, 1000, 1100, 1200, 1400, 1600, 1800, 2000]

# ===========================================================================
# 5. ELECTRICAL PANEL STANDARD
# ===========================================================================
HP_TO_KW = 0.746
PANEL_SPARE = 0.15                      # 15% spare capacity
STARTER_BANDS = [(7.5, "DOL"), (30.0, "Star Delta"), (float("inf"), "Soft Starter / VFD")]
PANEL_SCOPE = ["MCC panel", "Main isolator", "Emergency stop", "Overload relay",
               "Phase failure relay", "MCB / MCCB", "Contactor", "Indication lamps"]

# ===========================================================================
# 6. FIRE PROTECTION
# ===========================================================================
FIRE_PROTECTION = {
    "solvent": {"standard": "NFPA 33",
                "items": ["Flameproof components", "ABC extinguishers",
                          "Fire detection", "Interlocked shutdown"],
                "mandatory": True},
    "water-based": {"standard": "General industrial practice",
                    "items": ["ABC extinguishers", "Smoke detection", "Emergency stop"],
                    "mandatory": False},
    "powder": {"standard": "Powder booth practice",
               "items": ["Explosion venting", "Spark detection", "ABC extinguishers"],
               "mandatory": False},
}

# ===========================================================================
# 7. MATERIAL SELECTION MATRIX  (advisory, never asserted)
# ===========================================================================
MATERIAL_MATRIX = {
    "standard":   {"structure": "MS", "panels": "MS", "fasteners": "Zinc",
                   "reason": "standard industrial environment"},
    "water-based": {"structure": "MS", "panels": "GI", "fasteners": "Zinc",
                    "reason": "higher moisture exposure associated with water-based painting"},
    "high_humidity": {"structure": "GI", "panels": "GI", "fasteners": "SS304",
                      "reason": "sustained high humidity"},
    "corrosive":  {"structure": "SS304", "panels": "SS304", "fasteners": "SS304",
                   "reason": "corrosive chemical exposure"},
    "food_pharma": {"structure": "SS304", "panels": "SS304", "fasteners": "SS304",
                    "reason": "food / pharma hygiene requirements"},
}

# ===========================================================================
# 8. PROVENANCE TAGS + RELEASE STATUS
# ===========================================================================
SRC_CUSTOMER = "customer_input"
SRC_CALC = "calculation"
SRC_HISTORY = "historical"
SRC_STANDARD = "standard"
SRC_ADVISORY = "advisory"
SRC_DECISION = "customer_decision"

STATUS_ENGINEERING_DRAFT = "Engineering Draft"
STATUS_CUSTOMER_REVIEW = "Customer Review Draft"
STATUS_CUSTOMER_READY = "Customer Ready"
STATUS_RELEASED = "Released Design"

HISTORICAL_TOLERANCE = 0.20             # ±20% before a reused value needs review


# ===========================================================================
# SELECTION FUNCTIONS
# ===========================================================================
class Selection(NamedTuple):
    """One selected value with the formula and standard that produced it."""
    value: str
    formula: str
    source: str
    detail: dict = {}


def resolve_booth_type(text: Optional[str], paint_type: Optional[str] = None) -> tuple[BoothType, Optional[str]]:
    """Canonical booth type from free text, plus a warning when the source
    wording is not a standard type.

    Returns (BoothType, warning). Falls back to the paint process, then to the
    default — never to an invented type.
    """
    t = (text or "").lower().replace("-", " ")
    warning = None
    for phrase in NON_STANDARD_WORDINGS:
        if phrase in t:
            warning = (f'Historical wording "{phrase}" is not a standard booth type; '
                       f"resolved to the nearest standard configuration.")
            break
    for phrase, key in _BOOTH_SYNONYMS:
        if phrase in t:
            return BOOTH_TYPES[key], warning
    p = (paint_type or "").lower()
    if "powder" in p:
        return BOOTH_TYPES["powder"], warning
    return BOOTH_TYPES[DEFAULT_BOOTH], warning


def select_filters(airflow_cmh: float, size_key: str = PREFERRED_FILTER) -> Selection:
    """Paint-arresting filters from airflow and media velocity.

    Replaces the `FILTERS_PER_M2 = 0.6` placeholder: the count now follows from
    the airflow the filters actually have to pass.
    """
    size = next((s for s in FILTER_SIZES if s["key"] == size_key), FILTER_SIZES[0])
    required_area = airflow_cmh / (3600.0 * FILTER_MEDIA_VELOCITY)
    count = max(1, math.ceil(required_area / size["area_m2"]))
    lo, hi = FILTER_PRESSURE_DROP["paint_arrestor"]
    return Selection(
        value=f"{count} nos {size['label']}",
        formula=(f"required area {required_area:.1f} m2 = {round(airflow_cmh)} m3/h / "
                 f"(3600 x {FILTER_MEDIA_VELOCITY:g} m/s media velocity), "
                 f"/ {size['area_m2']:g} m2 per filter"),
        source=SRC_CALC,
        detail={"count": count, "size": size["label"], "area_m2": round(required_area, 2),
                "pressure_drop_pa": f"{lo} initial / {hi} final"},
    )


def select_lighting(floor_area_m2: float, application: str = "manual_painting",
                    fixture_key: str = PREFERRED_FIXTURE) -> Selection:
    """Luminaires by lux, replacing a fixture count copied from another booth."""
    lux = TARGET_LUX.get(application, TARGET_LUX["manual_painting"])
    fx = next((f for f in FIXTURES if f["key"] == fixture_key), FIXTURES[1])
    required_lumens = floor_area_m2 * lux
    count = max(1, math.ceil(required_lumens / fx["lumens"]))
    return Selection(
        value=f"{count} nos {fx['label']} ({lux} lux)",
        formula=(f"{floor_area_m2:g} m2 x {lux} lux = {round(required_lumens)} lm, "
                 f"/ {fx['lumens']} lm per fixture"),
        source=SRC_CALC,
        detail={"count": count, "lux": lux, "watts_total": count * fx["watts"],
                "fixture": fx["label"]},
    )


def select_duct(airflow_cmh: float, process: str = "paint_fume") -> Selection:
    """Exhaust duct from the airflow already computed — was left blank before."""
    v = TRANSPORT_VELOCITY.get(process, TRANSPORT_VELOCITY["paint_fume"])
    area = airflow_cmh / (v * 3600.0)
    dia_mm = math.sqrt(4 * area / math.pi) * 1000
    std = min(STANDARD_DUCT_DIA_MM, key=lambda d: (d < dia_mm, abs(d - dia_mm)))
    if std < dia_mm:                      # never undersize the duct
        larger = [d for d in STANDARD_DUCT_DIA_MM if d >= dia_mm]
        std = larger[0] if larger else STANDARD_DUCT_DIA_MM[-1]
    actual_v = airflow_cmh / (3600.0 * math.pi * (std / 2000.0) ** 2)
    return Selection(
        value=f"{std} mm dia, GI, {actual_v:.1f} m/s transport velocity",
        formula=(f"area {area:.2f} m2 = {round(airflow_cmh)} m3/h / ({v:g} m/s x 3600), "
                 f"dia = sqrt(4A/pi) = {dia_mm:.0f} mm -> standard {std} mm"),
        source=SRC_CALC,
        detail={"diameter_mm": std, "velocity_ms": round(actual_v, 1),
                "area_m2": round(area, 2)},
    )


def select_electrical(motor_hp_total: float, lighting_kw: float = 0.0) -> Selection:
    """Panel scope and starter from the connected load — was left blank before."""
    motor_kw = motor_hp_total * HP_TO_KW
    connected = (motor_kw + lighting_kw) * (1 + PANEL_SPARE)
    starter = next(name for limit, name in STARTER_BANDS if motor_kw < limit)
    return Selection(
        value=f"{connected:.1f} kW MCC panel, {starter} starter",
        formula=(f"{motor_hp_total:g} HP x {HP_TO_KW} = {motor_kw:.1f} kW"
                 f"{f' + {lighting_kw:.1f} kW lighting' if lighting_kw else ''}, "
                 f"+{int(PANEL_SPARE * 100)}% spare; starter by load band"),
        source=SRC_CALC,
        detail={"connected_kw": round(connected, 1), "motor_kw": round(motor_kw, 1),
                "starter": starter, "scope": list(PANEL_SCOPE)},
    )


def select_fire_protection(paint_type: Optional[str]) -> Selection:
    """Fire protection inferred from the paint process — was left blank before."""
    p = (paint_type or "").lower()
    key = ("powder" if "powder" in p
           else "water-based" if ("water" in p) else "solvent")
    spec = FIRE_PROTECTION[key]
    return Selection(
        value=", ".join(spec["items"]),
        formula=(f"{key} process -> {spec['standard']}"
                 f"{' (mandatory)' if spec['mandatory'] else ' (recommended)'}"),
        source=SRC_STANDARD,
        detail={"standard": spec["standard"], "items": list(spec["items"]),
                "mandatory": spec["mandatory"]},
    )


def recommend_material(paint_type: Optional[str], environment: Optional[str] = None) -> Selection:
    """Material as an ADVISORY recommendation, never an assertion.

    The client's review was explicit: water-based paint does not by itself
    determine GI. So this returns a recommendation with its reason and states
    that the final material is subject to customer approval.
    """
    p = (paint_type or "").lower()
    key = (environment if environment in MATERIAL_MATRIX
           else "water-based" if "water" in p else "standard")
    m = MATERIAL_MATRIX[key]
    return Selection(
        value=(f"Recommended {m['panels']} panels on {m['structure']} structure "
               f"({m['fasteners']} fasteners) due to {m['reason']}. "
               f"Final material subject to customer approval."),
        formula=f"material matrix: {key} -> structure {m['structure']}, panels {m['panels']}",
        source=SRC_ADVISORY,
        detail=dict(m, environment=key),
    )


def check_historical(reused_value: float, computed_value: float) -> Optional[str]:
    """Flag a reused figure that sits outside +/-20% of the computed one."""
    if not computed_value:
        return None
    dev = (reused_value - computed_value) / computed_value
    if abs(dev) > HISTORICAL_TOLERANCE:
        return (f"historical value differs from the calculated value by "
                f"{dev * 100:+.0f}% - requires review")
    return None
