"""Spec template — the canonical OUTPUT-field list per equipment category.

Defines WHAT a complete engineering specification contains for a category, so
that "a value is missing" is well-defined. Every template field resolves, in
priority order, to:
    client-given  ->  engineering-rule calculation  ->  reused historical value
    ->  explicit TBD (needs engineering input)
NEVER a guess. The TBD rows are the deterministic guardrail: a gap is shown as a
gap, so the model is never handed a vacuum to hallucinate into (golden rule #2).

This is the surface the client's uploaded engineering field-lists slot into — add
a category's field list to `spec_template` in catalog.py and the resolver walks
it automatically. Categories without a template are unaffected (opt-in).
"""
from .catalog import origin_label

TBD_VALUE = "To be determined"

# Per-field kind — documents what the field IS and drives the TBD message +
# geometry extraction:
#   geometry — a numeric dimensional field the 2D drawing consumes
#   computed — should come from an engineering calculation (formula + standard)
#   standard — a standard selection / reused categorical value
#   text     — descriptive
_KIND_NEED = {
    "geometry": "Needs a dimensional calculation (engineering rule) or the client dimension.",
    "computed": "Needs an engineering calculation (formula + standard).",
    "standard": "Needs a standard selection or a historical match.",
    "text": "Needs engineering input.",
}


def _norm(s):
    return str(s or "").strip().lower()


def _tbd_row(field):
    return {
        "label": field["label"],
        "value": TBD_VALUE,
        "origin": "tbd",
        "origin_label": origin_label("tbd"),
        "source": None,
        "reason": _KIND_NEED.get(field.get("kind"), _KIND_NEED["text"]),
        "kind": field.get("kind"),
    }


def apply_template(profile, technical):
    """Reconcile resolved `technical` rows against the category spec template:
    resolved rows appear in template order, and every template field with no
    resolved value gets an explicit TBD row. Rows the template doesn't mention
    (extra reused detail) are appended, so nothing is lost. No template ->
    `technical` unchanged (opt-in)."""
    template = (profile or {}).get("spec_template")
    if not template:
        return technical

    by_label = {}
    for it in technical:
        by_label.setdefault(_norm(it.get("label")), it)

    out, used = [], set()
    for field in template:
        hit = by_label.get(_norm(field["label"]))
        if hit is not None:
            # tag the resolved row with its template kind (geometry extraction)
            if field.get("kind") and "kind" not in hit:
                hit["kind"] = field["kind"]
            out.append(hit)
            used.add(id(hit))
        else:
            out.append(_tbd_row(field))
    for it in technical:
        if id(it) not in used:
            out.append(it)
    return out


def template_stats(technical):
    """(#resolved, #tbd) over a reconciled technical list — for completeness."""
    tbd = sum(1 for t in technical if t.get("origin") == "tbd")
    return len(technical) - tbd, tbd
