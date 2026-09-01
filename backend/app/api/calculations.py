"""Calculation tools: the VOC safety gate and the oven / tank heat load.

These expose the services transcribed from the client's own calculation
workbooks (`app/engineering/voc_service.py`, `heat_load_service.py`) as agent
tools. Two rules shape them, both learned the hard way elsewhere in this
codebase:

  * **A missing input is a QUESTION, never a default.** Every endpoint that
    cannot compute returns `need_inputs` with the list of what is missing and an
    instruction to ASK. The alternative — letting an 8B model supply a paint
    consumption or a job mass so the tool "works" — is exactly the vacuum-filling
    that produced the hot-air-oven hallucination.
  * **The reply is rendered in CODE and printed verbatim.** Each response carries
    a `*_markdown` block, the same structural fix that made `lookup_markdown` and
    `quotation_markdown` reliable. The model narrates around it; it never
    reformats a number.
"""
import re

from fastapi import APIRouter, Body

from ..engineering import heat_load_service as hl
from ..engineering import voc_service as voc
from ..observability import jobs as _jobs, trace as _obs
from .support import _tool_q

router = APIRouter()

# Labelled-number extraction. Deliberately conservative: a number is only read
# when its OWN unit or keyword is present, so a stray figure in prose cannot be
# mistaken for a design input.
_PATTERNS = {
    "paint_consumption_l_hr": r"(\d+(?:\.\d+)?)\s*(?:l|lit|litre|liter)s?\s*(?:/|per\s*)\s*(?:hr|hour)",
    "voc_percent": r"(\d+(?:\.\d+)?)\s*%\s*(?:voc|solvent)|voc\D{0,12}?(\d+(?:\.\d+)?)\s*%",
    "density_kg_l": r"(\d+(?:\.\d+)?)\s*kg\s*(?:/|per\s*)\s*(?:l|lit|litre|liter)",
    "airflow_cmh": r"(\d+(?:\.\d+)?)\s*(?:cmh|m3/h|m3/hr|m³/h)",
}


def _from_text(q: str) -> dict:
    out: dict[str, float] = {}
    t = (q or "").lower().replace(",", "")
    for key, pat in _PATTERNS.items():
        m = re.search(pat, t)
        if m:
            val = next((g for g in m.groups() if g), None)
            if val is not None:
                out[key] = float(val)
    return out


