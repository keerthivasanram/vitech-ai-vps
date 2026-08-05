"""Compose the engineering package from artifacts the existing engines produce.

ONE resolution, many documents. The analysis passed in here is the SAME object
`agent_router.prepare` produced for the specification — the drawing, the BOM, the
quotation, the review and the assumptions are all derived from it. That is what
guarantees the package is internally consistent: there is no second resolution
that could disagree with the first.

A missing artifact never fails the package. A category with no priced history has
no quotation, and a requirement with no dimensions has no dimensioned GA; both
are recorded as absent WITH THE REASON, because a package that silently omits a
document looks complete and is not.
"""
from datetime import date
from typing import Any, Optional

from . import assumptions as assumptions_mod
from . import dashboard as dashboard_mod
from . import identifiers, review as review_mod, traceability

# Each document carries its own revision and confidence, because they do not
# move together: a drawing can be re-issued when nothing in the specification
# changed, and a BOM inherits the spec's confidence but not its revision.
DOCUMENTS = ["requirement_summary", "specification", "drawing", "bom",
             "quotation", "assumptions", "review"]


def _doc(name: str, present: bool, revision: str, confidence=None,
         absent_reason: str = "", **extra) -> dict:
    return {"document": name, "present": present, "revision": str(revision),
            "confidence_pct": confidence, "absent_reason": absent_reason, **extra}


def requirement_summary(analysis: dict, question: str = "") -> dict[str, Any]:
    """What the customer actually asked for, separated from what we engineered.

    First document in the package for the same reason it is first in a real
    offer file: every later disagreement is settled by going back to what was
    requested, so it is recorded verbatim alongside the parsed values.
    """
    given = analysis.get("given_data") or []
    missing = analysis.get("completeness_missing") or analysis.get("missing_inputs") or []
    return {
        "requirement_text": question,
        "equipment": analysis.get("category_label") or analysis.get("category"),
        "stated_values": [{"field": g.get("label"), "value": g.get("value")}
                          for g in given],
        "not_stated": [str(m) for m in missing],
        "completeness_pct": analysis.get("completeness"),
    }


def requirement_markdown(summary: dict) -> str:
    lines = ["# Customer Requirement Summary", "",
             f"**Equipment:** {summary.get('equipment')}", ""]
    if summary.get("requirement_text"):
        lines += ["**As received:**", "", f"> {summary['requirement_text']}", ""]
    stated = summary.get("stated_values") or []
    lines += [f"## Stated by the customer ({len(stated)})", ""]
    if stated:
        lines += ["| Field | Value |", "| --- | --- |"]
        lines += [f"| {s['field']} | {s['value']} |" for s in stated]
    else:
        lines.append("Nothing was stated in structured form.")
    lines.append("")
    missing = summary.get("not_stated") or []
    lines += [f"## Not stated ({len(missing)})", "",
              "These were not supplied with the enquiry. Where the design needed "
              "them they were engineered or reused, and every such value is "
              "listed in the assumption register.", ""]
    lines += ([f"- {m}" for m in missing] if missing else ["None — the requirement was complete."])
    return "\n".join(lines)


def build(analysis: dict, *, question: str = "", hits: Optional[list] = None,
          drawing: Optional[dict] = None, bom: Optional[dict] = None,
          quotation: Optional[dict] = None, geometry: Optional[dict] = None,
          spec_markdown: str = "", revision: str = "0",
          project: str = "", client: str = "", ref: str = "",
          drawn_by: str = "") -> dict[str, Any]:
    """Resolved analysis (+ the artifacts already built from it) -> one package."""
    rows = analysis.get("technical_details") or []
    release = analysis.get("release") or {}

    records = traceability.build(rows, hits)
    register = identifiers.build_register(rows)
    xref = identifiers.cross_reference(register, drawing, bom, quotation)
    assumption_report = assumptions_mod.build(rows, records)
    review_report = review_mod.build(analysis, release, geometry, records, xref)
    summary = requirement_summary(analysis, question)
    meta = dashboard_mod.build(analysis, review_report, assumption_report, xref,
                               records, revision, project, client)

    confidence = analysis.get("confidence_pct")
    manifest = [
        _doc("requirement_summary", True, revision),
        _doc("specification", bool(rows), revision, confidence,
             "" if rows else "The requirement resolved no engineering rows."),
        _doc("drawing", bool((drawing or {}).get("svg")), revision, confidence,
             "" if (drawing or {}).get("svg") else "No drawing was generated for this requirement.",
             dimensioned=bool((drawing or {}).get("ready")),
             views=len((drawing or {}).get("views") or [])),
        _doc("bom", bool((bom or {}).get("lines")), revision, confidence,
             "" if (bom or {}).get("lines") else "No bill of materials could be derived.",
             priced_lines=len([l for l in (bom or {}).get("lines") or []
                               if l.get("amount") is not None]),
             uncosted_lines=len((bom or {}).get("uncosted") or [])),
        _doc("quotation", bool(quotation), revision, confidence,
             "" if quotation else "No priced historical record exists for this equipment, "
                                  "so no budgetary figure could be derived deterministically."),
        _doc("assumptions", True, revision, confidence,
             open_items=assumption_report.get("open_items", 0)),
        _doc("review", True, revision, confidence,
             findings=len(review_report.get("findings") or [])),
    ]

    return {
        "ok": True,
        "generated": f"{date.today():%Y-%m-%d}",
        "ref": ref or f"VT/PKG/{date.today():%y%m%d}/DRAFT",
        "project": project or "(to be completed)",
        "client": client or "(to be completed)",
        "drawn_by": drawn_by or "Vitech AI",
        "revision": str(revision),
        "equipment": analysis.get("category_label") or analysis.get("category"),
        "category": analysis.get("category"),
        # --- the documents ------------------------------------------------
        "requirement_summary": summary,
        "specification": {"rows": rows, "markdown": spec_markdown,
                          "confidence_pct": confidence,
                          "confidence_label": analysis.get("confidence_label")},
        "drawing": drawing or {},
        "bom": bom or {},
        "quotation": quotation or {},
        "assumptions": assumption_report,
        "review": review_report,
        # --- the connective tissue ----------------------------------------
        "traceability": records,
        "cross_reference": xref,
        "dashboard": meta,
        "manifest": manifest,
        "markdown": {
            "requirement": requirement_markdown(summary),
            "assumptions": assumptions_mod.markdown(assumption_report),
            "review": review_mod.markdown(review_report),
            "summary": dashboard_mod.markdown(meta),
            "traceability": traceability.markdown(records),
            "cross_reference": identifiers.markdown(xref),
        },
    }
