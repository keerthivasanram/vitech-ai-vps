"""The PRELIMINARY schematic: what a sheet shows when no size is engineered yet.

WHY THIS IS NOT A GOLDEN-RULE-#2 VIOLATION, which is the first question anyone
should ask of a module that draws a box nobody dimensioned.

A dimensioned view ASSERTS a size: the outline is to scale, the dimension says
what it is, and a fabricator can work from it. This module asserts nothing of
the kind. Every axis is labelled TBD rather than a number, the sheet prints NTS
instead of a ratio, the title block reads PRELIMINARY, and the drawing carries
"NOT FOR FABRICATION" across it. What is left is a picture of the KIND of
machine — which is information the engineering genuinely has, because the
category was resolved — and nothing about its size.

The alternative it replaces was an empty sheet reading "NO DIMENSIONED VIEWS".
That was equally honest and strictly less useful: it told the reader nothing
about the equipment, nothing about why, and nothing about what to send back.

PROPORTIONS ARE NOMINAL AND DELIBERATELY NEUTRAL. The boxes are drawn on a
fixed 3:2:2 arrangement that is not read from, and never written to, any
engineering value — it exists only so the three views sit where a third-angle
reader expects them. Because `model_w` / `model_h` are None on these views,
every glyph routine that needs real millimetres (panel pitch, bay dimensions)
disables itself automatically, which is what keeps a schematic free of geometry
that would imply a size.
"""
from .primitives import Line, Rect, Text
from .style import (CENTRE_LINE, DIM_LANE_OVERALL, HIDDEN_LINE, L_TEXT,
                    PRIMARY_OUTLINE, T_BODY, T_CAPTION, T_DIM, T_SECTION,
                    T_VIEW_TITLE)
from .views import LABEL_DROP, VIEW_GAP, View

# Nominal box proportions for the three views. NOT a size and never derived
# from one — purely the arrangement a third-angle reader expects to find.
_NOM_L, _NOM_W, _NOM_H = 3.0, 2.0, 2.0

TBD_TEXT = "TBD"


def _tbd_dim(canvas, x1: float, y1: float, x2: float, y2: float,
             vertical: bool = False) -> None:
    """A dimension line whose value is openly TBD.

    Drawn WITHOUT arrow terminators and with an open gap, so it cannot be
    mistaken at a glance for a real dimension carrying a number. The witness
    lines are still shown, because the reader needs to see WHICH extent is
    unresolved.
    """
    off = DIM_LANE_OVERALL
    if vertical:
        dx = x1 + off
        canvas.add(Line(x1 + 1.5, y1, dx, y1, *HIDDEN_LINE),
                   Line(x1 + 1.5, y2, dx, y2, *HIDDEN_LINE),
                   Line(dx, y1, dx, y1 + (y2 - y1) * 0.36, *HIDDEN_LINE),
                   Line(dx, y2 - (y2 - y1) * 0.36, dx, y2, *HIDDEN_LINE))
        canvas.add(Text(dx, (y1 + y2) / 2 + 1.0, TBD_TEXT, L_TEXT, T_DIM,
                        "middle", rotate=-90))
    else:
        dy = y1 + off
        canvas.add(Line(x1, y1 + 1.5, x1, dy, *HIDDEN_LINE),
                   Line(x2, y1 + 1.5, x2, dy, *HIDDEN_LINE),
                   Line(x1, dy, x1 + (x2 - x1) * 0.36, dy, *HIDDEN_LINE),
                   Line(x2 - (x2 - x1) * 0.36, dy, x2, dy, *HIDDEN_LINE))
        canvas.add(Text((x1 + x2) / 2, dy - 1.6, TBD_TEXT, L_TEXT, T_DIM,
                        "middle"))


