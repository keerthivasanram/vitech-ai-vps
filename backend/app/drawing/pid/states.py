"""What a P&ID sheet is allowed to claim, given what the engineering resolved.

WHY NOT `drawing/states.py`. That module decides from the resolved ENVELOPE, and
its docstring makes that a principle rather than an implementation detail. A
P&ID's completeness has nothing to do with the envelope: a scrubber whose
dimensions are entirely unknown can still have a complete, true and useful
process diagram, because a P&ID is not to scale. Adding a parameter to
`classify()` would blur two genuinely different questions.

So this module owns the QUESTION and imports the VOCABULARY. The three state
keys, the three gap kinds and `action_for` all come from the GA module, so both
sheets speak one language, the studio's `is-${drawing.state}` styling keeps
working, and a reader who has learnt one sheet has learnt the other.

    FULL       every line carries a size and a flow, and no instrument is
               merely proposed -> a P&ID that could be issued for review
    PARTIAL    the topology is complete and TRUE, but some sizes, specs or
               instrument scope are unresolved
    SCHEMATIC  no process template applies -> the sheet draws NO train

THE HONEST POSITION TODAY IS PARTIAL, for every category, and probably for
months: no liquid velocity standard exists anywhere in the platform, so every
recirculation line prints TBD, and nobody has confirmed Vitech's instrument
scope. Presenting that as FULL would be the failure this whole engine exists to
prevent.
"""
from typing import NamedTuple

from ..states import CONFIRM, DETAIL, FULL, GEOMETRY, PARTIAL, SCHEMATIC
from ..states import action_for
from ...engineering.process_model import STATUS_PROPOSED

STATE_LABELS = {
    FULL: "Process and instrumentation diagram",
    PARTIAL: "Process topology complete - line data to be confirmed",
    SCHEMATIC: "Process topology not established",
}

STATE_NOTES = {
    FULL: (),
    PARTIAL: (
        "PROCESS TOPOLOGY COMPLETE - LINE SIZES AND INSTRUMENT SCOPE TO BE "
        "CONFIRMED.",
        "Items shown TBD are not yet engineered; see the schedule below.",
    ),
    SCHEMATIC: (
        "PROCESS TOPOLOGY NOT ESTABLISHED FOR THIS EQUIPMENT.",
        "NO PROCESS DIAGRAM IS DRAWN - a generic arrangement would assert "
        "connections this plant may not have.",
    ),
}

STANDING_NOTES = [
    "Diagram is schematic. NOT TO SCALE - no dimension is implied.",
    "Process topology per equipment type; line data as scheduled.",
    "Instruments shown broken are PROPOSED - scope to be confirmed.",
    "Engineer-reviewed draft - not released for construction.",
]


class State(NamedTuple):
    state: str
    label: str
    notes: tuple
    unresolved_lines: int
    proposed_instruments: int

    @property
    def is_schematic(self) -> bool:
        return self.state == SCHEMATIC


def classify(train) -> State:
    """Decide the state from the TRAIN, never from the envelope."""
    if not train or not train.ok or not train.nodes:
        return State(SCHEMATIC, STATE_LABELS[SCHEMATIC],
                     STATE_NOTES[SCHEMATIC], 0, 0)

    open_lines = sum(1 for s in train.streams
                     if not s.size.resolved or not s.flow.resolved)
    proposed = sum(1 for i in train.instruments
                   if i.status == STATUS_PROPOSED)
    if open_lines or proposed:
        return State(PARTIAL, STATE_LABELS[PARTIAL], STATE_NOTES[PARTIAL],
                     open_lines, proposed)
    return State(FULL, STATE_LABELS[FULL], STATE_NOTES[FULL], 0, 0)


def unresolved(train, rows: list) -> list:
    """Every gap on this sheet, classified, with the action that clears it.

    Ordered so a reader meets the BLOCKING items first, the same argument
    `drawing/states.unresolved` makes: what stops the diagram existing comes
    before what merely enriches it.
    """
    out: list = []
    if not train or not train.ok:
        out.append({
            "parameter": "Process topology",
            "status": "TBD",
            "kind": GEOMETRY,
            "action": ("Engineering input required - no process template "
                       "exists for this equipment"),
        })
        return out

    for key, reason in train.dropped:
        out.append({"parameter": f"{key.replace('_', ' ').title()} - {reason}",
                    "status": "TBD", "kind": DETAIL,
                    "action": "Confirm whether this item is in scope"})

    # One row per line missing a size. A line with no bore cannot be ordered,
    # so this is the schedule's most actionable content.
    no_size = [s for s in train.streams if not s.size.resolved]
    for s in no_size:
        out.append({
            "parameter": f"Line {s.tag} size - {s.service or s.medium}",
            "status": "TBD", "kind": DETAIL,
            "action": ("Confirm line sizing basis (transport / liquid "
                       "velocity) for this medium"),
        })

    # Instruments are GROUPED. One row per device would bury the three or four
    # rows a reader can actually act on under a list that all says one thing:
    # nobody has confirmed the instrument scope.
    proposed = [i for i in train.instruments if i.status == STATUS_PROPOSED]
    if proposed:
        out.append({
            "parameter": (f"Instrument scope ({len(proposed)} device(s): "
                          + ", ".join(i.tag for i in proposed) + ")"),
            "status": "TBD", "kind": CONFIRM,
            "action": "Confirm Vitech's standard instrument scope of supply",
        })
        out.append({
            "parameter": "Instrument setpoints and alarm settings",
            "status": "TBD", "kind": CONFIRM,
            "action": "Confirm with customer / process - none held on file",
        })

    # Anything the SPECIFICATION itself left open still belongs here, routed by
    # the GA's own owner logic so a customer-owned parameter is never sent to
    # engineering and vice versa.
    for row in rows or []:
        val = str(row.get("value", "")).strip().lower()
        if row.get("origin") == "tbd" or val == "to be determined":
            label = str(row.get("label") or "").strip()
            if not label:
                continue
            kind = CONFIRM if row.get("origin") == "customer_decision" else DETAIL
            out.append({"parameter": label, "status": "TBD", "kind": kind,
                        "action": action_for(label, kind)})
    return out
