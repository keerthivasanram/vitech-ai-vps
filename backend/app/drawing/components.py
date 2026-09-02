"""Reusable industrial equipment symbols, built from drawing primitives.

WHY THIS MODULE EXISTS. Every glyph in `symbols.py` drew its own components
inline, so a blower was a rectangle with a circle in it on a paint booth and a
different rectangle with a circle in it on a dust collector. Nothing was shared,
nothing was recognisable as a blower, and improving one improved only one.

These are the drafting VOCABULARY: a filter bank, a blower, a duct, a motor, an
access door, a plenum. An equipment renderer composes them, exactly as a
draughtsman reuses a standard detail, and a change here reaches every category
at once.

TWO RULES HOLD THROUGHOUT.

  * **Deterministic.** No randomness, no measurement of rendered text, no
    dependence on anything but the arguments. The same call always emits the
    same geometry, because the whole drawing engine is covered by byte-level
    tests.
  * **Symbolic, not fabricated.** These draw what a component IS, at the size
    the caller gives them. They never decide where a component GOES — that
    stays with the equipment renderer, and where the client has supplied no
    setting-out rules the sheet says the arrangement is indicative. A
    recognisable blower symbol is presentation; a blower at an invented
    position would be engineering nobody approved.

Style comes from `style.py` — a component names the ROLE of each line, never a
width, so the house drafting standard stays in one place.
"""
import math

from .primitives import Circle, Line, Rect, Text, hatch, poly
from .style import (DUCT, EQUIPMENT, HATCH_LINE, INTERNAL_DETAIL,
                    PANEL_SEAM, SECONDARY_OUTLINE, SYMBOL_DETAIL, T_TINY,
                    CENTRE_LINE, L_TEXT)


# --------------------------------------------------------------------------
# Filtration
# --------------------------------------------------------------------------
def filter_bank(canvas, x: float, y: float, w: float, h: float,
                count: int, across: bool = False, pleated: bool = True) -> None:
    """A filter bank: frame, cell divisions, and media.

    `across=False` stacks cells up the bank (a vertical face); `across=True`
    ranks them along it (a bank seen in plan). `pleated` draws the zig-zag that
    makes a filter READ as a filter — a plain rectangle reads as glazing, and a
    45-degree hatch reads as solid material. Falls back to hatch on a bank too
    small for the zig-zag to survive.
    """
    canvas.add(Rect(x, y, w, h, *SECONDARY_OUTLINE))
    cells = max(1, min(int(count or 1), 12))
    for i in range(1, cells):
        if across:
            cx = x + w * i / cells
            canvas.add(Line(cx, y, cx, y + h, *PANEL_SEAM))
        else:
            cy = y + h * i / cells
            canvas.add(Line(x, cy, x + w, cy, *PANEL_SEAM))

    depth = w if across else h
    span = h if across else w
    if not pleated or depth / cells < 1.2 or span < 2.0:
        canvas.add(hatch(x, y, w, h, spacing=1.6, layer=HATCH_LINE.layer,
                         width=HATCH_LINE.width))
        return

    # Pleats run ACROSS the airflow, so they follow the cell divisions.
    for i in range(cells):
        if across:
            c0 = x + w * i / cells
            c1 = x + w * (i + 1) / cells
            _pleat(canvas, c0, y, c1 - c0, h, vertical=False)
        else:
            c0 = y + h * i / cells
            c1 = y + h * (i + 1) / cells
            _pleat(canvas, x, c0, w, c1 - c0, vertical=True)


def _pleat(canvas, x: float, y: float, w: float, h: float, vertical: bool,
           folds: int = 4) -> None:
    """The zig-zag of one filter cell's media."""
    pts = []
    if vertical:
        for i in range(folds * 2 + 1):
            t = i / (folds * 2)
            pts.append((x + (w if i % 2 else 0), y + h * t))
    else:
        for i in range(folds * 2 + 1):
            t = i / (folds * 2)
            pts.append((x + w * t, y + (h if i % 2 else 0)))
    canvas.add(poly(pts, SYMBOL_DETAIL.layer, HATCH_LINE.width, closed=False))


