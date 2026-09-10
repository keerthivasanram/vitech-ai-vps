"""The ISA-5.1 glyph set: one function per equipment kind.

WHY NONE OF THE GA GLYPHS ARE REUSED. `drawing/symbols.py` draws a blower as a
scroll volute with an impeller and a discharge port, because a GA is a picture
of the machine and that is what the machine looks like. A P&ID is a schematic
language: the same blower is a circle with a tangent, and its meaning comes from
the tag beside it, not from its shape. Mixing the two vocabularies on one sheet
produces a drawing that reads as neither — a picture with tags, which invites
the reader to measure it.

EVERY GLYPH IS DRAWN IN ITS OWN BOX, in sheet millimetres, and knows nothing
about the plant. Where a line attaches is declared separately in `ports.py`, so
a glyph can be redrawn without moving a single route.

NO GLYPH PRINTS A VALUE. The tag block under a symbol is written once by
`service.py` from the node's `Attr`s, which already decided what may print. A
glyph that formatted its own text would be a second place for a number to reach
the sheet, and the first one that forgot to check an origin would put an
untrusted value on a drawing.

CLIENT-EXTENSION POINT: `PID_SYMBOLS[kind]`.
"""
import math
from typing import Callable

from ..primitives import L_COMPONENT, Circle, Line, Rect, Text, poly
from ..style import (INSTRUMENT_BUBBLE, INSTRUMENT_PROPOSED, PID_SYMBOL_DETAIL,
                     PID_VESSEL, PROCESS_LINE, SIGNAL_LINE, T_TAG, T_TINY)

# The nominal symbol box, in sheet mm. A glyph may use less (a valve is small)
# but never more, because the lane pitch is sized from this.
NODE_W = 22.0
NODE_H = 16.0

# HEIGHT MULTIPLIERS. A scrubber tower is a tall vessel and a filter is a flat
# box; drawing both in a 16 mm square made the tower's own internals - the
# demister and the spray header it contains - overlap each other and its tag.
# The aspect belongs with the glyph because the glyph is what needs the room.
NODE_ASPECT = {
    "scrub_tower": 2.6,
    "tank_open": 1.15,
    "stack": 1.5,
    "carbon_bed": 1.3,
}


def node_height(kind: str) -> float:
    return NODE_H * NODE_ASPECT.get(kind, 1.0)


def _v(canvas, *shapes):
    canvas.add(*shapes)


def _stubs(canvas, x, y, w, h, bx, bw, cy=None):
    """Join a glyph's BODY to the edges of its BOX.

    Ports sit on the box, but most glyphs draw a body narrower than it - a
    strainer is a small basket in a wide cell. Without these the line stopped
    short and the symbol floated, unconnected, a few millimetres away: the
    drawing said "no connection here" at every single in-line item. The stub is
    what a real P&ID draws anyway, so the fix is also the convention.
    """
    cy = (y + h / 2) if cy is None else cy
    _v(canvas, Line(x, cy, bx, cy, *PID_VESSEL),
       Line(bx + bw, cy, x + w, cy, *PID_VESSEL))


# --- equipment --------------------------------------------------------------
def connector(canvas, x, y, w, h, node) -> None:
    """An off-sheet connection: the flag ISA uses for a line that leaves.

    Drawn as a pentagon pointing the way the process goes, so a reader can see
    at a glance that the sheet's boundary is a boundary and not a vessel.
    """
    m = min(h * 0.5, 5.0)
    cy = y + h / 2
    _v(canvas, poly([(x, cy - m), (x + w * 0.62, cy - m), (x + w, cy),
                     (x + w * 0.62, cy + m), (x, cy + m)],
                    PID_VESSEL.layer, PID_VESSEL.width))


def scrub_tower(canvas, x, y, w, h, node) -> None:
    """A vertical vessel: a tall body with dished ends."""
    bw = min(w * 0.52, 13.0)
    bx = x + (w - bw) / 2
    r = bw * 0.34
    _v(canvas,
       Line(bx, y + r, bx, y + h - r, *PID_VESSEL),
       Line(bx + bw, y + r, bx + bw, y + h - r, *PID_VESSEL),
       # dished heads, as two half-ellipses approximated by arcs of a polyline
       poly(_arc(bx + bw / 2, y + r, bw / 2, r, 180, 360),
            PID_VESSEL.layer, PID_VESSEL.width, closed=False),
       poly(_arc(bx + bw / 2, y + h - r, bw / 2, r, 0, 180),
            PID_VESSEL.layer, PID_VESSEL.width, closed=False))
    # The gas inlet nozzle, from the box edge to the shell at its port height.
    iy = y + h * 0.78
    _v(canvas, Line(x, iy, bx, iy, *PID_VESSEL))


