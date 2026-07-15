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

def cross_validate(category: str | None, params: dict, chosen, items: list[dict]) -> list[dict]:
    """Catch the class of error where a value REUSED from a historical offer no
    longer fits the new requirement (e.g. a demister sized for a smaller tower,
    or components carried over from a different-airflow design)."""
    checks: list[dict] = []
    if category != "wet_scrubber" or not chosen:
        return checks
    rec = chosen.get("record", {}) if isinstance(chosen, dict) else {}
    tech = rec.get("technical_details", {}) or {}
    gd = rec.get("given_data", {}) or {}

    # 1) reused demister bore vs the (possibly larger) required tower bore
    d_tower = params.get("tower_diameter_mm")
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*dia", str(tech.get("demister", "")))
    if isinstance(d_tower, (int, float)) and m:
        d_dem = float(m.group(1))
        if d_dem < d_tower * 0.9:
            checks.append({"level": "warn", "message": (
                f"Reused mist eliminator ({int(d_dem)} mm dia) is undersized for the "
                f"{int(d_tower)} mm tower bore - resize the demister to match the tower.")})

    # 2) components carried over from a materially different-airflow design
    req = _air_cmh(params)
    off = gd.get("air_volume_cmh") or (gd.get("air_volume_cfm", 0) * _CFM_TO_CMH)
    reused = [it["label"] for it in (items or []) if it.get("origin") in ("reused", "kept")]
    if req and off and abs(req - off) / off > 0.10 and reused:
        checks.append({"level": "info", "message": (
            f"{len(reused)} component(s) were reused from {chosen.get('id')} "
            f"(a {round(off)} m3/h design) for a {round(req)} m3/h duty - confirm "
            f"they still suit the new airflow.")})
    return checks
