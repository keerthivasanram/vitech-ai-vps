"""Where a line may attach to a symbol — as pure data, not as drawing code.

WHY THIS IS ITS OWN MODULE. Routing must not depend on draw order. If a port
were a coordinate a glyph happened to return while painting itself, then the
router would need the canvas built before it could plan a line, the QA gate
could not ask "does this line start on a real port?" without rendering a sheet,
and moving a nozzle on a symbol would silently move every line attached to it.

Ports are FRACTIONS of the symbol's box, so a symbol can be resized — a booth
spanning two columns, a tower drawn taller on A2 — without a single route
changing. (0,0) is the box's top-left, matching the sheet's own convention.

A PORT IS A REAL FEATURE, not a convenience. A scrubber tower takes gas low and
discharges from the top because that is how the machine works; a centrifugal
pump discharges vertically. Those are the same facts of the equipment type that
license the topology itself, so they are declared here beside it.
"""
from typing import Optional

PORTS: dict = {
    # --- boundaries ---------------------------------------------------------
    "connector": {"in": (0.0, 0.5), "out": (1.0, 0.5)},

    # --- scrubber ----------------------------------------------------------
    # Gas enters LOW and leaves at the TOP, the liquor drains from the bottom.
    "scrub_tower": {"in_low": (0.0, 0.78), "out_top": (0.5, 0.0),
                    "drain": (0.5, 1.0), "in": (0.0, 0.5), "out": (1.0, 0.5)},
    "demister": {"in": (0.0, 0.5), "out": (1.0, 0.5)},
    # FED FROM THE RIGHT, because the recirculation pump is downstream in the
    # lane below and a header fed from the left would send its delivery line
    # back across the tower it enters.
    "spray_header": {"in": (1.0, 0.5), "out": (0.0, 0.5)},
    # An OPEN tank is filled from the top, draws off low on the DOWNSTREAM
    # side, and drains from the bottom. The suction port was on the left while
    # the pump it feeds is to the right, so the line left the tank, turned, and
    # ran back across the tank it had just left.
    "tank_open": {"in_top": (0.5, 0.0), "out_low": (1.0, 0.72),
                  "drain": (0.5, 1.0), "in": (0.0, 0.4), "out": (1.0, 0.5)},
    "strainer_y": {"in": (0.0, 0.5), "out": (1.0, 0.5)},
    # A centrifugal pump discharges VERTICALLY from the volute top.
    "pump_centrifugal": {"suction": (0.0, 0.55), "discharge": (0.5, 0.0),
                         "in": (0.0, 0.55), "out": (0.5, 0.0)},
    "fan_centrifugal": {"suction": (0.0, 0.55), "discharge": (1.0, 0.45),
                        "in": (0.0, 0.55), "out": (1.0, 0.45)},
    "stack": {"in": (0.0, 0.72), "out": (0.5, 0.0)},

    # --- booth / filtration -------------------------------------------------
    "filter_panel": {"in": (0.0, 0.5), "out": (1.0, 0.5)},
    "filter_bank": {"in": (0.0, 0.5), "out": (1.0, 0.5)},
    "carbon_bed": {"in": (0.0, 0.5), "out": (1.0, 0.5)},
    "booth_enclosure": {"in_face": (0.0, 0.5), "out_extract": (1.0, 0.5),
                        "in": (0.0, 0.5), "out": (1.0, 0.5)},
    "panel": {"in": (0.0, 0.5), "out": (1.0, 0.5), "bottom": (0.5, 1.0)},
}

# Every kind falls back to these, so a new glyph is routable the moment it is
# registered. A template naming a port that does not exist is a source error and
# the QA gate reports it (`unknown_port`) rather than routing from (0,0) — which
# would draw a line from the symbol's top-left corner and look almost right.
_DEFAULT = {"in": (0.0, 0.5), "out": (1.0, 0.5)}


def port(kind: str, name: str) -> Optional[tuple]:
    """The fractional (x, y) of one named port, or None if it does not exist."""
    return PORTS.get(kind, _DEFAULT).get(name) or _DEFAULT.get(name)


def port_xy(kind: str, name: str, x: float, y: float, w: float,
            h: float) -> tuple:
    """One named port as SHEET millimetres, given the symbol's placed box."""
    fx, fy = port(kind, name) or _DEFAULT["out"]
    return (x + fx * w, y + fy * h)


def has_port(kind: str, name: str) -> bool:
    return port(kind, name) is not None