def _box(canvas, x: float, y: float, w: float, h: float, label: str,
         axis_w: str, axis_h: str) -> None:
    """One nominal view: outline, centre lines, TBD dimensions, caption."""
    canvas.add(Rect(x, y, w, h, *PRIMARY_OUTLINE))
    cx, cy = x + w / 2, y + h / 2
    canvas.add(Line(x - 4, cy, x + w + 4, cy, *CENTRE_LINE),
               Line(cx, y - 4, cx, y + h + 4, *CENTRE_LINE))

    _tbd_dim(canvas, x, y + h, x + w, y + h)
    _tbd_dim(canvas, x + w, y, x + w, y + h, vertical=True)

    # Name the axis each TBD belongs to. On a sheet with three unresolved
    # extents, a bare "TBD" beside a box does not say WHICH one is unknown.
    canvas.add(Text(cx, y + h + DIM_LANE_OVERALL + 3.4,
                    f"OVERALL {axis_w.upper()} - TBD", L_TEXT, T_CAPTION, "middle"))
    canvas.add(Text(x + w + DIM_LANE_OVERALL + 3.6, cy,
                    f"OVERALL {axis_h.upper()} - TBD", L_TEXT, T_CAPTION,
                    "middle", rotate=-90))

    ty = y + h + LABEL_DROP + 12.0
    canvas.add(Text(cx, ty, label, L_TEXT, T_VIEW_TITLE, "middle", bold=True))
    half = max(len(label) * T_VIEW_TITLE * 0.30, w * 0.18)
    canvas.add(Line(cx - half, ty + 1.6, cx + half, ty + 1.6, *CENTRE_LINE))


# Fraction of the drawing area the nominal views may occupy. The remainder is
# reserved for the COMPLETE schedule of missing inputs, because on a sheet with
# no dimensions that schedule is the actual content — it is what the reader has
# to act on to get a real GA.
VIEW_BAND = 0.62


def layout(ox: float, oy: float, avail_w: float, avail_h: float) -> list[View]:
    """Nominal third-angle placement, returned as ordinary `View`s.

    `model_w` / `model_h` are None BY DESIGN. Every glyph that needs true
    millimetres already guards on them, so a schematic inherits "draw the
    symbol, not the setting-out" without any glyph knowing about this module.
    """
    # Fit the nominal block into the drawing area with a margin, so the sheet
    # looks composed rather than stretched to the frame.
    span_x = _NOM_L + _NOM_W
    span_y = _NOM_H + _NOM_W
    band_h = avail_h * VIEW_BAND
    unit = min((avail_w - VIEW_GAP - 26.0) / span_x,
               (band_h - VIEW_GAP - LABEL_DROP * 2 - 30.0) / span_y)
    unit = max(unit, 6.0)

    sL, sW, sH = _NOM_L * unit, _NOM_W * unit, _NOM_H * unit
    block_w = sL + VIEW_GAP + sW
    block_h = sW + VIEW_GAP + sH
    x0 = ox + max(0.0, (avail_w - block_w) / 2)
    y0 = oy + 22.0 + max(0.0, (band_h - block_h - LABEL_DROP * 2 - 22.0) / 2)

    return [
        View("plan", "PLAN", x0, y0, sL, sW, None, None, "length", "width"),
        View("front", "FRONT ELEVATION", x0, y0 + sW + VIEW_GAP + LABEL_DROP,
             sL, sH, None, None, "length", "height"),
        View("side", "SIDE ELEVATION", x0 + sL + VIEW_GAP,
             y0 + sW + VIEW_GAP + LABEL_DROP, sW, sH, None, None,
             "width", "height"),
    ]


def draw(canvas, placed: list, ax: float, ay: float, aw: float, ah: float) -> None:
    """Draw the nominal views and the banner that governs how they are read."""
    axis_names = {"plan": ("length", "width"),
                  "front": ("length", "height"),
                  "side": ("width", "height")}
    for v in placed:
        w_axis, h_axis = axis_names.get(v.key, (v.w_axis, v.h_axis))
        _box(canvas, v.x, v.y, v.w, v.h, v.label, w_axis, h_axis)

    # THE BANNER IS RESERVED FIRST, at the top of the drawing area, because it
    # is the statement that makes everything below it safe to show. The same
    # reasoning as the standing notes on a crowded sheet: if it can be pushed
    # off, it is the one thing that must not be.
    canvas.add(Text(ax + aw / 2, ay + 5.0,
                    "PRELIMINARY SCHEMATIC - NOT FOR FABRICATION",
                    L_TEXT, T_SECTION, "middle", bold=True))
    canvas.add(Text(ax + aw / 2, ay + 10.4,
                    "DIMENSIONS PENDING ENGINEERING / CLIENT CONFIRMATION",
                    L_TEXT, T_BODY, "middle"))
    canvas.add(Text(ax + aw / 2, ay + 15.0,
                    "Arrangement indicative - drawn to NO SCALE",
                    L_TEXT, T_CAPTION, "middle"))
