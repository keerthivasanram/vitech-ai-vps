"""Drafting DETAILING: the conventions that make a sheet read as a GA.

WHY THIS IS A THIRD MODULE, beside `style.py` and `components.py`. `style.py`
says how a line LOOKS (its role, weight, layer). `components.py` says what a
piece of EQUIPMENT looks like (a blower, a filter bank). Neither covers the
draughtsman's own vocabulary — section markers, break lines, level datums,
material hatching, detail bubbles. That vocabulary is what separates a
professional general arrangement from a software-generated sketch, and it
belongs to the DRAWING rather than to the machine.

THE TRACEABILITY RULE, unchanged and load-bearing. Nothing here may invent an
engineering value. A level marker prints a level only when the caller passes a
RESOLVED one; a section marker names a cut the glyph actually draws; material
hatching states what a spec row already says the material is. Where a detail is
conventional rather than engineered — the position of a lifting lug, the pitch
of a ladder rung — it is drawn as an INDICATIVE symbol and the sheet's standing
note already covers it. That is the same line the component glyphs draw.

Everything is deterministic and emitted as real line segments: the DXF and PDF
exporters consume coordinates, so a hatch that existed only as an SVG pattern
would render on screen and vanish from both.
"""
import math

from .primitives import Circle, Line, Rect, Text, hatch, poly
from .style import (BALLOON, CENTRE_LINE, DIMENSION_LINE, EQUIPMENT,
                    HATCH_LINE, HIDDEN_LINE, INTERNAL_DETAIL, LEADER_LINE,
                    L_TEXT, PANEL_SEAM, PRIMARY_OUTLINE, SECONDARY_OUTLINE,
                    SYMBOL_DETAIL, T_CAPTION, T_DIM, T_SMALL, T_TINY,
                    T_VIEW_TITLE)

# --------------------------------------------------------------------------
# Material hatching
# --------------------------------------------------------------------------
# A cut face is what makes a section read as a section, and DIFFERENT materials
# must be told apart by their hatch — that is the whole convention. These are
# the four this plant actually cuts through.
STEEL = "steel"
STEEL_ALT = "steel_alt"          # adjacent steel part, opposite slope
INSULATION = "insulation"
CONCRETE = "concrete"
LIQUID = "liquid"


def material_hatch(canvas, x: float, y: float, w: float, h: float,
                   material: str = STEEL) -> None:
    """Fill a cut region with the hatch convention for its material.

    Adjacent parts of the SAME material are distinguished by slope
    (`STEEL` / `STEEL_ALT`), which is exactly how a section drawing separates
    two plates that meet — not by changing the pattern, which would imply a
    different material.
    """
    if w <= 0 or h <= 0:
        return
    lay, wid = HATCH_LINE.layer, HATCH_LINE.width
    if material == STEEL:
        canvas.add(hatch(x, y, w, h, spacing=1.5, slope=1, layer=lay, width=wid))
    elif material == STEEL_ALT:
        canvas.add(hatch(x, y, w, h, spacing=1.5, slope=-1, layer=lay, width=wid))
    elif material == CONCRETE:
        # Coarse, both ways: the conventional "anything solid and cast" fill.
        canvas.add(hatch(x, y, w, h, spacing=2.6, slope=1, layer=lay, width=wid))
        canvas.add(hatch(x, y, w, h, spacing=5.2, slope=-1, layer=lay, width=wid))
    elif material == LIQUID:
        # Horizontal only — a liquid has a level, and the convention echoes it.
        n = max(1, int(h / 2.0))
        for i in range(1, n):
            ly = y + h * i / n
            canvas.add(Line(x, ly, x + w, ly, lay, wid))
    elif material == INSULATION:
        _insulation(canvas, x, y, w, h)


def _insulation(canvas, x: float, y: float, w: float, h: float) -> None:
    """Mineral-wool hatch: rows of soft zig-zag, the standard lagging symbol.

    Drawn as a polyline rather than a pattern for the exporter's sake, and the
    row pitch adapts to the band's depth so lagging on a 6 mm wall and on a
    60 mm one both read as lagging rather than as noise or as a solid.
    """
    if w <= 0 or h <= 0:
        return
    across = w >= h                      # zig-zag runs along the longer axis
    depth = h if across else w
    rows = max(1, min(4, int(depth / 1.6)))
    step = depth / rows
    for r in range(rows):
        base = (y if across else x) + step * (r + 0.5)
        run = w if across else h
        teeth = max(3, min(40, int(run / (step * 1.15)) or 3))
        pts = []
        for i in range(teeth * 2 + 1):
            t = i / (teeth * 2)
            off = (step * 0.34) * (1 if i % 2 else -1)
            if across:
                pts.append((x + run * t, base + off))
            else:
                pts.append((base + off, y + run * t))
        canvas.add(poly(pts, HATCH_LINE.layer, HATCH_LINE.width, closed=False))