def _num(payload: dict, key: str, parsed: dict):
    v = payload.get(key, parsed.get(key))
    try:
        return float(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _ask(missing: list[str], what: str) -> dict:
    return {"ok": False, "need_inputs": True, "missing": missing,
            "message": (f"Cannot {what} yet. ASK the user for: {', '.join(missing)}. "
                        "Do NOT assume, estimate or supply any of these values yourself.")}


@router.post("/api/tools/voc", operation_id="check_voc_safety")
def tool_voc(payload: dict = Body(...)):
    """Paint consumption + airflow -> solvent concentration and a PASS/FAIL gate."""
    q = _tool_q(payload)
    parsed = _from_text(q)
    args = {k: _num(payload, k, parsed) for k in _PATTERNS}
    missing = [k.replace("_", " ") for k, v in args.items() if v is None]
    if missing:
        return _ask(missing, "check the VOC concentration")

    _obs.note(tool="check_voc_safety", agent="Engineering")
    job = _jobs.create("voc_check", requirement=q)
    r = voc.assess_voc(args["paint_consumption_l_hr"], args["voc_percent"],
                       args["density_kg_l"], args["airflow_cmh"])
    verdict = "PASS" if r.verdict == voc.PASS else "FAIL"
    lines = [
        "**VOC / LEL SAFETY CHECK**", "",
        f"Verdict: **{verdict}** — {r.reason}", "",
        "| Quantity | Value | Basis |",
        "| --- | --- | --- |",
        f"| Solvent mass rate | {r.voc_kg_hr:.2f} kg/hr | "
        f"{args['paint_consumption_l_hr']:g} l/hr x {args['density_kg_l']:g} kg/l "
        f"x {args['voc_percent']:g}% |",
        f"| Concentration in extracted air | {round(r.concentration_mg_m3)} mg/m3 | "
        f"into {args['airflow_cmh']:g} m3/h |",
        f"| Design limit | {r.limit_mg_m3:g} mg/m3 | Vitech paint-shop VOC calculation |",
    ]
    if r.required_airflow_cmh:
        lines.append(f"| Airflow required to pass | {round(r.required_airflow_cmh)} m3/h | "
                     f"at this paint consumption |")
    lines += ["", "This is a design check, not a certificate. Confirm the solvent's own "
                  "LEL and the local statutory limit before issue."]
    _jobs.finish(job, equipment="paint_booth",
                 summary={"verdict": verdict, "mg_m3": round(r.concentration_mg_m3)})
    return {"ok": True, "verdict": verdict, "reason": r.reason,
            "concentration_mg_m3": round(r.concentration_mg_m3, 1),
            "voc_kg_hr": round(r.voc_kg_hr, 3),
            "limit_mg_m3": r.limit_mg_m3,
            "required_airflow_cmh": (round(r.required_airflow_cmh)
                                     if r.required_airflow_cmh else None),
            "voc_markdown": "\n".join(lines)}


_UNITS = {"tank": ("tank", "mm"), "dry_off_oven": ("dry-off oven", "m"),
          "curing_oven": ("curing oven", "m")}


def _equipment(q: str, payload: dict) -> str:
    t = (payload.get("equipment") or q or "").lower()
    if "tank" in t:
        return "tank"
    if "cure" in t or "curing" in t or "bake" in t:
        return "curing_oven"
    if "dry" in t:
        return "dry_off_oven"
    return ""


@router.post("/api/tools/heat-load", operation_id="calculate_heat_load")
def tool_heat_load(payload: dict = Body(...)):
    """Tank / dry-off oven / curing oven -> heat load in kW, from the client's sheets."""
    q = _tool_q(payload)
    kind = _equipment(q, payload)
    if not kind:
        return _ask(["which unit: a process tank, a dry-off oven or a curing oven"],
                    "calculate a heat load")

    dims = {k: _num(payload, k, {}) for k in ("length", "width", "height")}
    temps = {k: _num(payload, k, {}) for k in ("temp_from_c", "temp_to_c")}
    missing = [k for k, v in {**dims, **temps}.items() if v is None]
    if missing:
        return _ask([m.replace("_", " ") for m in missing],
                    f"calculate the {_UNITS[kind][0]} heat load")

    _obs.note(tool="calculate_heat_load", agent="Engineering")
    job = _jobs.create("heat_load", requirement=q)
    if kind == "tank":
        r = hl.tank_heat_load(dims["length"], dims["width"], dims["height"],
                              temps["temp_from_c"], temps["temp_to_c"],
                              _num(payload, "tank_steel_mass_kg", {}) or 0.0)
    elif kind == "dry_off_oven":
        r = hl.dry_off_oven_heat_load(
            dims["length"], dims["width"], dims["height"],
            temps["temp_from_c"], temps["temp_to_c"],
            _num(payload, "sheet_thickness_mm", {}) or 1.2,
            job_mass_kg=_num(payload, "job_mass_kg", {}),
            jobs_per_hour=_num(payload, "jobs_per_hour", {}))
    else:
        thk = _num(payload, "insulation_thickness_mm", {})
        r = hl.curing_oven_heat_load(
            dims["length"], dims["width"], dims["height"],
            temps["temp_from_c"], temps["temp_to_c"],
            _num(payload, "sheet_thickness_mm", {}) or 1.2,
            conveyor_mass_kg=_num(payload, "conveyor_mass_kg", {}),
            job_mass_kg=_num(payload, "job_mass_kg", {}),
            insulation_thickness_mm=int(thk) if thk else None)

    label = _UNITS[kind][0].title()
    lines = [f"**HEAT LOAD — {label.upper()}**", "",
             f"Heat load: **{r.kw} kW**  ({round(r.kcal):,} Kcal)", "",
             "| Step | Value | Basis |", "| --- | --- | --- |"]
    for name, value, formula, _std in r.trail:
        lines.append(f"| {name} | {value} | {formula} |")
    if r.gaps:
        lines += ["", "**Not included — confirm before sizing the heater:**"]
        lines += [f"- {g}" for g in r.gaps]
    lines += ["", "Calculated from Vitech's own heat-load sheet (1 kW = 860 Kcal). "
                  "Heater selection must add the process margin and the burner turndown."]
    _jobs.finish(job, equipment=kind, summary={"kw": r.kw})
    return {"ok": True, "equipment": kind, "kw": r.kw, "kcal": round(r.kcal),
            "gaps": list(r.gaps), "heat_load_markdown": "\n".join(lines)}
