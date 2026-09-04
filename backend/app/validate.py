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
from .catalog import origin_label
from .engineering.design_standards import check_historical

TBD_VALUE = "To be determined"          # matches spec_template's own wording

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


def fits_size(required: dict, offer: dict, profile: dict | None = None) -> bool:
    """Is this offer close enough in size for its values to be evidence here?

    Used before BORROWING a field from history, so that field-level retrieval
    cannot quietly reintroduce the very mismatch `demote_unscalable` removes.
    Unknown size compares as acceptable: refusing every offer we cannot measure
    would turn the retrieval off rather than make it careful.
    """
    req, off, _ = _drivers(profile, required or {}, offer or {})
    if not req or not off:
        return True
    return check_historical(off, req) is None


def demote_unscalable(items: list[dict], params: dict, chosen,
                      profile: dict | None = None) -> list[dict]:
    """Refuse to ASSERT a size-dependent value copied across a large size gap.

    Warning about it is not enough. The spec still printed "20 W x 10 LED" as
    the lighting for a booth seven times the size of the one it came from, and a
    reader takes a stated value as engineered. Golden rule #2 applies to reuse
    exactly as it applies to invention: outside the client's +/-20% band the
    value is a different machine's answer, so it is demoted to an honest gap
    with the reason attached.

    Scaling would be better than demoting, but scaling needs a per-field rule
    the client has not supplied. Until then the honest gap is the right answer,
    and the reason tells the engineer precisely what to re-size and from where.
    """
    if not items or not chosen:
        return items
    rec = chosen.get("record", {}) if isinstance(chosen, dict) else {}
    req, off, unit = _drivers(profile, params, rec.get("given_data") or {})
    if not req or not off or not check_historical(off, req):
        return items

    gap = (off - req) / req * 100
    out = []
    for it in items:
        if (it.get("origin") in ("reused", "kept")
                and is_size_dependent(it.get("label"), it.get("value"))):
            it = dict(it)
            it["reason"] = (
                f"{it.get('label')} from {chosen.get('id')} was engineered for a "
                f"{round(off)} {unit} design, {gap:+.0f}% from this "
                f"{round(req)} {unit} duty - re-size rather than reuse.")
            it["value"] = TBD_VALUE
            it["origin"] = "tbd"
            it["origin_label"] = origin_label("tbd")
            it["source"] = None
        out.append(it)
    return out


# --------------------------------------------------------------------------
# CONTRADICTION between a CONFIRMED input and a REUSED value.
#
# `demote_unscalable` refuses a reused value carried across a SIZE gap. This is
# the same argument applied to a value the customer has already CONTRADICTED,
# and it is the sharper case of the two, because the size gap is a judgement
# about similarity while this is a flat disagreement with a stated fact.
#
# The oven that prompted it: the customer specified a 100 mm insulated panel and
# the specification came back reading "175mm blanket 96 kg/m3 + 25mm ceramic
# wool" — 200 mm of insulation, reused from a 230 deg C conveyorised oven,
# correctly attributed, and not this machine. A reader takes a stated value as
# engineered (the exact reasoning behind `demote_unscalable`), so a confidently
# reused contradiction is worse than an admitted gap: the gap is visibly a gap.
#
# It DEMOTES rather than substitutes. The customer gave a panel THICKNESS, not
# an insulation construction, and inventing "100mm blanket" from that would be a
# golden-rule-#2 breach of exactly the kind this platform exists to avoid. The
# thickness stays confirmed on its own row; the construction becomes an honest
# gap whose reason names both numbers and the offer they disagree about.
#
# It fires only where a profile DECLARES the pairing, so it can never guess that
# two unrelated fields are about the same quantity.
# --------------------------------------------------------------------------
_MM_FIGURE = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.I)


def _mm_figures(text: str) -> list[float]:
    return [float(m.group(1)) for m in _MM_FIGURE.finditer(str(text or ""))]


def _agrees_mm(stated: float, text: str, tol: float = 1.0) -> bool:
    """Does the reused text mention the stated thickness at all?

    Either as one figure ("100mm rockwool") or as a build-up that sums to it
    ("50mm + 50mm"), because a layered construction is written both ways. A text
    with NO millimetre figure in it is not a contradiction — it simply does not
    speak about thickness, so it is left alone.
    """
    figures = _mm_figures(text)
    if not figures:
        return True
    if any(abs(f - stated) <= tol for f in figures):
        return True
    return abs(sum(figures) - stated) <= tol


def demote_contradicted(items: list[dict], params: dict,
                        profile: dict | None = None) -> list[dict]:
    """Refuse to ASSERT a reused value the customer's own requirement contradicts."""
    checks = (profile or {}).get("contradiction_checks") or ()
    if not items or not checks or not params:
        return items

    by_label = {str(c.get("label", "")).strip().lower(): c for c in checks}
    out = []
    for it in items:
        check = by_label.get(str(it.get("label", "")).strip().lower())
        stated = params.get(check["input"]) if check else None
        if (check is None or stated in (None, "", [])
                or it.get("origin") not in ("reused", "kept")):
            out.append(it)
            continue
        try:
            stated_v = float(stated)
        except (TypeError, ValueError):
            out.append(it)
            continue
        if _agrees_mm(stated_v, it.get("value")):
            out.append(it)
            continue
        it = dict(it)
        it["reason"] = (
            f"The requirement states {check.get('quantity', 'a value')} of "
            f"{_num(stated_v)} {check.get('unit', '')}".rstrip() +
            f", which {it.get('value')!r} reused from "
            f"{it.get('source') or 'the nearest design'} contradicts. The stated "
            f"figure stands; this field needs engineering input consistent with it "
            f"and is not carried over.")
        it["contradicted"] = {"input": check["input"], "stated": stated,
                              "reused": it.get("value"), "source": it.get("source")}
        it["value"] = TBD_VALUE
        it["origin"] = "tbd"
        it["origin_label"] = origin_label("tbd")
        it["source"] = None
        out.append(it)
    return out


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)
