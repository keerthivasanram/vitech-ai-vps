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
from typing import Any

from .engineering.design_standards import (STATUS_CUSTOMER_READY,
                                           STATUS_CUSTOMER_REVIEW,
                                           STATUS_ENGINEERING_DRAFT)

# An origin every populated value must carry. A value with none is untraceable:
# nobody can tell whether it was calculated, taken from an offer, or guessed.
_UNTRACEABLE = ("", None, "unknown")


def _rows(analysis: dict) -> list[dict]:
    return analysis.get("technical_details") or []


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

    return {
        "status": status,
        "blockers": blockers,
        "gaps": [str(g) for g in gaps],
        "questions": [str(q) for q in questions],
        "summary": _summary(status, blockers, gaps, questions),
    }


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
