"""What the sheet is ALLOWED to claim, given what the engineering resolved.

WHY THIS MODULE EXISTS. The drawing engine had two outcomes: it either drew
dimensioned views or it printed "NO DIMENSIONED VIEWS" in the middle of an empty
sheet. Both were honest, but the second reads as a broken tool rather than an
engineering position, and it gave the reader nothing — not the equipment, not
the reason, not what to send back.

There are really THREE states, and naming them is what lets the sheet be
professional in every one of them:

    FULL       every axis resolved -> a normal dimensioned GA
    PARTIAL    some axes resolved  -> draw what is known, TBD what is not
    SCHEMATIC  no axis resolved    -> a PRELIMINARY schematic, clearly marked

THE RULE THAT SHAPES ALL THREE. A state may only ever WEAKEN a claim, never
strengthen one. Nothing here supplies a dimension, a default, or a nominal size
that could be mistaken for engineering — a SCHEMATIC sheet is drawn to no scale
and says so on its face, in its title block, and in its notes. Golden rule #2 is
not relaxed because the sheet would look nicer if it were.

This module is CATEGORY-AGNOSTIC on purpose. The oven is what exposed the gap,
but a conveyor, a duct run and a pretreatment line hit it the same way, so the
states are decided from the resolved envelope rather than from equipment type.
"""
from typing import NamedTuple, Optional

AXES = ("length", "width", "height")

FULL = "fully_dimensioned"
PARTIAL = "partially_dimensioned"
SCHEMATIC = "schematic"

STATE_LABELS = {
    FULL: "Dimensioned general arrangement",
    PARTIAL: "Partially dimensioned - unresolved sizes shown as TBD",
    SCHEMATIC: "Preliminary schematic - not to scale",
}

# What a reader must be told, per state, before they can act on the sheet. These
# are STATEMENTS ABOUT THE DOCUMENT, so they belong with the state rather than
# in the sheet renderer, and every consumer (SVG, PDF, DXF, the agent summary)
# gets the same wording.
STATE_NOTES = {
    FULL: (),
    PARTIAL: (
        "PARTIALLY DIMENSIONED - dimensions shown TBD are not yet engineered.",
        "Views that cannot be drawn to size are omitted, never approximated.",
    ),
    SCHEMATIC: (
        "PRELIMINARY SCHEMATIC - NOT FOR FABRICATION.",
        "DIMENSIONS PENDING ENGINEERING / CLIENT CONFIRMATION.",
        "Arrangement is indicative only and drawn to NO SCALE.",
    ),
}


class Geometry(NamedTuple):
    """The envelope, classified."""
    state: str
    known: tuple                  # axes with a resolved dimension
    missing: tuple                # axes without one
    scale_is_real: bool           # False -> the sheet must print NTS

    @property
    def is_schematic(self) -> bool:
        return self.state == SCHEMATIC

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def notes(self) -> tuple:
        return STATE_NOTES[self.state]


def classify(env: dict) -> Geometry:
    """Decide the drawing state from the resolved envelope alone.

    A dimension counts as resolved only when it is a real positive number. A
    zero, a None or a string is NOT a dimension — treating any of them as one is
    exactly how a fabricated size reaches a drawing.
    """
    env = env or {}
    known, missing = [], []
    for axis in AXES:
        v = env.get(axis)
        (known if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
         else missing).append(axis)

    if not known:
        return Geometry(SCHEMATIC, (), tuple(missing), False)
    if not missing:
        return Geometry(FULL, tuple(known), (), True)
    return Geometry(PARTIAL, tuple(known), tuple(missing), True)


# --------------------------------------------------------------------------
# What is missing, and what the reader should DO about it
# --------------------------------------------------------------------------
# An unresolved item is only useful if the sheet says who resolves it. These
# three classes are the same distinction the package layer already draws
# between an engineering gap and a customer decision, applied to the drawing:
#
#   GEOMETRY   blocks a dimensioned GA outright
#   DETAIL     enriches the sheet but never blocks it
#   CONFIRM    belongs to the customer's process and must stay TBD
#
GEOMETRY = "geometry"
DETAIL = "detail"
CONFIRM = "confirm"

# Actions for the three envelope axes. Deliberately phrased as what to CONFIRM,
# not as a value to supply, because the engine must not hint at an answer.
_AXIS_ACTION = {
    "length": "Confirm overall length / throughput requirement",
    "width": "Confirm chamber width and service access arrangement",
    "height": "Confirm internal envelope and heating / insulation build-up",
}

# A resolved-row label is matched against these to decide WHO owns the gap. The
# match is on contained words because spec labels vary by category ("Air volume
# (m3/h)", "Exhaust airflow"), and an unmatched row falls to engineering review
# rather than being assumed to be the customer's — the same default the package
# layer's assumption engine takes.
# NOTE the absence of a bare "capacity": it matched "Heating capacity
# (kcal/hr)", which is an ENGINEERING OUTPUT the rules compute, and telling the
# reader to go and ask the customer for it is worse than saying nothing. Terms
# here must name something only the customer's process can answer.
_CUSTOMER_OWNED = (
    "paint", "product", "job weight", "job size", "batch", "shift",
    "operating temp", "throughput", "production capacity", "material handling",
    "utilities", "power supply", "fuel", "solvent", "consumption",
    "process temp", "component size",
)


def action_for(label: str, kind: str = DETAIL) -> str:
    """The 'required action' cell for one unresolved parameter."""
    low = str(label or "").strip().lower()
    for axis, action in _AXIS_ACTION.items():
        if low.startswith(f"overall {axis}") or low == axis:
            return action
    if any(w in low for w in _CUSTOMER_OWNED):
        return "Confirm with customer - process input"
    if kind == GEOMETRY:
        return "Engineering input required before a dimensioned GA"
    return "Engineering selection required"


def unresolved(env: dict, rows: list) -> list[dict]:
    """Every unresolved parameter, classified, with the action that clears it.

    Returns rows of {parameter, status, action, kind}. The ENVELOPE AXES COME
    FIRST because they are the ones that decide whether a GA can exist at all —
    a reader scanning the schedule should meet the blocking items before the
    enriching ones.
    """
    out: list[dict] = []
    g = classify(env)
    for axis in g.missing:
        out.append({"parameter": f"Overall {axis}", "status": "TBD",
                    "action": _AXIS_ACTION[axis], "kind": GEOMETRY})

    for row in rows or []:
        val = str(row.get("value", "")).strip().lower()
        if row.get("origin") == "tbd" or val == "to be determined":
            label = str(row.get("label") or "").strip()
            if not label:
                continue
            kind = CONFIRM if row.get("origin") == "customer_decision" else DETAIL
            out.append({"parameter": label, "status": "TBD",
                        "action": action_for(label, kind), "kind": kind})
    return out


def required_inputs_note(g: Geometry) -> Optional[str]:
    """One line naming what would unlock a dimensioned GA, or None."""
    if not g.missing:
        return None
    names = ", ".join(g.missing)
    return f"A dimensioned GA needs: overall {names}."
