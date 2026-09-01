"""One identifier per engineering item, and the cross-reference that resolves it.

THE PROBLEM. Each document numbers things for its own convenience: the drawing
allocates balloons in the order it draws them, the BOM groups by section, the
quotation lists by commercial scope. So "item 3" means three different things
depending on which sheet you are holding, and nothing says that balloon 5, the
"Exhaust blower" BOM line and quotation item 2 are one and the same fan.

THE APPROACH. The specification is the engineering model every other document is
derived from, so its rows are the spine: each gets a stable `VT-nn` id in spec
order. Every other document keeps its OWN numbering untouched — the drawing's
balloons still allocate themselves, which is what makes a printed sheet readable
on its own — and this module builds the cross-reference that maps them together.

That is deliberately a cross-reference table rather than forcing one numbering
scheme on all four engines: renumbering the drawing to match the spec would mean
rewriting the balloon allocator, and a GA whose balloons skip numbers because a
spec row had no symbol is worse than one that reads 1, 2, 3.

A link is only recorded when the match is unambiguous. An unmatched item is
REPORTED as unmatched rather than guessed at, because a wrong cross-reference
sends an engineer to the wrong part.
"""
import re
from typing import Any, Optional

# Words that carry no identity: they appear in half the labels on a sheet and
# matching on them alone would link a filter to a filter bank to a filter area.
_STOP = {"the", "a", "an", "of", "for", "and", "or", "in", "on", "at", "to",
         "with", "type", "nos", "no", "set", "sets", "mm", "m", "kg", "hp",
         "size", "value", "total", "each", "per", "unit", "units", "qty",
         "quantity", "system", "details", "detail", "specification"}


def slug(text: Any) -> str:
    """A label reduced to its comparable form: `Exhaust blower (nos)` -> `exhaust-blower`."""
    words = _tokens(text)
    return "-".join(words)


def _tokens(text: Any) -> list[str]:
    raw = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())
    return [w for w in raw.split() if w and w not in _STOP]


def _identifies(label: str, text: str) -> bool:
    """Does `text` name the thing `label` names?

    Every significant word of the label must appear in the text. Requiring ALL
    of them is what stops "Filter area" matching a "Paint arresting filter bank"
    legend row: a partial overlap is a different component, not a loose spelling
    of the same one.
    """
    want = _tokens(label)
    if not want:
        return False
    have = set(_tokens(text))
    return all(w in have for w in want)


def build_register(rows: list[dict]) -> list[dict]:
    """Assign `VT-nn` to every specification row, in the order the spec prints.

    Numbering follows the specification rather than significance, so the id of an
    item never changes because another item resolved differently on a later run —
    a stable id is the whole point of having one.
    """
    register = []
    for i, row in enumerate(rows or [], 1):
        label = str(row.get("label") or "").strip()
        register.append({
            "item_id": f"VT-{i:02d}",
            "label": label,
            "slug": slug(label),
            "value": str(row.get("value") or ""),
            "origin": row.get("origin"),
            "resolved": _resolved(row),
        })
    return register


def _resolved(row: dict) -> bool:
    value = str(row.get("value") or "").strip().lower()
    return bool(value) and value not in ("to be determined",
                                         "to be confirmed with the customer")


def cross_reference(register: list[dict], drawing: Optional[dict],
                    bom: Optional[dict], quotation: Optional[dict]) -> dict[str, Any]:
    """Resolve each item's identifier in every other document.

    Returns the table plus an honest coverage count: an item that appears in no
    other document is not an error (most spec rows are not drawn or bought), but
    a package that silently linked nothing would look complete and be useless.
    """
    legend = (drawing or {}).get("legend") or []
    bom_lines = (bom or {}).get("lines") or []
    quote_items = _quote_items(quotation)

    table = []
    for item in register:
        label = item["label"]
        # The drawing's legend is PROSE ("Exhaust blower CLP-4-15-14500 (1 no)"),
        # so a balloon can only be found by looking for the label's words inside
        # it. The BOM and the quotation scope take their item names FROM the
        # specification's labels, so those match exactly — and exactly is what
        # they must do, because a near-match there ("Construction" against
        # "Construction material") is a different line, not a loose spelling.
        balloons = [str(l.get("tag")) for l in legend
                    if _identifies(label, l.get("description"))]
        bom_refs = [str(b.get("item")) for b in bom_lines
                    if slug(b.get("item")) == item["slug"]]
        quote_refs = [str(q) for q in quote_items if slug(q) == item["slug"]]
        entry = {
            "item_id": item["item_id"],
            "label": label,
            "specification": label,
            "drawing_balloons": balloons,
            "bom_items": bom_refs,
            "quotation_items": quote_refs,
        }
        entry["appears_in"] = [name for name, hit in (
            ("specification", True), ("drawing", bool(balloons)),
            ("bom", bool(bom_refs)), ("quotation", bool(quote_refs))) if hit]
        table.append(entry)

    linked = [e for e in table if len(e["appears_in"]) > 1]
    return {
        "items": table,
        "linked_count": len(linked),
        "item_count": len(table),
        # Per-document coverage is the useful signal. A single "linked" count
        # hides the shape of the package: this quotation carries the whole
        # machine as one scope list, so EVERY item appears in it, and a headline
        # of "26 of 26 linked" would read as a quality score when it is really a
        # statement about how the quotation is structured.
        "coverage": {
            "drawing": sum(1 for e in table if e["drawing_balloons"]),
            "bom": sum(1 for e in table if e["bom_items"]),
            "quotation": sum(1 for e in table if e["quotation_items"]),
        },
        # Stated, not hidden: these are specification rows that no drawing
        # balloon, BOM line or quotation item refers to. Usually correct (a
        # material grade is not a purchased part), and worth an engineer's eye.
        "specification_only": [e["item_id"] for e in table
                               if len(e["appears_in"]) == 1],
    }


def _quote_items(quotation: Optional[dict]) -> list[str]:
    """Descriptions of whatever the quotation actually lists.

    The quotation's shape differs by category, so several known keys are tried
    and anything unrecognised simply yields no links rather than an exception.
    """
    if not quotation:
        return []
    out: list[str] = []
    for key in ("items", "scope", "line_items", "inclusions"):
        for entry in quotation.get(key) or []:
            if isinstance(entry, str):
                out.append(entry)
            elif isinstance(entry, dict):
                text = entry.get("description") or entry.get("item") or entry.get("label")
                if text:
                    out.append(str(text))
    return out


def markdown(xref: dict) -> str:
    """The cross-reference schedule, as it would appear on a real package."""
    lines = ["## Document cross-reference", "",
             "Every row below is ONE engineering item. The columns give the "
             "identifier that item carries in each document.", "",
             "| Item | Description | Drawing balloon | BOM | Quotation |",
             "| --- | --- | --- | --- | --- |"]
    for e in xref.get("items") or []:
        lines.append(
            f"| {e['item_id']} | {e['label']} | {', '.join(e['drawing_balloons']) or '-'} "
            f"| {', '.join(e['bom_items']) or '-'} | {', '.join(e['quotation_items']) or '-'} |")
    cov = xref.get("coverage") or {}
    lines += ["", f"{xref.get('item_count', 0)} engineering items: "
                  f"{cov.get('drawing', 0)} appear on the drawing, "
                  f"{cov.get('bom', 0)} in the bill of materials, "
                  f"{cov.get('quotation', 0)} in the quotation scope.", "",
              "An item that appears only in the specification is normal — a "
              "material grade or a design velocity is not a purchased part."]
    return "\n".join(lines)
