"""The review sheet — the first document an engineer should read.

An engineer opening a package needs one question answered before any other: is
there anything here I should not trust? Today that answer is spread across a
confidence score, a validation list, a release status and a column of TBDs — all
present, none of them the first thing anyone sees.

This sheet collects them into one ordered list of findings, worst first, in a
vocabulary that says what to DO:

    FAIL ...... something is contradictory or untraceable. Do not issue.
    WARNING ... engineering is sound but incomplete. Ours to close.
    QUESTION .. the customer must decide. Not an engineering gap.
    PASS ...... a check that ran and was satisfied.

PASS entries are printed, not omitted. A review sheet showing only problems
leaves a reader unable to tell a clean design from an unchecked one — "no
warnings" and "never validated" look identical, and they are not the same thing.

Every finding is derived from checks the engines already ran. This module runs
no engineering of its own.
"""
from typing import Any, Optional

FAIL, WARNING, QUESTION, PASS = "FAIL", "WARNING", "QUESTION", "PASS"

# Worst first: the order the sheet prints, and the order an engineer works.
_ORDER = {FAIL: 0, WARNING: 1, QUESTION: 2, PASS: 3}


def _finding(level: str, check: str, detail: str, item_id: Optional[str] = None) -> dict:
    return {"level": level, "check": check, "detail": detail, "item_id": item_id}


def build(analysis: dict, release: dict, geometry: Optional[dict] = None,
          records: Optional[list] = None, xref: Optional[dict] = None) -> dict[str, Any]:
    """Assemble the review findings from the checks that already ran."""
    findings: list[dict] = []
    rows = analysis.get("technical_details") or []

    # --- cross-validation (the engine's own consistency checks) ------------
    validation = analysis.get("validation") or []
    for check in validation:
        level = WARNING if check.get("level") == "warn" else PASS
        findings.append(_finding(level, "Cross validation",
                                 str(check.get("message") or "")))
    if not validation:
        findings.append(_finding(PASS, "Cross validation",
                                 "No contradictory values found between the "
                                 "requirement, the engineering rules and the "
                                 "reused historical design."))

    # --- dimensions --------------------------------------------------------
    geom = geometry or {}
    env = geom.get("envelope_mm") or {}
    if geom.get("ready"):
        dims = " x ".join(str(env.get(a)) for a in ("length", "width", "height"))
        findings.append(_finding(PASS, "Dimensions validated",
                                 f"Overall envelope resolved as {dims} mm "
                                 f"({geom.get('envelope_source') or 'given'})."))
    else:
        missing = [a for a in ("length", "width", "height") if not env.get(a)]
        findings.append(_finding(WARNING, "Dimensions validated",
                                 "Overall envelope incomplete: "
                                 f"{', '.join(missing) or 'no dimensions'} not determined. "
                                 "The drawing cannot be dimensioned on these axes."))

    # --- historical comparison --------------------------------------------
    projects = _projects(records or [])
    if projects:
        best = projects[0]
        score = best.get("similarity_score")
        findings.append(_finding(
            PASS, "Historical comparison",
            f"Design compared against {len(projects)} historical project(s); "
            f"closest is {best['project']}"
            + (f" (match {score:.3f})" if isinstance(score, (int, float)) else "") + "."))
    elif any(str(r.get("origin")) not in ("given", "tbd", "customer_decision") for r in rows):
        findings.append(_finding(WARNING, "Historical comparison",
                                 "No historical project could be attributed to the "
                                 "reused values in this design."))

    # --- provenance --------------------------------------------------------
    stray = [r.get("label") for r in (records or []) if not r.get("attributed")]
    if stray:
        findings.append(_finding(
            FAIL, "Traceability",
            f"{len(stray)} populated value(s) carry no source and cannot be "
            f"checked: {', '.join(str(s) for s in stray[:5])}."))
    elif records:
        findings.append(_finding(PASS, "Traceability",
                                 f"All {len(records)} populated values carry a "
                                 f"source (customer, rule or project)."))

    # --- the release gate's own findings -----------------------------------
    for blocker in release.get("blockers") or []:
        findings.append(_finding(FAIL, "Release gate", str(blocker)))
    by_label = {str(e.get("label")): e.get("item_id") for e in (xref or {}).get("items") or []}
    for gap in release.get("gaps") or []:
        findings.append(_finding(WARNING, "Engineering gap",
                                 f"{gap} requires engineering confirmation.",
                                 by_label.get(str(gap))))
    for question in release.get("questions") or []:
        findings.append(_finding(QUESTION, "Customer decision",
                                 f"{question} must be confirmed by the customer.",
                                 by_label.get(str(question))))

    findings.sort(key=lambda f: _ORDER.get(f["level"], 9))
    counts = {lvl: sum(1 for f in findings if f["level"] == lvl)
              for lvl in (FAIL, WARNING, QUESTION, PASS)}
    return {
        "findings": findings,
        "counts": counts,
        "release_status": release.get("status"),
        "verdict": _verdict(counts, release),
    }


def _projects(records: list[dict]) -> list[dict]:
    from .traceability import projects_used
    return projects_used(records)


def _verdict(counts: dict, release: dict) -> str:
    """One line stating what happens next."""
    if counts.get(FAIL):
        return (f"NOT FOR ISSUE — {counts[FAIL]} item(s) must be resolved before "
                f"this package goes to a customer.")
    if counts.get(WARNING):
        return (f"ENGINEERING REVIEW REQUIRED — {counts[WARNING]} item(s) are ours "
                f"to close. Status: {release.get('status')}.")
    if counts.get(QUESTION):
        return (f"AWAITING CUSTOMER — nothing outstanding on our side; "
                f"{counts[QUESTION]} item(s) need the customer's decision.")
    return (f"CLEAN — all checks passed. Status: {release.get('status')}. "
            f"Release still requires an engineer's signature.")


def markdown(report: dict, title: str = "Engineering Review Report") -> str:
    """The review sheet. Read this before the specification."""
    counts = report.get("counts") or {}
    lines = [f"# {title}", "",
             "**Read this first.** It states what in this package is trustworthy "
             "and what is not.", "",
             f"**{report.get('verdict')}**", "",
             f"Release status: **{report.get('release_status')}**", "",
             f"| FAIL | WARNING | QUESTION | PASS |", "| --- | --- | --- | --- |",
             f"| {counts.get(FAIL, 0)} | {counts.get(WARNING, 0)} "
             f"| {counts.get(QUESTION, 0)} | {counts.get(PASS, 0)} |", "",
             "## Findings", ""]
    for f in report.get("findings") or []:
        ref = f" [{f['item_id']}]" if f.get("item_id") else ""
        lines += [f"**{f['level']}** — {f['check']}{ref}", "", f"{f['detail']}", ""]
    lines += ["---", "",
              "`Released Design` is never awarded automatically. A human engineer "
              "signs a package off."]
    return "\n".join(lines)
