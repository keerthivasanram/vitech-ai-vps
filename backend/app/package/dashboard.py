"""Project metadata — the package described in one screen.

Everything here is counted from the resolved analysis. In particular
`completion` is a measure of THIS DOCUMENT SET, not a delivery date: it is the
share of specification fields that are actually resolved. Calling a date
"estimated completion" would be a fabricated number, and manufacturing lead time
is not something the platform has any basis to know.
"""
from typing import Any, Optional


def build(analysis: dict, review: dict, assumptions: dict, xref: dict,
          records: Optional[list] = None, revision: str = "0",
          project: str = "", client: str = "") -> dict[str, Any]:
    rows = analysis.get("technical_details") or []
    counts = assumptions.get("counts") or {}
    resolved = len(rows) - counts.get("engineering_review", 0) - counts.get("customer_confirmation", 0)
    total = len(rows) or 1

    from .traceability import projects_used
    projects = projects_used(records or [])

    return {
        "equipment": analysis.get("category_label") or analysis.get("category"),
        "category": analysis.get("category"),
        "project": project or "(to be completed)",
        "client": client or "(to be completed)",
        "revision": str(revision),
        "confidence_pct": analysis.get("confidence_pct"),
        "confidence_label": analysis.get("confidence_label"),
        "release_status": review.get("release_status"),
        "verdict": review.get("verdict"),
        "historical_projects_used": [
            {"project": p["project"], "drawing": p.get("drawing"),
             "similarity_score": p.get("similarity_score"),
             "fields_taken": len(p.get("fields") or [])}
            for p in projects
        ],
        "engineering_rules_applied": _rules(rows),
        "customer_questions": [f["field"] for f in
                               (assumptions.get("buckets") or {}).get("customer_confirmation", [])],
        "warnings": [f["detail"] for f in (review.get("findings") or [])
                     if f.get("level") in ("FAIL", "WARNING")],
        "item_count": xref.get("item_count", 0),
        "cross_linked_items": xref.get("linked_count", 0),
        "document_coverage": xref.get("coverage") or {},
        # Document completeness, explicitly NOT a delivery date.
        "completion": {
            "resolved_fields": max(resolved, 0),
            "total_fields": len(rows),
            "percent": round(100.0 * max(resolved, 0) / total),
            "basis": ("Share of specification fields resolved. This measures the "
                      "DOCUMENT SET, not manufacturing lead time."),
        },
    }


def _rules(rows: list[dict]) -> list[dict]:
    """The distinct engineering rules and standards this design invoked."""
    seen: dict[str, dict] = {}
    for row in rows or []:
        if str(row.get("origin")) not in ("rule", "standard", "advisory"):
            continue
        ref = str(row.get("source") or "").strip()
        if not ref:
            continue
        entry = seen.setdefault(ref, {"reference": ref, "fields": []})
        entry["fields"].append(row.get("label"))
    return sorted(seen.values(), key=lambda e: e["reference"])


def _coverage(meta: dict) -> str:
    cov = meta.get("document_coverage") or {}
    return (f"{cov.get('drawing', 0)} drawn, {cov.get('bom', 0)} in BOM, "
            f"{cov.get('quotation', 0)} quoted")


def markdown(meta: dict, title: str = "Project Summary") -> str:
    comp = meta.get("completion") or {}
    lines = [f"# {title}", "",
             f"| | |", "| --- | --- |",
             f"| Equipment | {meta.get('equipment')} |",
             f"| Project | {meta.get('project')} |",
             f"| Client | {meta.get('client')} |",
             f"| Revision | {meta.get('revision')} |",
             f"| Confidence | {meta.get('confidence_pct')}% "
             f"({meta.get('confidence_label')}) |",
             f"| Release status | {meta.get('release_status')} |",
             f"| Document completion | {comp.get('percent')}% "
             f"({comp.get('resolved_fields')} of {comp.get('total_fields')} fields) |",
             f"| Engineering items | {meta.get('item_count')} "
             f"({_coverage(meta)}) |", "",
             f"**{meta.get('verdict')}**", ""]

    projects = meta.get("historical_projects_used") or []
    lines += [f"## Historical projects used ({len(projects)})", ""]
    if projects:
        lines += ["| Project | Source document | Match | Fields |",
                  "| --- | --- | --- | --- |"]
        for p in projects:
            score = p.get("similarity_score")
            lines.append(f"| {p['project']} | {p.get('drawing') or '-'} "
                         f"| {f'{score:.3f}' if isinstance(score, (int, float)) else '-'} "
                         f"| {p.get('fields_taken')} |")
    else:
        lines.append("None — this design was produced from rules and the "
                     "customer's own requirement.")
    lines.append("")

    rules = meta.get("engineering_rules_applied") or []
    lines += [f"## Engineering rules applied ({len(rules)})", ""]
    lines += ([f"- **{r['reference']}** — {', '.join(str(f) for f in r['fields'])}"
               for r in rules] if rules else ["None recorded."])
    lines.append("")

    questions = meta.get("customer_questions") or []
    lines += [f"## Customer questions ({len(questions)})", ""]
    lines += ([f"- {q}" for q in questions] if questions else ["None."])
    lines.append("")

    warnings = meta.get("warnings") or []
    lines += [f"## Warnings ({len(warnings)})", ""]
    lines += ([f"- {w}" for w in warnings] if warnings else ["None."])
    lines += ["", f"_{comp.get('basis')}_"]
    return "\n".join(lines)