def demister(canvas, x, y, w, h, node) -> None:
    """A mesh pad: a hatched band across the vessel it sits in."""
    _v(canvas, Rect(x, y, w, h, PID_SYMBOL_DETAIL.layer,
                    PID_SYMBOL_DETAIL.width))
    step = max(w / 7.0, 1.2)
    cx = x + step
    while cx < x + w - 0.1:
        _v(canvas, Line(cx, y, cx - step * 0.6, y + h, *PID_SYMBOL_DETAIL))
        cx += step


def spray_header(canvas, x, y, w, h, node) -> None:
    """A spray header: a run with nozzle cones beneath it."""
    cy = y + h * 0.3
    _v(canvas, Line(x, cy, x + w, cy, *PID_SYMBOL_DETAIL))
    for i in range(3):
        nx = x + w * (0.22 + 0.28 * i)
        _v(canvas, poly([(nx, cy), (nx - w * 0.07, y + h),
                         (nx + w * 0.07, y + h)],
                        PID_SYMBOL_DETAIL.layer, PID_SYMBOL_DETAIL.width))


def tank_open(canvas, x, y, w, h, node) -> None:
    """An open-topped tank: three sides and a liquid level."""
    _v(canvas,
       Line(x, y, x, y + h, *PID_VESSEL),
       Line(x + w, y, x + w, y + h, *PID_VESSEL),
       Line(x, y + h, x + w, y + h, *PID_VESSEL),
       Line(x + 0.8, y + h * 0.34, x + w - 0.8, y + h * 0.34,
            *PID_SYMBOL_DETAIL))


def strainer_y(canvas, x, y, w, h, node) -> None:
    """A Y-type strainer: the run, with the basket limb below it."""
    cy = y + h / 2
    bw = min(w * 0.5, 9.0)
    bx = x + (w - bw) / 2
    _v(canvas,
       Line(bx, cy - bw * 0.28, bx + bw, cy - bw * 0.28, *PID_VESSEL),
       Line(bx, cy + bw * 0.28, bx + bw, cy + bw * 0.28, *PID_VESSEL),
       Line(bx, cy - bw * 0.28, bx, cy + bw * 0.28, *PID_VESSEL),
       Line(bx + bw, cy - bw * 0.28, bx + bw, cy + bw * 0.28, *PID_VESSEL),
       Line(bx + bw * 0.35, cy + bw * 0.28, bx + bw * 0.75, cy + bw * 0.9,
            *PID_SYMBOL_DETAIL),
       Line(bx + bw * 0.75, cy + bw * 0.28, bx + bw * 0.95, cy + bw * 0.62,
            *PID_SYMBOL_DETAIL))
    _stubs(canvas, x, y, w, h, bx, bw, cy)


def pump_centrifugal(canvas, x, y, w, h, node) -> None:
    """The ISA centrifugal pump: a circle with a tangential discharge up."""
    r = min(w * 0.26, h * 0.34, 5.2)
    cx, cy = x + w / 2, y + h * 0.55
    _v(canvas,
       Circle(cx, cy, r, PID_VESSEL.layer, PID_VESSEL.width),
       Line(cx - r, cy, cx - r, cy - r * 0.1, *PID_VESSEL),
       # the discharge leg, rising to the port at the box top
       Line(cx, cy - r, cx, y, *PID_VESSEL),
       Line(cx - r, cy, x, cy, *PID_VESSEL))


def fan_centrifugal(canvas, x, y, w, h, node) -> None:
    """A fan / blower: a circle with an impeller mark and a discharge leg."""
    r = min(w * 0.28, h * 0.36, 5.6)
    cx, cy = x + w * 0.46, y + h * 0.55
    _v(canvas,
       Circle(cx, cy, r, PID_VESSEL.layer, PID_VESSEL.width),
       Line(cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5,
            *PID_SYMBOL_DETAIL),
       Line(cx - r * 0.5, cy + r * 0.5, cx + r * 0.5, cy - r * 0.5,
            *PID_SYMBOL_DETAIL),
       Line(x, cy, cx - r, cy, *PID_VESSEL),
       Line(cx + r, cy - r * 0.35, x + w, cy - r * 0.35, *PID_VESSEL))


def stack(canvas, x, y, w, h, node) -> None:
    """A discharge stack: a tapering duct open to atmosphere."""
    bw = min(w * 0.3, 7.0)
    cx = x + w / 2
    _v(canvas,
       Line(cx - bw / 2, y, cx - bw * 0.78, y + h, *PID_VESSEL),
       Line(cx + bw / 2, y, cx + bw * 0.78, y + h, *PID_VESSEL),
       Line(cx - bw / 2, y, cx + bw / 2, y, *PID_SYMBOL_DETAIL))


