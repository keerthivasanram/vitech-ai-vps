"""Engineering validation layer.

A sanity-check pass over a requirement (and the values the engine produced),
surfacing engineer-grade observations: is the gas velocity in range, is the
tower sized sensibly, are critical inputs missing. Returns a list of checks
{level: ok|warn|info, message} shown with the specification.

This is what lets a small local model output something an engineer can trust:
the numbers are checked against physics before they're shown.
"""
import math
import re
from typing import Any

# The +/-20% tolerance and its wording are the CLIENT's, so they live with the
# rest of their standards rather than being restated here.
from .engineering.design_standards import check_historical

_CFM_TO_CMH = 1.699

# Wet-scrubber design envelope (ATS practice, consistent with stored offers).
WS_V_MIN = 0.7        # m/s superficial gas velocity - below this, tower oversized
WS_V_MAX = 1.5        # m/s - above this, droplet carry-over risk
WS_V_DESIGN = 1.0     # m/s - used to recommend a diameter


def _air_cmh(params: dict) -> float | None:
    q = params.get("air_volume_cmh")
    if isinstance(q, (int, float)):
        return float(q)
    cfm = params.get("air_volume_cfm")
    return float(cfm) * _CFM_TO_CMH if isinstance(cfm, (int, float)) else None


def _recommended_diameter_mm(q_cmh: float, v: float = WS_V_DESIGN) -> int:
    area = (q_cmh / 3600.0) / v                       # m2
    return int(round(math.sqrt(4 * area / math.pi) * 1000))


def _validate_wet_scrubber(params: dict[str, Any]) -> list[dict]:
    checks: list[dict] = []
    q_cmh = _air_cmh(params)
    d_mm = params.get("tower_diameter_mm")

    if q_cmh and isinstance(d_mm, (int, float)) and d_mm > 0:
        area = math.pi / 4 * (d_mm / 1000.0) ** 2
        v = (q_cmh / 3600.0) / area
        rec = _recommended_diameter_mm(q_cmh)
        if v < WS_V_MIN:
            checks.append({"level": "warn", "message": (
                f"Gas velocity is only {v:.2f} m/s - below the typical "
                f"{WS_V_MIN}-{WS_V_MAX} m/s. The {d_mm:g} mm tower is oversized for "
                f"{round(q_cmh)} m3/h; about {rec} mm would suffice (lower cost).")})
        elif v > WS_V_MAX:
            checks.append({"level": "warn", "message": (
                f"Gas velocity is {v:.2f} m/s - above ~{WS_V_MAX} m/s, so droplet "
                f"carry-over is likely. Consider a larger tower (about {rec} mm) or "
                f"a higher-efficiency demister.")})
        else:
            checks.append({"level": "ok", "message": (
                f"Gas velocity {v:.2f} m/s is within the design range "
                f"({WS_V_MIN}-{WS_V_MAX} m/s) for the {d_mm:g} mm tower.")})

    if not params.get("operating_temp"):
        checks.append({"level": "info", "message": (
            "Operating temperature not given - ambient assumed. A hot gas stream "
            "would need pre-cooling and a material/finish review.")})
    if not params.get("operating_pressure"):
        checks.append({"level": "info", "message": (
            "Operating pressure / available draft not given - confirm the blower "
            "static pressure against the scrubber pressure drop.")})
    return checks


def validate(category: str | None, params: dict[str, Any]) -> list[dict]:
    if category == "wet_scrubber":
        return _validate_wet_scrubber(params)
    return []


# --- cross-validation: computed requirement vs SELECTED historical component ---

# Equipment whose sizing follows the machine's size. Naming the component is not
# enough on its own — see the two filters below it.
SIZE_DEPENDENT = (
    "illumination", "lighting", "luminaire", "lux",
    "filter", "blower", "fan", "motor", "pump", "nozzle", "heater",
    "duct", "airflow", "air volume", "capacity", "scrubber", "demister",
    "weight", "surface area", "heat load", "chamber", "tank",
)

# A DESCRIPTOR of a component, not a sizing of it. "Blower MOC = MS" and
# "Spray nozzle material = SS316" name the same components as above, but a
# material travels between machine sizes perfectly well.
_DESCRIPTOR = ("moc", "material", "type", "finish", "make", "brand", "grade",
               "construction", "drive", "colour", "color")

# Units that mean a value SCALES. Deliberately excludes grades and ratings that
# merely contain a number: "10 micron velcro type" is a filter grade, and a
# 100 m2 booth uses the same grade as a 14 m2 one.
_SCALING_UNIT = ("nos", "no's", " no", "set", "mm", "cm", " m ", "m2", "m3",
                 "sq", "cfm", "cmh", "hp", "kw", "kg", "lux", "lumen", "dia",
                 "litre", "liter", "ltr", "watt")


