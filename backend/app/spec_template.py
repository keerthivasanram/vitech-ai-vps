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
import re

from .catalog import origin_label

TBD_VALUE = "To be determined"

# Per-field kind — documents what the field IS and drives the TBD message +
# geometry extraction:
#   geometry — a numeric dimensional field the 2D drawing consumes
#   computed — should come from an engineering calculation (formula + standard)
#   standard — a standard selection / reused categorical value
#   text     — descriptive
_KIND_NEED = {
    "customer_decision": "Customer to confirm the required option.",
    "geometry": "Needs a dimensional calculation (engineering rule) or the client dimension.",
    "computed": "Needs an engineering calculation (formula + standard).",
    "standard": "Needs a standard selection or a historical match.",
    "text": "Needs engineering input.",
}


def _norm(s):
    return str(s or "").strip().lower()


def _tbd_row(field):
    # A field the CUSTOMER must decide is not an engineering gap — it is a
    # question. Tagging it separately lets the agent ask instead of printing a
    # blank the reader mistakes for missing engineering (client review #10).
    decision = field.get("kind") == "customer_decision"
    return {
        "label": field["label"],
        "value": ("To be confirmed with the customer" if decision else TBD_VALUE),
        "origin": "customer_decision" if decision else "tbd",
        "origin_label": origin_label("customer_decision" if decision else "tbd"),
        "source": None,
        "reason": _KIND_NEED.get(field.get("kind"), _KIND_NEED["text"]),
        "kind": field.get("kind"),
    }


def _keys_for(field, profile) -> list[str]:
    """The historical record keys that hold this template field.

    An offer stores `technical_details` keyed by field name (`dry_scrubber`),
    while the template names the field by label ("Dry scrubber"), so the two are
    matched through the profile's own `field_labels` map plus the obvious
    snake_case form of the label.
    """
    label = _norm(field.get("label"))
    keys = [k for k, lbl in ((profile or {}).get("field_labels") or {}).items()
            if _norm(lbl) == label]
    slug = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
    if slug and slug not in keys:
        keys.append(slug)
    return keys


def _num_text(value) -> str:
    """A requirement number as an engineer wrote it: 9000, not 9000.0."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _field_from_requirement(field, profile, params):
    """The CLIENT'S OWN STATED VALUE for this field — checked before anything else.

    This rung was MISSING from the ladder the module docstring describes, and the
    gap was visible on a real sheet: asked for a 9000 m3/h dust collector, the
    specification printed "Air volume (m3/h): To be determined" while separately
    showing a DERIVED "Air volume cfm: 5297" as client-given. The stated duty was
    on the page in the unit nobody asked for and absent in the unit they did.

    The cause is that the template matches by LABEL: when the nearest offer
    records the duty under a different key, the template's own field found no
    resolved row and fell straight through to history and then TBD — never once
    consulting the requirement that started the whole thing.

    A value the customer stated is the most authoritative source in the system,
    so it outranks history, and it can never be right to print it as a gap. It
    is looked up through the same `field_labels` map history uses, so a category
    gains this the moment it labels its keys.
    """
    if not params:
        return None
    for key in _keys_for(field, profile):
        value = params.get(key)
        if value in (None, "", []):
            continue
        return {
            "label": field["label"],
            "value": _num_text(value),
            "origin": "given",
            "origin_label": origin_label("given"),
            "source": None,
            "reason": "Client requirement (authoritative).",
            "kind": field.get("kind"),
        }
    return None


def _field_from_history(field, profile, offers, params):
    """Search comparable offers for THIS field before declaring it unknown.

    The nearest offer decides most of a spec, but it is one document: a field it
    happens to leave blank may be answered by the next-closest design. Before
    this, `dry_scrubber` was `None` on the nearest booth and the template stopped
    there, printing a TBD while several comparable booths on file had the answer
    (client review defect #6).

    The same size guard applies as everywhere else: a value engineered for a
    materially different duty is not evidence for this one, so it is skipped
    rather than borrowed. Retrieval must not reintroduce the defect that
    `demote_unscalable` exists to prevent.
    """
    if not offers:
        return None
    from .validate import fits_size, is_size_dependent

    keys = _keys_for(field, profile)
    if not keys:
        return None

    for hit in offers:
        rec = (hit or {}).get("record") or {}
        tech = rec.get("technical_details") or {}
        for key in keys:
            value = tech.get(key)
            if value in (None, "", []) or _norm(value) == _norm(TBD_VALUE):
                continue
            text = value if isinstance(value, str) else str(value)
            if (is_size_dependent(field.get("label"), text)
                    and not fits_size(params, rec.get("given_data") or {}, profile)):
                continue                     # a different-sized machine's answer
            return {
                "label": field["label"],
                "value": text,
                "origin": "reused",
                "origin_label": origin_label("reused"),
                "source": hit.get("id") or rec.get("id"),
                "reason": (f"Field-level match: the nearest design left this blank, so "
                           f"{field['label'].lower()} was taken from comparable project "
                           f"{hit.get('id') or rec.get('id')}."),
                "kind": field.get("kind"),
            }
    return None


def apply_template(profile, technical, offers=None, params=None):
    """Reconcile resolved `technical` rows against the category spec template:
    resolved rows appear in template order, and every template field with no
    resolved value is looked up in comparable history before falling back to an
    explicit TBD row. Rows the template doesn't mention (extra reused detail) are
    appended, so nothing is lost. No template -> `technical` unchanged (opt-in)."""
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
            continue
        # TBD is the LAST resort, not the first answer. The client's own stated
        # value is consulted FIRST — including for a customer decision, because
        # a decision the customer has already made is an answer, not a question.
        # Only then history, which a customer decision is never looked up in:
        # that one is theirs to make, not ours to find.
        found = _field_from_requirement(field, profile, params or {})
        if found is None and field.get("kind") != "customer_decision":
            found = _field_from_history(field, profile, offers, params or {})
        out.append(found or _tbd_row(field))
    for it in technical:
        if id(it) not in used:
            out.append(it)
    return out


def template_stats(technical):
    """(#resolved, #tbd) over a reconciled technical list — for completeness."""
    tbd = sum(1 for t in technical if t.get("origin") == "tbd")
    return len(technical) - tbd, tbd
