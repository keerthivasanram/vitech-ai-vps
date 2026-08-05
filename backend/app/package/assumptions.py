"""What was assumed, stated apart from what was engineered.

WHY THIS IS A SEPARATE DOCUMENT. A specification is a statement of what the
equipment IS. The moment a caveat is printed beside a row — "reused from a
smaller booth", "awaiting customer confirmation" — the reader has to decide,
line by line, which numbers are load-bearing. Worse, a caveat folded into the
spec tends to be read as part of the design and quoted back as though it were.

So the specification keeps saying what the machine is, and this document says
what that statement rests on. The two are generated from the SAME resolved rows,
so they cannot disagree: a value is in exactly one bucket here, decided by the
origin the resolver already recorded.

The buckets are the client's own review vocabulary:

    customer_supplied ....... they told us
    engineering_calculated .. a rule or standard produced it
    historical_reused ....... a past project produced it
    customer_confirmation ... theirs to decide, and still open
    engineering_review ...... ours to finish, and still open
"""
from .. import values
from typing import Any

_clip = values.clip          # shared table-cell reader (app/values.py)

from .traceability import CALCULATED, CUSTOMER, HISTORICAL

TBD_VALUES = values.TBD_VALUES

BUCKETS = [
    ("customer_supplied", "Customer supplied values",
     "Stated by the customer. Authoritative — the design is built to these."),
    ("engineering_calculated", "Engineering calculated values",
     "Produced by an engineering rule or standard. Check the calculation reference."),
    ("historical_reused", "Historical reused values",
     "Taken from a comparable past project. Check the source and the size match."),
    ("customer_confirmation", "Fields requiring customer confirmation",
     "Open questions for the customer. NOT engineering gaps."),
    ("engineering_review", "Fields requiring engineering review",
     "Open on our side. These must be closed before the package is released."),
]


def _bucket_for(row: dict) -> str:
    origin = str(row.get("origin") or "")
    value = str(row.get("value") or "").strip().lower()
    if origin == "customer_decision" or value == "to be confirmed with the customer":
        return "customer_confirmation"
    if origin == "tbd" or value in TBD_VALUES or not value:
        return "engineering_review"
    if origin in CUSTOMER:
        return "customer_supplied"
    if origin in CALCULATED:
        return "engineering_calculated"
    if origin in HISTORICAL:
        return "historical_reused"
    # An origin nobody recognises is a traceability failure, not a calculated
    # value: it goes where it will be looked at rather than being assumed sound.
    return "engineering_review"


def build(rows: list[dict], records: list[dict] | None = None) -> dict[str, Any]:
    """Group the resolved rows into the assumption buckets.

    `records` are the traceability records, used only to attach a source to a
    reused value — never to change which bucket a value falls in.
    """
    by_label = {str(r.get("label")): r for r in (records or [])}
    grouped: dict[str, list] = {key: [] for key, _, _ in BUCKETS}
    for row in rows or []:
        trace = by_label.get(str(row.get("label")), {})
        grouped[_bucket_for(row)].append({
            "field": row.get("label"),
            "value": str(row.get("value") or ""),
            "origin": row.get("origin"),
            "reason": row.get("reason"),
            "source_project": trace.get("source_project"),
            "source_drawing": trace.get("source_drawing"),
            "similarity_score": trace.get("similarity_score"),
            "calculation_reference": trace.get("calculation_reference"),
        })
    return {
        "buckets": grouped,
        "counts": {key: len(grouped[key]) for key, _, _ in BUCKETS},
        "open_items": len(grouped["customer_confirmation"]) + len(grouped["engineering_review"]),
    }


def markdown(report: dict, title: str = "Engineering Assumptions") -> str:
    """The assumption register, one section per bucket."""
    grouped = report.get("buckets") or {}
    lines = [f"# {title}", "",
             "This document states what the specification RESTS ON. It is issued "
             "alongside the specification and deliberately kept out of it: the "
             "specification says what the equipment is, this says what that "
             "statement depends on.", ""]
    for key, heading, blurb in BUCKETS:
        entries = grouped.get(key) or []
        lines += [f"## {heading} ({len(entries)})", "", f"_{blurb}_", ""]
        if not entries:
            lines += ["None.", ""]
            continue
        if key in ("customer_confirmation", "engineering_review"):
            lines += ["| Field | Why it is open |", "| --- | --- |"]
            for e in entries:
                lines.append(f"| {e['field']} | {_clip(e.get('reason') or 'Needs input.', 90)} |")
        elif key == "historical_reused":
            lines += ["| Field | Value | Source project | Source document | Match |",
                      "| --- | --- | --- | --- | --- |"]
            for e in entries:
                score = e.get("similarity_score")
                lines.append(
                    f"| {e['field']} | {_clip(e['value'], 90)} | {e.get('source_project') or '-'} "
                    f"| {e.get('source_drawing') or '-'} "
                    f"| {f'{score:.3f}' if isinstance(score, (int, float)) else '-'} |")
        elif key == "engineering_calculated":
            lines += ["| Field | Value | Calculation reference |", "| --- | --- | --- |"]
            for e in entries:
                lines.append(f"| {e['field']} | {_clip(e['value'], 90)} "
                             f"| {_clip(e.get('calculation_reference') or e.get('reason'), 90)} |")
        else:
            lines += ["| Field | Value |", "| --- | --- |"]
            for e in entries:
                lines.append(f"| {e['field']} | {_clip(e['value'], 90)} |")
        lines.append("")
    return "\n".join(lines)
