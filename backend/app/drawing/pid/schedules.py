"""The line schedule and the instrument index.

These are what make the sheet READABLE WITHOUT THE STUDIO. A P&ID's symbols say
what is connected; the schedules say what each connection carries and who
measures it. Printed or emailed, the sheet has to stand on its own — the same
argument `sheet._item_table` makes for a GA's parts list.

EVERY CELL COMES FROM AN `Attr.text`, never from a raw value. That is the whole
reason the schedules are built here rather than formatted inline while drawing:
one place decides what may print, and the QA gate can then check the schedule
against the drawing and find a disagreement.
"""
from ...engineering.process_model import STATUS_PROPOSED

# (heading, width fraction, clip). Headings are lower-cased to index the row
# dicts, so a column is renamed in exactly one place.
LINE_COLUMNS = [
    ("LINE", 0.10, 10),
    ("SERVICE", 0.30, 40),
    ("FROM", 0.13, 16),
    ("TO", 0.13, 16),
    ("SIZE", 0.10, 12),
    ("FLOW", 0.13, 16),
    ("SPEC", 0.11, 18),
]

INSTRUMENT_COLUMNS = [
    ("TAG", 0.12, 12),
    ("SERVICE", 0.42, 56),
    ("LOCATION", 0.16, 20),
    ("SETPOINT", 0.13, 14),
    ("STATUS", 0.17, 22),
]

_MOUNTING = {"field": "Field", "panel": "Panel", "local_panel": "Local panel"}


def line_rows(train, tags: dict) -> list:
    """One row per drawn line. `tags` maps a node key to its plant tag."""
    out = []
    for s in train.streams:
        out.append({
            "line": s.tag,
            "service": s.service or s.medium.title(),
            "from": tags.get(s.frm, s.frm),
            "to": tags.get(s.to, s.to),
            "size": s.size.text,
            "flow": s.flow.text,
            "spec": s.spec.text,
        })
    return out


def instrument_rows(train) -> list:
    """One row per bubble, stating plainly which devices are unconfirmed.

    A PROPOSED device that reached the index without saying so would read as
    confirmed scope of supply — the dashed circle is a convention, and a
    convention alone is not an adequate disclosure on a document someone may
    order from.
    """
    out = []
    for i in train.instruments:
        out.append({
            "tag": i.tag,
            "service": i.service,
            "location": _MOUNTING.get(i.mounting, i.mounting.title()),
            "setpoint": i.setpoint.text,
            "status": ("TO BE CONFIRMED" if i.status == STATUS_PROPOSED
                       else "Per standard"),
        })
    return out


def valve_rows(train) -> list:
    """Inline valves and dampers, as legend rows rather than a third table.

    They earn a tag and a line, but not a column of their own: a fail action is
    the only attribute anyone would schedule and nobody has stated one, so a
    table would be five rows of TBD.
    """
    return [{"tag": v.tag, "description": f"{v.label} (on {v.on})"}
            for v in train.inline]


def equipment_rows(train) -> list:
    """The equipment schedule — what the side column carries as the BOM.

    Reuses the GA payload's `bom` shape so `sheet.side_column` and the studio's
    existing panel both render it with no change.
    """
    out = []
    for n in train.nodes:
        if n.boundary:
            continue
        spec = "; ".join(f"{c} {a.text}" for c, a in n.attrs) or "-"
        out.append({"item": f"{n.tag}  {n.label}", "spec": spec,
                    "origin": "rule"})
    return out
