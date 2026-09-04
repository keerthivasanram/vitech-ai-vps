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

from .catalog import CONFIRMED, DERIVED, INDICATIVE, TBD, origin_label, state_for, state_label

TBD_VALUE = "To be determined"

# Origins that mean "this came from another project". These are the only ones a
# stated requirement is allowed to displace: everything else is either the
# customer's own value already, or engineering computed FROM it.
_REUSE_ORIGINS = frozenset({"reused", "kept", "existing", "adapted",
                            "scaled", "interpolated", "consistent"})

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
    """The record / requirement keys that hold this template field.

    An offer stores `technical_details` keyed by field name (`dry_scrubber`),
    while the template names the field by label ("Dry scrubber"), so the two are
    matched through the profile's own `field_labels` map plus the obvious
    snake_case form of the label.

    `from_given` is consulted too, because it is the profile's own statement
    that a REQUIREMENT key answers a DIFFERENT record key — an oven's stated
    `heating_mode` answers the offer's `heating` field. The planner already
    honours that mapping and treats the stated value as authoritative; without
    it here, the same requirement resolved through knowledge mode (where there
    is no offer for the planner to work from) fell through to TBD instead.
    """
    profile = profile or {}
    label = _norm(field.get("label"))
    keys = [k for k, lbl in (profile.get("field_labels") or {}).items()
            if _norm(lbl) == label]
    for given_key, target_key in (profile.get("from_given") or {}).items():
        if target_key in keys and given_key not in keys:
            keys.append(given_key)
    slug = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
    if slug and slug not in keys:
        keys.append(slug)
    return keys


# --------------------------------------------------------------------------
# COMPOSED FIELDS.
#
# Some template fields are one STATEMENT made of several requirement keys. The
# overall envelope is the standing example: the customer states a length, a
# width and a height, and the specification states "4000 x 2500 x 2500". There
# is no requirement key and no offer key named "overall_dimensions_mm", so a
# label-matched lookup could never find it — and an oven whose three axes were
# all confirmed printed its own overall size as "To be determined", directly
# beside the same three numbers listed as client-given data.
#
# A composer only REFORMATS values the customer already supplied. It performs no
# arithmetic and adds no information, so the result is a CONFIRMED input, not a
# derived one — which is why it is allowed to carry origin "given".
# --------------------------------------------------------------------------
def _compose_dims_mm(params):
    """The overall envelope in millimetres, from the three confirmed axes.

    All three are required: two axes out of three is not an envelope, and
    printing a partial one would state a size the customer never gave. A missing
    axis leaves the field to the normal TBD path, where the drawing engine's own
    state machine already reports which axes are unresolved.
    """
    axes = [params.get(k) for k in ("length_m", "width_m", "height_m")]
    if any(a in (None, "") for a in axes):
        return None
    try:
        mm = [float(a) * 1000.0 for a in axes]
    except (TypeError, ValueError):
        return None
    return " x ".join(str(int(v)) if float(v).is_integer() else str(v) for v in mm)


_COMPOSERS = {"dims_mm": _compose_dims_mm}


def _field_composed(field, params):
    composer = _COMPOSERS.get(field.get("compose"))
    if composer is None or not params:
        return None
    value = composer(params)
    if value in (None, "", []):
        return None
    return {
        "label": field["label"],
        "value": value,
        "origin": "given",
        "origin_label": origin_label("given"),
        "source": None,
        "reason": "Client requirement (authoritative) - stated overall size.",
        "kind": field.get("kind"),
    }


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
            used.add(id(hit))
            # A REUSED value never outranks the customer's own words.
            #
            # The requirement rung was only ever reached when NOTHING resolved,
            # so a value carried over from the nearest design short-circuited it
            # — and a stated field was answered with a different machine's
            # answer rather than with the customer's. It is the worse half of
            # the same defect the TBD case shows: a gap is visibly a gap, but a
            # confidently reused contradiction reads as engineering.
            #
            # Only reuse is displaced. A rule-computed or standards-selected
            # value stays put: those are engineering that FOLLOWS from the
            # requirement, not a substitute for it, and the customer stating an
            # input is not a reason to discard the calculation it feeds.
            if hit.get("origin") in _REUSE_ORIGINS:
                stated = _field_from_requirement(field, profile, params or {})
                if stated is not None and _norm(stated["value"]) != _norm(hit.get("value")):
                    stated["superseded"] = {
                        "value": hit.get("value"), "source": hit.get("source")}
                    stated["reason"] = (
                        f"Client requirement (authoritative). Supersedes "
                        f"{hit.get('value')!r} reused from "
                        f"{hit.get('source') or 'the nearest design'}.")
                    out.append(stated)
                    continue
            # tag the resolved row with its template kind (geometry extraction)
            if field.get("kind") and "kind" not in hit:
                hit["kind"] = field["kind"]
            out.append(hit)
            continue
        # TBD is the LAST resort, not the first answer. The client's own stated
        # value is consulted FIRST — including for a customer decision, because
        # a decision the customer has already made is an answer, not a question.
        # Only then history, which a customer decision is never looked up in:
        # that one is theirs to make, not ours to find.
        found = _field_composed(field, params or {})
        if found is None:
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


def apply_states(technical):
    """Stamp every row with its requirement STATE, in place.

    `origin` says how a value was produced; `state` says what a reviewer may do
    with it. Four buckets, and every row lands in exactly one — see
    `catalog.ORIGIN_STATES`. Nothing here changes a value: this is a reading of
    the provenance each row already carries, which is precisely why it can be
    trusted as a summary of the whole specification.
    """
    for it in technical or ():
        it["state"] = state_for(it.get("origin"))
        it["state_label"] = state_label(it["state"])
    return technical


def state_summary(technical):
    """The four buckets, as labels, for the caller that wants the partition
    rather than the rows. A PARTITION: the four counts sum to the row count."""
    rows = technical or []
    buckets = {CONFIRMED: [], DERIVED: [], TBD: [], INDICATIVE: []}
    for it in rows:
        buckets.setdefault(state_for(it.get("origin")), []).append(it.get("label"))
    return {
        "confirmed": buckets[CONFIRMED],
        "derived": buckets[DERIVED],
        "tbd": buckets[TBD],
        "indicative": buckets[INDICATIVE],
        "total": len(rows),
    }