def filter_panel(canvas, x, y, w, h, node) -> None:
    """A filter: a box with the diagonal medium mark."""
    bw, bh = min(w * 0.5, 11.0), min(h * 0.62, 10.0)
    bx, by = x + (w - bw) / 2, y + (h - bh) / 2
    _v(canvas, Rect(bx, by, bw, bh, PID_VESSEL.layer, PID_VESSEL.width),
       Line(bx, by + bh, bx + bw, by, *PID_SYMBOL_DETAIL))
    _stubs(canvas, x, y, w, h, bx, bw)


def filter_bank(canvas, x, y, w, h, node) -> None:
    """A bank: three filter cells side by side, so it reads as a bank."""
    bw, bh = min(w * 0.62, 14.0), min(h * 0.62, 10.0)
    bx, by = x + (w - bw) / 2, y + (h - bh) / 2
    cell = bw / 3.0
    _v(canvas, Rect(bx, by, bw, bh, PID_VESSEL.layer, PID_VESSEL.width))
    for i in range(3):
        _v(canvas, Line(bx + cell * i, by + bh, bx + cell * (i + 1), by,
                        *PID_SYMBOL_DETAIL))
        if i:
            _v(canvas, Line(bx + cell * i, by, bx + cell * i, by + bh,
                            *PID_SYMBOL_DETAIL))
    _stubs(canvas, x, y, w, h, bx, bw)


def carbon_bed(canvas, x, y, w, h, node) -> None:
    """An adsorber: a vessel with a stippled bed."""
    bw, bh = min(w * 0.5, 11.0), min(h * 0.7, 12.0)
    bx, by = x + (w - bw) / 2, y + (h - bh) / 2
    _v(canvas, Rect(bx, by, bw, bh, PID_VESSEL.layer, PID_VESSEL.width))
    for r in range(3):
        for c in range(3):
            _v(canvas, Circle(bx + bw * (0.25 + 0.25 * c),
                              by + bh * (0.3 + 0.2 * r), 0.4,
                              PID_SYMBOL_DETAIL.layer,
                              PID_SYMBOL_DETAIL.width))
    _stubs(canvas, x, y, w, h, bx, bw)


def booth_enclosure(canvas, x, y, w, h, node) -> None:
    """The booth: an enclosure with an open working face."""
    _v(canvas, Rect(x, y, w, h, PID_VESSEL.layer, PID_VESSEL.width),
       Line(x + w * 0.16, y + h, x + w * 0.16, y + h * 0.4,
            *PID_SYMBOL_DETAIL),
       Line(x + w * 0.16, y + h * 0.4, x + w * 0.5, y + h * 0.4,
            *PID_SYMBOL_DETAIL))


def panel(canvas, x, y, w, h, node) -> None:
    """A control panel: a box with a divider, distinct from a vessel."""
    bw, bh = min(w * 0.56, 13.0), min(h * 0.56, 9.0)
    bx, by = x + (w - bw) / 2, y + (h - bh) / 2
    _v(canvas, Rect(bx, by, bw, bh, PID_VESSEL.layer, PID_VESSEL.width),
       Line(bx, by + bh * 0.3, bx + bw, by + bh * 0.3, *PID_SYMBOL_DETAIL))


PID_SYMBOLS: dict[str, Callable] = {
    "connector": connector,
    "scrub_tower": scrub_tower,
    "demister": demister,
    "spray_header": spray_header,
    "tank_open": tank_open,
    "strainer_y": strainer_y,
    "pump_centrifugal": pump_centrifugal,
    "fan_centrifugal": fan_centrifugal,
    "stack": stack,
    "filter_panel": filter_panel,
    "filter_bank": filter_bank,
    "carbon_bed": carbon_bed,
    "booth_enclosure": booth_enclosure,
    "panel": panel,
}


# --- inline elements --------------------------------------------------------
# Drawn ON a routed line, rotated to the segment they sit on. Two opposed
# triangles is the universal valve body; what distinguishes one valve from
# another is the actuator or mark above it, exactly as ISA has it.
VALVE_L = 4.4


def _rot(pts, cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (px - cx) * c - (py - cy) * s,
             cy + (px - cx) * s + (py - cy) * c) for px, py in pts]