def cut_wall(canvas, x: float, y: float, w: float, h: float,
             material: str = STEEL, outline: bool = True) -> None:
    """A wall/plate CUT by the view: heavy outline plus its material hatch.

    A cut edge is the heaviest line on a drawing — that is how a reader knows
    the view passes through the material rather than looking at it. Drawing the
    cut at component weight is the commonest way a section stops reading as one.
    """
    if outline:
        canvas.add(Rect(x, y, w, h, *PRIMARY_OUTLINE))
    material_hatch(canvas, x, y, w, h, material)


# --------------------------------------------------------------------------
# Section and detail references
# --------------------------------------------------------------------------
def section_marker(canvas, x1: float, y1: float, x2: float, y2: float,
                   tag: str = "A", flip: bool = False) -> None:
    """The cutting-plane line and its viewing arrows, labelled at both ends.

    Only ever drawn for a section the sheet ACTUALLY carries. A section mark
    pointing at a view that does not exist is worse than no mark: it tells the
    reader a drawing is missing.
    """
    canvas.add(Line(x1, y1, x2, y2, *CENTRE_LINE))
    dx, dy = x2 - x1, y2 - y1
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag
    px, py = (-uy, ux) if not flip else (uy, -ux)   # viewing direction

    # THE LABELS SIT INWARD OF EACH END, not beyond it. Drawn outboard, the
    # far-end letter landed on the view's overall dimension — the dimension lane
    # is exactly where a cutting plane wants to stick out, on every view. Moving
    # the letter in along its own cutting line keeps the mark unambiguous and
    # cannot collide with the lane, whatever the view's size.
    for (ex, ey), inward in (((x1, y1), 1.0), ((x2, y2), -1.0)):
        # Heavy stub at each end: the cutting plane is a thick line where it
        # turns, which is what distinguishes it from an ordinary centre line.
        canvas.add(Line(ex - ux * 4.0 * inward, ey - uy * 4.0 * inward, ex, ey,
                        *PRIMARY_OUTLINE))
        ax, ay = ex + px * 4.4, ey + py * 4.4
        canvas.add(Line(ex, ey, ax, ay, *PRIMARY_OUTLINE))
        canvas.add(poly([(ax + px * 1.8, ay + py * 1.8),
                         (ax - ux * 1.3 + px * 0.2, ay - uy * 1.3 + py * 0.2),
                         (ax + ux * 1.3 + px * 0.2, ay + uy * 1.3 + py * 0.2)],
                        PRIMARY_OUTLINE.layer, PRIMARY_OUTLINE.width,
                        "currentColor"))
        canvas.add(Text(ex + ux * 3.4 * inward - px * 4.2,
                        ey + uy * 3.4 * inward - py * 4.2 + 1.0, tag,
                        L_TEXT, T_VIEW_TITLE, "middle", bold=True))


def detail_bubble(canvas, cx: float, cy: float, r: float, tag: str,
                  label_at: tuple = None) -> None:
    """Ring a region and name it, for a detail drawn elsewhere on the sheet."""
    canvas.add(Circle(cx, cy, r, CENTRE_LINE.layer, CENTRE_LINE.width))
    lx, ly = label_at or (cx + r * 0.72, cy - r * 0.72)
    canvas.add(Line(cx + r * 0.7, cy - r * 0.7, lx + 3.0, ly - 3.0, *LEADER_LINE))
    canvas.add(Text(lx + 4.0, ly - 3.4, f"DETAIL {tag}", L_TEXT, T_CAPTION,
                    "start", bold=True))


def break_line(canvas, x1: float, y1: float, x2: float, y2: float,
               amp: float = 1.8) -> None:
    """A conventional break: this run continues, and is not drawn to length.

    THIS IS AN HONESTY DEVICE, not decoration. A conveyor whose stated length is
    60 m cannot be drawn to scale beside a 3 m machine; without a break symbol
    the reader takes the drawn length as the real one. With it, the drawing says
    "shortened" in the standard way.
    """
    dx, dy = x2 - x1, y2 - y1
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag
    px, py = -uy, ux
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    pts = [(x1, y1)]
    for i, side in enumerate((1, -1, 1, -1)):
        t = (i - 1.5) * (mag * 0.09)
        pts.append((mx + ux * t + px * amp * side, my + uy * t + py * amp * side))
    pts.append((x2, y2))
    canvas.add(poly(pts, SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width, closed=False))