def is_size_dependent(label: str, value: Any = None) -> bool:
    """True when a value cannot simply be carried to a different-sized machine.

    Needs BOTH a component whose sizing follows the machine AND an actual
    quantity in the label or value. Without the second test the check fired on
    "Blower MOC = MS" and "Air intake filter = 10 micron velcro type", which are
    descriptors — and a warning an engineer knows is wrong is worse than none.
    """
    low = str(label or "").lower()
    if not any(k in low for k in SIZE_DEPENDENT):
        return False
    if any(d in low for d in _DESCRIPTOR):
        return False
    text = f" {low} {str(value or '').lower()} "
    if not re.search(r"\d", text):
        return False
    return any(u in text for u in _SCALING_UNIT)


# How each sizing driver reads in a sentence ("a 6100 CFM design"), rather than
# the raw parameter key ("a 6100 air volume cfm design").
_DRIVER_UNITS = {
    "air_volume_cfm": "CFM",
    "air_volume_cmh": "m3/h",
    "tower_diameter_mm": "mm bore",
    "track_length_m": "m",
}


def _positive(values: dict, key: str) -> float | None:
    v = (values or {}).get(key)
    return float(v) if isinstance(v, (int, float)) and v > 0 else None


def _floor_area(values: dict) -> float | None:
    L, W = _positive(values, "length_m"), _positive(values, "width_m")
    return L * W if L and W else None


def _drivers(profile: dict | None, required: dict,
             offer: dict) -> tuple[float | None, float | None, str]:
    """Comparable 'how big is this machine' numbers for BOTH sides, one unit.

    The two sides MUST be measured the same way. The requirement carries CFM
    while an offer may record only m3/h, and comparing 6100 m3/h against
    3000 CFM as though they were the same unit reported a 103% size gap where
    the true gap is 20% — a warning wrong enough to discredit the whole check.
    So a basis is used only when BOTH sides have it.
    """
    driver = (profile or {}).get("scale_driver")
    if driver:
        a, b = _positive(required, driver), _positive(offer, driver)
        if a and b:
            return a, b, _DRIVER_UNITS.get(driver, driver.replace("_", " "))
    a, b = _air_cmh(required), _air_cmh(offer)      # normalises cfm -> m3/h
    if a and b:
        return a, b, "m3/h"
    a, b = _floor_area(required), _floor_area(offer)
    if a and b:
        return a, b, "m2 floor area"
    return None, None, ""


def cross_validate(category: str | None, params: dict, chosen, items: list[dict],
                   profile: dict | None = None) -> list[dict]:
    """Catch the class of error where a value REUSED from a historical offer no
    longer fits the new requirement (e.g. a demister sized for a smaller tower,
    or components carried over from a different-airflow design).

    Runs for EVERY category, not just wet scrubbers: reuse across a size gap is
    a platform-wide failure mode, and the reviewer found it on a paint booth.
    """
    checks: list[dict] = []
    if not chosen:
        return checks
    rec = chosen.get("record", {}) if isinstance(chosen, dict) else {}
    tech = rec.get("technical_details", {}) or {}
    gd = rec.get("given_data", {}) or {}

    # 1) reused demister bore vs the (possibly larger) required tower bore
    if category == "wet_scrubber":
        d_tower = params.get("tower_diameter_mm")
        m = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*dia", str(tech.get("demister", "")))
        if isinstance(d_tower, (int, float)) and m:
            d_dem = float(m.group(1))
            if d_dem < d_tower * 0.9:
                checks.append({"level": "warn", "message": (
                    f"Reused mist eliminator ({int(d_dem)} mm dia) is undersized for the "
                    f"{int(d_tower)} mm tower bore - resize the demister to match the tower.")})

    # 2) SIZE GAP. The client's own +/-20% tolerance decides when a reused value
    #    stops being evidence and starts being a different machine's answer.
    reused = [it["label"] for it in (items or []) if it.get("origin") in ("reused", "kept")]
    sized = [it["label"] for it in (items or [])
             if it.get("origin") in ("reused", "kept")
             and is_size_dependent(it.get("label"), it.get("value"))]
    req, off, unit = _drivers(profile, params, gd)
    if req and off and reused:
        note = check_historical(off, req)
        if note and sized:
            checks.append({"level": "warn", "message": (
                f"{len(sized)} size-dependent value(s) were reused from {chosen.get('id')}, "
                f"a {round(off)} {unit} design, for a {round(req)} {unit} duty - the "
                f"{note.split(' - ')[0]}. Re-size before release: "
                f"{', '.join(sized[:6])}{'...' if len(sized) > 6 else ''}.")})
        elif abs(req - off) / off > 0.10:
            checks.append({"level": "info", "message": (
                f"{len(reused)} component(s) were reused from {chosen.get('id')} "
                f"(a {round(off)} {unit} design) for a {round(req)} {unit} duty - confirm "
                f"they still suit the new duty.")})
    return checks