def inline_symbol(canvas, kind: str, cx: float, cy: float,
                  ang: float) -> None:
    """One valve or damper, centred on (cx, cy) and rotated to its line."""
    L, H = VALVE_L, VALVE_L * 0.62
    if kind == "damper":
        # A damper is a blade in a duct, not a valve body.
        pts = _rot([(cx - L / 2, cy - H), (cx - L / 2, cy + H)], cx, cy, ang)
        pts2 = _rot([(cx + L / 2, cy - H), (cx + L / 2, cy + H)], cx, cy, ang)
        blade = _rot([(cx - L * 0.42, cy + H * 0.7),
                      (cx + L * 0.42, cy - H * 0.7)], cx, cy, ang)
        _v(canvas,
           Line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], *PID_VESSEL),
           Line(pts2[0][0], pts2[0][1], pts2[1][0], pts2[1][1], *PID_VESSEL),
           Line(blade[0][0], blade[0][1], blade[1][0], blade[1][1],
                *PID_VESSEL))
        return

    body = _rot([(cx - L / 2, cy - H), (cx - L / 2, cy + H), (cx, cy),
                 (cx + L / 2, cy + H), (cx + L / 2, cy - H), (cx, cy)],
                cx, cy, ang)
    _v(canvas, poly(body, PID_VESSEL.layer, PID_VESSEL.width))

    if kind == "valve_check":
        # A non-return valve carries a bar the flow cannot pass backwards.
        bar = _rot([(cx + L * 0.16, cy - H), (cx + L * 0.16, cy + H)],
                   cx, cy, ang)
        _v(canvas, Line(bar[0][0], bar[0][1], bar[1][0], bar[1][1],
                        *PID_VESSEL))
    elif kind == "valve_control":
        # A control valve carries its actuator above the body.
        _v(canvas, Circle(cx, cy - H * 1.9, H * 0.8, PID_VESSEL.layer,
                          PID_VESSEL.width),
           Line(cx, cy - H, cx, cy - H * 1.9, *PID_VESSEL))


# --- instruments ------------------------------------------------------------
BUBBLE_R = 4.0


def instrument(canvas, cx: float, cy: float, tag: str, mounting: str,
               proposed: bool) -> None:
    """One ISA bubble: the tag inside a circle, on the instrument layer.

    A PROPOSED device is drawn BROKEN. That is the whole honesty convention for
    instrumentation on this sheet: a solid bubble claims the device is in the
    scope of supply, and until Vitech confirm their standard instrument scope
    nobody can claim that. The legend on the sheet says so in words as well,
    because a dashed circle is a convention a reader has to know.
    """
    pen = INSTRUMENT_PROPOSED if proposed else INSTRUMENT_BUBBLE
    _v(canvas, Circle(cx, cy, BUBBLE_R, pen.layer, pen.width))
    if mounting == "panel":
        # Panel-mounted: the bar through the bubble.
        _v(canvas, Line(cx - BUBBLE_R, cy, cx + BUBBLE_R, cy, pen.layer,
                        pen.width))
    elif mounting == "local_panel":
        _v(canvas, Rect(cx - BUBBLE_R, cy - BUBBLE_R, BUBBLE_R * 2,
                        BUBBLE_R * 2, pen.layer, pen.width))
    letters, _, loop = str(tag).partition("-")
    _v(canvas,
       Text(cx, cy - 0.2, letters, pen.layer, T_TINY, "middle", bold=True),
       Text(cx, cy + 2.6, loop, pen.layer, T_TINY, "middle"))


def signal(canvas, x1, y1, x2, y2) -> None:
    """The broken line from a bubble to what it measures.

    Its own layer, so the studio can strip every instrument and leave a clean
    process flow diagram — which is a genuinely useful second document, free.
    """
    _v(canvas, Line(x1, y1, x2, y2, *SIGNAL_LINE))


# --- shared line furniture --------------------------------------------------
def arrow(canvas, x: float, y: float, dx: float, dy: float,
          pen=PROCESS_LINE) -> None:
    """A solid flow arrowhead. A process line without one is ambiguous about
    the single thing the line exists to state."""
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag
    px, py = -uy * 1.15, ux * 1.15
    _v(canvas, poly([(x, y), (x - ux * 3.0 + px, y - uy * 3.0 + py),
                     (x - ux * 3.0 - px, y - uy * 3.0 - py)],
                    pen.layer, pen.width, "currentColor"))


def tag_text(canvas, cx: float, y: float, tag: str, lines: list) -> float:
    """The tag block under a symbol: the identity, then its resolved fields."""
    _v(canvas, Text(cx, y, tag, L_COMPONENT, T_TAG, "middle", bold=True))
    y += 3.0
    for ln in lines:
        _v(canvas, Text(cx, y, ln, L_COMPONENT, T_TINY, "middle"))
        y += 2.6
    return y


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float,
         a1: float, steps: int = 10) -> list:
    """A polyline arc. Deliberately NOT an SVG arc command: the DXF and PDF
    exporters consume coordinates, so an `A` path would render on screen and
    vanish from both — the same drift `primitives.hatch` avoids."""
    out = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out
