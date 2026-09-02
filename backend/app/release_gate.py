"""Is this specification fit to send a customer, and if not, what is missing?

Confidence already says how well-founded the numbers are. It does NOT say
whether the document may leave the building — a 94%-confident spec that
contradicts itself, or that reuses a lighting layout from a seven-times-smaller
booth, is still an internal draft. The client's engineering review made exactly
that distinction ("a good engineering draft, NOT ready for customer release"),
so it is stated explicitly rather than left for a reader to infer from a score.

The ladder and the criteria are the CLIENT's:

  Engineering Draft ..... something contradicts, or a value has no provenance
  Customer Review Draft . engineering is sound but gaps remain for us to close
  Customer Ready ........ nothing outstanding except what the CUSTOMER must decide
  Released Design ....... never automatic; a human signs this off

`Released Design` is deliberately unreachable from code. Release is an
engineer's signature, and a program that could award it to itself would defeat
the human-in-the-loop rule the whole platform is built on.
"""
import re
from typing import Any, Optional

from .engineering import voc_service as voc
from .engineering.design_standards import (STATUS_CUSTOMER_READY,
                                           STATUS_CUSTOMER_REVIEW,
                                           STATUS_ENGINEERING_DRAFT)

# An origin every populated value must carry. A value with none is untraceable:
# nobody can tell whether it was calculated, taken from an offer, or guessed.
_UNTRACEABLE = ("", None, "unknown")


def _rows(analysis: dict) -> list[dict]:
    return analysis.get("technical_details") or []


def _row_value(rows: list[dict], label: str) -> Optional[str]:
    for row in rows:
        if str(row.get("label", "")).strip().lower() == label.lower():
            return row.get("value")
    return None


def _number(text: Any) -> Optional[float]:
    match = re.search(r"[-+]?\d*\.?\d+", str(text or "").replace(",", ""))
    return float(match.group()) if match else None


# The client's VOC workbook inputs, named as `/api/tools/voc` names them.
_VOC_INPUTS = (("paint_consumption_l_hr", "paint consumption (l/hr)"),
               ("voc_percent", "VOC content (%)"),
               ("density_kg_l", "paint density (kg/l)"))


def _voc_safety(rows: list[dict], params: dict) -> dict[str, Any]:
    """The client's VOC/LEL check, as a release verdict rather than a spec row.

    Solvent concentration is the one quantity here that is a SAFETY question:
    the extracted air is either below the client's 1000 mg/m3 design limit or it
    is not. `voc_service` has been able to answer it since the workbooks landed
    and nothing asked it, so an over-limit design could reach `Customer Ready`
    with nothing to show it was never checked.

    A FAIL is a BLOCKER, because no amount of customer sign-off makes an
    over-limit extraction safe. Missing inputs are a QUESTION rather than a gap:
    paint consumption and VOC content are the customer's own process figures,
    not engineering we can finish for them — but they are stated on the document
    either way, so "not checked" can never be mistaken for "checked and passed".

    A POWDER booth is skipped entirely. There is no solvent to evaporate, and a
    safety warning an engineer knows is inapplicable is worse than none.
    """
    process = str(_row_value(rows, "Paint process") or "").lower()
    if not process or "powder" in process:
        return {}

    airflow = _number(_row_value(rows, "Exhaust airflow"))
    missing = [label for key, label in _VOC_INPUTS if params.get(key) is None]

    result = voc.assess_voc(params.get("paint_consumption_l_hr"),
                            params.get("voc_percent"),
                            params.get("density_kg_l"),
                            airflow)
    if result.verdict == voc.FAIL:
        return {"verdict": voc.FAIL,
                "blocker": f"VOC safety: {result.reason}.",
                "reason": result.reason,
                "concentration_mg_m3": round(result.concentration_mg_m3),
                "limit_mg_m3": result.limit_mg_m3,
                "required_airflow_cmh": (round(result.required_airflow_cmh)
                                         if result.required_airflow_cmh else None)}
    if result.verdict == voc.PASS:
        return {"verdict": voc.PASS, "reason": result.reason,
                "concentration_mg_m3": round(result.concentration_mg_m3),
                "limit_mg_m3": result.limit_mg_m3}
    return {"verdict": None, "reason": result.reason,
            "question": ("Solvent VOC safety not verified — confirm "
                         + ", ".join(missing) + " to check the extracted air "
                         "against the 1000 mg/m3 design limit.")}


def assess(analysis: dict) -> dict[str, Any]:
    """Release status for a resolved specification, with the reasons behind it.

    Returns {status, blockers, gaps, questions, checks} — `blockers` are what
    keep it an internal draft, `gaps` are our engineering to finish, and
    `questions` are the customer's to answer.
    """
    rows = _rows(analysis)
    validation = analysis.get("validation") or []

    # --- what stops it being an engineering draft --------------------------
    blockers: list[str] = []
    for check in validation:
        if check.get("level") == "warn":
            blockers.append(str(check.get("message")))

    untraceable = [r.get("label") for r in rows
                   if str(r.get("value", "")).strip()
                   and str(r.get("value", "")).strip().lower() != "to be determined"
                   and (r.get("origin") in _UNTRACEABLE)]
    if untraceable:
        blockers.append(
            f"{len(untraceable)} value(s) carry no source: "
            f"{', '.join(str(u) for u in untraceable[:5])}.")

    # --- our engineering still to finish -----------------------------------
    gaps = [r.get("label") for r in rows if r.get("origin") == "tbd"]

    # --- the customer's decisions, which are not our gaps ------------------
    questions = [r.get("label") for r in rows if r.get("origin") == "customer_decision"]

    # --- safety, which outranks both -----------------------------------
    safety = _voc_safety(rows, analysis.get("parameters") or {})
    if safety.get("blocker"):
        blockers.append(safety["blocker"])
    elif safety.get("question"):
        questions.append(safety["question"])

    # A spec with no engineered rows at all has not been produced yet; calling
    # that "customer ready" because nothing failed would be absurd.
    if not rows:
        status = STATUS_ENGINEERING_DRAFT
    elif blockers:
        status = STATUS_ENGINEERING_DRAFT
    elif gaps:
        status = STATUS_CUSTOMER_REVIEW
    else:
        status = STATUS_CUSTOMER_READY

    out = {
        "status": status,
        "blockers": blockers,
        "gaps": [str(g) for g in gaps],
        "questions": [str(q) for q in questions],
        "summary": _summary(status, blockers, gaps, questions),
    }
    # Reported even when it PASSES: a sheet that shows only problems makes
    # "no VOC issue" and "VOC never checked" look identical.
    if safety:
        out["safety"] = safety
    return out


def _summary(status: str, blockers: list, gaps: list, questions: list) -> str:
    """One line an engineer can act on, not a score."""
    if blockers:
        return (f"{status}: {len(blockers)} issue(s) must be resolved before this "
                f"goes to a customer.")
    if gaps:
        return (f"{status}: engineering is consistent, but {len(gaps)} field(s) "
                f"still need input from us.")
    if questions:
        return (f"{status}: nothing outstanding on our side; {len(questions)} "
                f"item(s) await the customer's decision.")
    return f"{status}: complete and self-consistent. Release requires engineer sign-off."