# --------------------------------------------------------------------------
# Levels and datums
# --------------------------------------------------------------------------
def level_marker(canvas, x: float, y: float, text: str,
                 anchor: str = "start") -> None:
    """The filled datum triangle and its level, e.g. FFL 0.000 / +4.000.

    ONLY called with a level the engineering resolved — the floor line, or a
    height the envelope states. It is the clearest way a reader takes a real
    vertical dimension off an industrial elevation, and it costs no new
    assumption because both those levels already exist on the sheet.
    """
    s = 1.5
    canvas.add(poly([(x, y), (x - s, y - s * 1.5), (x + s, y - s * 1.5)],
                    PRIMARY_OUTLINE.layer, DIMENSION_LINE.width, "currentColor"))
    canvas.add(Line(x - s * 2.4, y - s * 1.5, x + s * 2.4, y - s * 1.5,
                    *DIMENSION_LINE))
    tx = x + s * 3.0 if anchor == "start" else x - s * 3.0
    canvas.add(Text(tx, y - s * 2.2, text, L_TEXT, T_DIM, anchor))


# --------------------------------------------------------------------------
# Structural and handling detail
# --------------------------------------------------------------------------
def base_plate(canvas, cx: float, y: float, w: float, t: float,
               bolts: int = 2) -> None:
    """A column base plate with its holding-down bolts, seen in elevation."""
    canvas.add(Rect(cx - w / 2, y, w, t, *SECONDARY_OUTLINE))
    for i in range(bolts):
        bx = cx - w / 2 + w * (i + 0.5) / bolts
        canvas.add(Line(bx, y - t * 0.8, bx, y + t, *SYMBOL_DETAIL))


def lifting_lug(canvas, cx: float, y: float, size: float) -> None:
    """A lifting lug on the roof line: plate with an eye."""
    canvas.add(poly([(cx - size, y), (cx - size * 0.5, y - size * 1.2),
                     (cx + size * 0.5, y - size * 1.2), (cx + size, y)],
                    SECONDARY_OUTLINE.layer, SECONDARY_OUTLINE.width))
    canvas.add(Circle(cx, y - size * 0.72, size * 0.30,
                      INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))


def ladder(canvas, x: float, y_top: float, y_bot: float, w: float) -> None:
    """A caged access ladder, drawn as stiles and rungs at an even pitch.

    The pitch is a DRAWING convention, not a set-out: it is chosen so the ladder
    reads as a ladder at sheet scale, and the sheet's standing note already says
    component positions are indicative.
    """
    if y_bot <= y_top or w <= 0:
        return
    canvas.add(Line(x, y_top, x, y_bot, *SYMBOL_DETAIL),
               Line(x + w, y_top, x + w, y_bot, *SYMBOL_DETAIL))
    rungs = max(2, min(24, int((y_bot - y_top) / max(w * 0.9, 1.2))))
    for i in range(1, rungs):
        ry = y_top + (y_bot - y_top) * i / rungs
        canvas.add(Line(x, ry, x + w, ry, *HATCH_LINE))


def platform(canvas, x: float, y: float, w: float, handrail_h: float) -> None:
    """A maintenance platform: deck, handrail, mid-rail and toe board."""
    canvas.add(Line(x, y, x + w, y, *SECONDARY_OUTLINE))
    canvas.add(Line(x, y - handrail_h, x + w, y - handrail_h, *SYMBOL_DETAIL),
               Line(x, y - handrail_h * 0.5, x + w, y - handrail_h * 0.5,
                    *HATCH_LINE))
    for px_ in (x, x + w):
        canvas.add(Line(px_, y, px_, y - handrail_h, *SYMBOL_DETAIL))


def nozzle(canvas, x: float, y: float, bore: float, length: float,
           direction: str = "right") -> tuple:
    """A flanged branch off a vessel. Returns the flange face centre point."""
    dx, dy = {"right": (1, 0), "left": (-1, 0),
              "up": (0, -1), "down": (0, 1)}.get(direction, (1, 0))
    x2, y2 = x + dx * length, y + dy * length
    if dx:
        canvas.add(Rect(min(x, x2), y - bore / 2, length, bore, *SECONDARY_OUTLINE))
        canvas.add(Line(x2, y2 - bore * 0.75, x2, y2 + bore * 0.75, *EQUIPMENT))
    else:
        canvas.add(Rect(x - bore / 2, min(y, y2), bore, length, *SECONDARY_OUTLINE))
        canvas.add(Line(x2 - bore * 0.75, y2, x2 + bore * 0.75, y2, *EQUIPMENT))
    return (x2, y2)


def stiffener(canvas, x: float, y: float, h: float, count: int,
              pitch: float) -> None:
    """External stiffening ribs down a casing — vertical members at a pitch."""
    for i in range(max(0, count)):
        sx = x + pitch * i
        canvas.add(Line(sx, y, sx, y + h, *PANEL_SEAM))
