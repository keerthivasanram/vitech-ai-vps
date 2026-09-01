"""Where every number came from, in the form an engineer can check it.

The resolver already records an origin, a source and a reason per value — that
is what makes the specification auditable at all. What it does NOT do is join
those to the retrieval that produced them, so "reused from OFF-CRI-PB-082406R4"
never said which DOCUMENT that offer is, or how close a match it actually was.
A reviewer cannot judge a reused value without both.

This module joins the resolved rows to the retrieval hits that produced them:

    source project ...... the offer id the value was taken from
    source drawing ...... the original document that offer was extracted from
    similarity score .... how close that offer was to THIS requirement
    reason .............. why the engine chose it
    calculation ref ..... for a calculated value, the rule/standard behind it

Nothing is inferred. A field the engine could not attribute is reported as
unattributed, which is exactly the signal a reviewer needs.
"""
from .. import values
from typing import Any, Optional

_clip = values.clip          # shared table-cell reader (app/values.py)

# Origins that mean "this number came from a past project" rather than from a
# rule or from the customer. Kept explicit because the legacy tags are still
# emitted by older code paths and a missed one would silently lose traceability.
HISTORICAL = {"reused", "kept", "existing", "scaled", "adapted", "consistent",
              "interpolated"}
CALCULATED = {"rule", "standard", "advisory"}
CUSTOMER = {"given"}


def _index_hits(hits: Optional[list]) -> dict[str, dict]:
    """offer id -> {source_file, score, title}, from the retrieval that ran."""
    index: dict[str, dict] = {}
    for hit in hits or []:
        record = hit.get("record") or {}
        key = hit.get("id") or record.get("id")
        if not key:
            continue
        index[str(key)] = {
            "source_file": record.get("source_file"),
            "score": hit.get("score"),
            "title": hit.get("title"),
        }
    return index


def build(rows: list[dict], hits: Optional[list] = None) -> list[dict]:
    """One traceability record per populated specification value."""
    index = _index_hits(hits)
    out: list[dict] = []
    for row in rows or []:
        value = str(row.get("value") or "").strip()
        if not value or value.lower() in ("to be determined",
                                          "to be confirmed with the customer"):
            continue                      # an admitted gap has nothing to trace
        origin = str(row.get("origin") or "")
        source = row.get("source")
        entry: dict[str, Any] = {
            "label": row.get("label"),
            "value": value,
            "origin": origin,
            "reason": row.get("reason"),
            "source_project": None,
            "source_drawing": None,
            "similarity_score": None,
            "calculation_reference": None,
            "attributed": False,
        }
        if origin in HISTORICAL and source:
            found = index.get(str(source)) or {}
            entry.update({
                "source_project": str(source),
                # The offer's own source document — the drawing/offer PDF an
                # engineer would open to check the value by hand.
                "source_drawing": found.get("source_file"),
                "similarity_score": found.get("score"),
                "attributed": True,
            })
        elif origin in CALCULATED:
            # For a calculated value the "source" IS the governing rule or
            # standard the calculation engine cited.
            entry.update({"calculation_reference": source or None,
                          "attributed": bool(source)})
        elif origin in CUSTOMER:
            entry.update({"source_project": "Customer requirement",
                          "attributed": True})
        out.append(entry)
    return out


def unattributed(records: list[dict]) -> list[dict]:
    """Populated values carrying no usable provenance — a release blocker."""
    return [r for r in records if not r.get("attributed")]


def projects_used(records: list[dict]) -> list[dict]:
    """The distinct historical projects this package leans on, best match first.

    This is what a reviewer wants when asking "what is this design based on?" —
    a short list of real projects, not a per-field trail.
    """
    seen: dict[str, dict] = {}
    for r in records:
        pid = r.get("source_project")
        if not pid or pid == "Customer requirement":
            continue
        entry = seen.setdefault(pid, {"project": pid,
                                      "drawing": r.get("source_drawing"),
                                      "similarity_score": r.get("similarity_score"),
                                      "fields": []})
        entry["fields"].append(r.get("label"))
    return sorted(seen.values(),
                  key=lambda e: (-(e.get("similarity_score") or 0), e["project"]))


def markdown(records: list[dict]) -> str:
    """The traceability schedule."""
    lines = ["## Traceability", "",
             "Every populated value, and what it can be checked against.", "",
             "| Field | Value | Origin | Source project | Source document | Match | Reference |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in records:
        score = r.get("similarity_score")
        lines.append(
            f"| {r.get('label')} | {_clip(r.get('value'), 60)} | {r.get('origin')} "
            f"| {r.get('source_project') or '-'} | {r.get('source_drawing') or '-'} "
            f"| {f'{score:.3f}' if isinstance(score, (int, float)) else '-'} "
            f"| {_clip(r.get('calculation_reference'), 60) or '-'} |")
    missing = unattributed(records)
    if missing:
        lines += ["", f"**{len(missing)} value(s) carry no provenance** — "
                      "these must be attributed before release:"]
        lines += [f"- {m.get('label')}" for m in missing]
    return "\n".join(lines)