# --------------------------------------------------------------------------
# Air moving
# --------------------------------------------------------------------------
def blower(canvas, cx: float, cy: float, r: float, discharge: str = "up",
           motor: bool = True) -> tuple:
    """A centrifugal blower: volute, impeller, discharge and drive motor.

    Returns the discharge connection point, so a duct can be drawn to the
    machine rather than near it. The old symbol was a rectangle with a circle
    inside — true of a blower, and equally true of a tank, a pump or a fan. A
    scroll with a tangential discharge is what makes it read as a BLOWER at a
    glance, which is the whole job of a symbol on a GA.
    """
    # Volute: a circle opened out into the discharge throat.
    canvas.add(Circle(cx, cy, r, EQUIPMENT.layer, EQUIPMENT.width))
    canvas.add(Circle(cx, cy, r * 0.34, INTERNAL_DETAIL.layer,
                      INTERNAL_DETAIL.width))          # impeller eye / inlet

    tw = r * 0.72                                       # throat width
    if discharge == "up":
        x0, y0 = cx - tw / 2, cy - r * 1.55
        canvas.add(Rect(x0, y0, tw, r * 0.62, *DUCT))
        port = (cx, y0)
    elif discharge == "down":
        y0 = cy + r * 0.93
        canvas.add(Rect(cx - tw / 2, y0, tw, r * 0.62, *DUCT))
        port = (cx, y0 + r * 0.62)
    elif discharge == "left":
        x0 = cx - r * 1.55
        canvas.add(Rect(x0, cy - tw / 2, r * 0.62, tw, *DUCT))
        port = (x0, cy)
    else:                                               # right
        x0 = cx + r * 0.93
        canvas.add(Rect(x0, cy - tw / 2, r * 0.62, tw, *DUCT))
        port = (x0 + r * 0.62, cy)

    if motor:
        mw, mh = r * 0.85, r * 0.62
        if discharge in ("up", "down"):
            motor_box(canvas, cx + r * 1.05, cy - mh / 2, mw, mh)
            canvas.add(Line(cx + r, cy, cx + r * 1.05, cy, *SYMBOL_DETAIL))
        else:
            motor_box(canvas, cx - mw / 2, cy + r * 1.05, mw, mh)
            canvas.add(Line(cx, cy + r, cx, cy + r * 1.05, *SYMBOL_DETAIL))
    return port


def motor_box(canvas, x: float, y: float, w: float, h: float) -> None:
    """A drive motor: body, terminal box and shaft end."""
    canvas.add(Rect(x, y, w, h, *EQUIPMENT))
    canvas.add(Rect(x + w * 0.30, y - h * 0.22, w * 0.34, h * 0.22,
                    *SYMBOL_DETAIL))                    # terminal box
    canvas.add(Line(x, y + h * 0.5, x - w * 0.14, y + h * 0.5, *SYMBOL_DETAIL))


# --------------------------------------------------------------------------
# Ducting
# --------------------------------------------------------------------------
def duct_run(canvas, x1: float, y1: float, x2: float, y2: float,
             bore: float, centre: bool = True) -> None:
    """A duct as two parallel walls about a centre line.

    A circular duct in elevation is its two walls and its axis — drawn as a
    single rectangle it is indistinguishable from a beam or a panel.
    """
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6 or bore <= 0:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy * bore / 2.0, ux * bore / 2.0
    canvas.add(Line(x1 + px, y1 + py, x2 + px, y2 + py, *DUCT),
               Line(x1 - px, y1 - py, x2 - px, y2 - py, *DUCT))
    if centre:
        canvas.add(Line(x1, y1, x2, y2, *CENTRE_LINE))


def flange(canvas, x: float, y: float, bore: float, vertical: bool = True) -> None:
    """A bolted duct connection, drawn as the pair of raised faces."""
    t = max(bore * 0.10, 0.6)
    if vertical:
        canvas.add(Line(x - bore * 0.62, y, x + bore * 0.62, y, *SECONDARY_OUTLINE),
                   Line(x - bore * 0.62, y + t, x + bore * 0.62, y + t, *SECONDARY_OUTLINE))
    else:
        canvas.add(Line(x, y - bore * 0.62, x, y + bore * 0.62, *SECONDARY_OUTLINE),
                   Line(x + t, y - bore * 0.62, x + t, y + bore * 0.62, *SECONDARY_OUTLINE))


# --------------------------------------------------------------------------
# Enclosure furniture
# --------------------------------------------------------------------------
def access_door(canvas, x: float, y: float, w: float, h: float,
                leaves: int = 2, handle: bool = True) -> None:
    """A door opening with its leaves and hardware."""
    canvas.add(Rect(x, y, w, h, *DUCT))
    for i in range(1, leaves):
        lx = x + w * i / leaves
        canvas.add(Line(lx, y, lx, y + h, *PANEL_SEAM))
    if handle:
        my = y + h / 2
        for i in range(leaves):
            c = x + w * (i + 0.5) / leaves
            off = w / leaves * 0.18
            canvas.add(Line(c - off, my, c + off, my, *SYMBOL_DETAIL))


def plenum(canvas, x: float, y: float, w: float, h: float, label: str = "") -> None:
    """A plenum / distribution chamber, as hidden detail behind a face."""
    from .style import HIDDEN_LINE
    canvas.add(Rect(x, y, w, h, *HIDDEN_LINE))
    for i in range(1, 4):
        canvas.add(Line(x, y + h * i / 4, x + w, y + h * i / 4, *HIDDEN_LINE))
    if label:
        canvas.add(Text(x + w / 2, y - 1.4, label, L_TEXT, T_TINY, "middle"))


def structural_base(canvas, x: float, y: float, w: float, depth: float) -> None:
    """The base frame an enclosure stands on, with its bearing points."""
    canvas.add(Rect(x, y - depth, w, depth, *SECONDARY_OUTLINE))
    for i in range(4):
        fx = x + w * (0.06 + 0.293 * i)
        canvas.add(Line(fx, y - depth, fx, y, *SYMBOL_DETAIL))
