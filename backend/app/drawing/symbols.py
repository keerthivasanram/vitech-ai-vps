"""Per-category component glyphs for the GA views.

THE RULE THAT SHAPES THIS FILE. The equipment ENVELOPE is dimensioned because
its millimetres come from the spec engine. Component *positions* mostly do not
exist as engineered numbers yet — Vitech has not supplied setting-out rules — so
they are drawn as SCHEMATIC INDICATIONS: proportional, balloon-labelled, and
never given a dimension line. Golden rule #2 is about numbers presented as fact;
an undimensioned schematic symbol asserts "a filter bank sits at the rear", not
"it sits at 1,240 mm". The sheet carries an explicit note saying exactly that.

What IS real here is the component SET and its COUNTS — those come from the
resolved spec (e.g. 9 dry filters, 1 exhaust blower CLP-4-15-14500), so the
drawing shows the right number of the right things.

CLIENT-EXTENSION POINT: `SYMBOLS[category]` — add a category's glyph function
and the sheet/views/title-block/export plumbing is inherited unchanged. When the
client supplies setting-out rules, a glyph can graduate to dimensioned geometry.
"""
import re
from typing import Callable, Optional

from .primitives import (DASH_HIDDEN, LW_MED, LW_THIN, L_COMPONENT, L_HIDDEN,
                         L_TEXT, Circle, Line, Path, Rect, Text)

BALLOON_R = 3.2


def balloon(canvas, x: float, y: float, tag: str) -> None:
    """A numbered/lettered item balloon, as on a real GA."""
    canvas.add(Circle(x, y, BALLOON_R, L_COMPONENT, LW_THIN),
               Text(x, y + 1.0, tag, L_COMPONENT, 2.3, "middle"))


def _int(value, default: int = 0) -> int:
    """First integer inside a spec value like '9 (dry)' or '2 sets/booth'."""
    m = re.search(r"\d+", str(value or ""))
    return int(m.group()) if m else default


def _nos(value, default: int = 0) -> int:
    """A COUNT, only when the value actually states one ('4 nos', '2 sets').

    Needed because a descriptive spec value carries numbers that are not
    quantities: "flame proof LED 700-800 LUX" would otherwise be read as 700
    luminaires. Anything without an explicit nos/set marker returns `default`,
    so the drawing omits the symbol rather than inventing a count.
    """
    m = re.search(r"(\d+)\s*(?:nos?\b|no's|sets?\b)", str(value or ""), re.I)
    return int(m.group(1)) if m else default


def _find(rows, *needles) -> Optional[str]:
    """Value of the first spec row whose label contains all the needles."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if all(nd in label for nd in needles):
            return r.get("value")
    return None


# --------------------------------------------------------------------------
def paint_booth(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Paint booth GA: filter bank, door leaves, lighting, exhaust blower.

    Returns the legend as (tag, description) pairs.
    """
    legend: list[tuple[str, str]] = []
    filters = _int(_find(rows, "filters"), 0)
    blower = _find(rows, "exhaust blower") or ""
    blower_qty = _nos(_find(rows, "blower", "nos"), 0) or _int(_find(rows, "blower", "nos"), 1)
    lights = _nos(_find(rows, "illumination"), 0)

    front = views.get("front")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Door opening: a double-leaf sliding door across the working face.
        dw = w * 0.44
        dx = x + (w - dw) / 2
        dh = h * 0.72
        dy = y + h - dh
        canvas.add(Rect(dx, dy, dw, dh, L_COMPONENT, LW_MED))
        canvas.add(Line(dx + dw / 2, dy, dx + dw / 2, dy + dh, L_COMPONENT, LW_THIN))
        # Sliding direction arrows.
        my = dy + dh / 2
        canvas.add(Line(dx + dw * 0.18, my, dx + dw * 0.40, my, L_COMPONENT, LW_THIN),
                   Line(dx + dw * 0.60, my, dx + dw * 0.82, my, L_COMPONENT, LW_THIN))
        balloon(canvas, dx + dw / 2, dy - 5.0, "1")
        legend.append(("1", "Manual sliding door, double leaf"))

        # View panels either side of the door.
        for sx in (x + w * 0.10, x + w * 0.78):
            canvas.add(Rect(sx, y + h * 0.22, w * 0.12, h * 0.20, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.16, y + h * 0.16, "2")
        legend.append(("2", "View glass panel"))

        if lights:
            for i in range(min(lights, 6)):
                lx = x + w * (0.14 + 0.72 * (i / max(1, min(lights, 6) - 1)))
                canvas.add(Rect(lx - w * 0.035, y + h * 0.06, w * 0.07, h * 0.04,
                                L_COMPONENT, LW_THIN))
            balloon(canvas, x + w * 0.5, y + h * 0.02, "3")
            legend.append(("3", f"Flame-proof LED luminaire ({lights} nos)"))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        # Filter bank across the rear wall, drawn with the real filter count.
        bank_d = h * 0.14
        by = y + h - bank_d
        canvas.add(Rect(x, by, w, bank_d, L_COMPONENT, LW_MED))
        if filters:
            for i in range(1, min(filters, 12)):
                fx = x + w * i / min(filters, 12)
                canvas.add(Line(fx, by, fx, by + bank_d, L_COMPONENT, LW_THIN))
            # Offset from centre: the blower symbol occupies the middle of the
            # extract end, so a centred balloon would sit on top of it.
            balloon(canvas, x + w * 0.16, by - 5.0, "4")
            legend.append(("4", f"Paint arresting filter bank ({filters} nos)"))

        # Exhaust blower on the extract centre line, drawn INSIDE the envelope
        # just ahead of the filter bank. Keeping it within the footprint leaves
        # the area below the view clear for the dimension line and caption —
        # a symbol overhanging the outline collides with both.
        bw = w * 0.16
        bh = bank_d * 1.4
        bx = x + (w - bw) / 2
        byy = by - bh - 2.0
        canvas.add(Rect(bx, byy, bw, bh, L_COMPONENT, LW_MED))
        canvas.add(Circle(bx + bw / 2, byy + bh / 2, min(bw, bh) * 0.32,
                          L_COMPONENT, LW_THIN))
        balloon(canvas, bx + bw + 6.0, byy + bh / 2, "5")
        legend.append(("5", f"Exhaust blower {blower} ({blower_qty} no)".replace("  ", " ")))

        # Air-inlet side (opposite the extract) shown as hidden detail.
        canvas.add(Line(x, y + h * 0.10, x + w, y + h * 0.10, L_HIDDEN, LW_THIN, DASH_HIDDEN))
        canvas.add(Text(x + w * 0.5, y + h * 0.075, "AIR INLET FILTER SIDE",
                        L_TEXT, 2.1, "middle"))
    return legend


# --------------------------------------------------------------------------
def wet_scrubber(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Wet scrubber GA: spray tower, recirculation tank, demister, blower."""
    legend: list[tuple[str, str]] = []
    nozzles = _int(_find(rows, "spray", "nozzle"), 0)
    pump = _find(rows, "pump", "capacity") or ""
    tank = _find(rows, "tank", "capacity") or ""

    front = views.get("front")
    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Recirculation tank occupies the lower portion of the envelope.
        tank_h = h * 0.26
        ty = y + h - tank_h
        canvas.add(Rect(x, ty, w, tank_h, L_COMPONENT, LW_MED))
        canvas.add(Line(x, ty + tank_h * 0.45, x + w, ty + tank_h * 0.45,
                        L_COMPONENT, LW_THIN, DASH_HIDDEN))
        balloon(canvas, x + w * 0.14, ty + tank_h * 0.72, "1")
        legend.append(("1", f"Recirculation tank {tank}".strip()))

        # Spray headers inside the tower.
        for i in range(3):
            sy = y + h * (0.30 + 0.14 * i)
            canvas.add(Line(x + w * 0.12, sy, x + w * 0.88, sy, L_COMPONENT, LW_THIN))
            for j in range(4):
                nx = x + w * (0.20 + 0.20 * j)
                canvas.add(Path(f"M{nx:.2f},{sy:.2f} l-1.4,2.6 l2.8,0 Z",
                                L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.90, y + h * 0.37, "2")
        legend.append(("2", f"Spray nozzle header ({nozzles} nozzles)" if nozzles
                       else "Spray nozzle header"))

        # Demister pad near the top.
        dy = y + h * 0.16
        canvas.add(Rect(x + w * 0.10, dy, w * 0.80, h * 0.07, L_COMPONENT, LW_MED))
        for i in range(1, 8):
            hx = x + w * (0.10 + 0.80 * i / 8)
            canvas.add(Line(hx, dy, hx - h * 0.03, dy + h * 0.07, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.5, dy - 6.5, "3")
        legend.append(("3", "Demister / eliminator pad"))

        # Circulation pump beside the tank, on the LEFT: the height dimension
        # runs down the right-hand side, so a pump drawn there collides with it.
        pr = min(w, h) * 0.05
        pcx = x - pr - 5.0
        canvas.add(Circle(pcx, ty + tank_h * 0.5, pr, L_COMPONENT, LW_MED))
        balloon(canvas, pcx, ty - 5.0, "4")
        legend.append(("4", f"Circulation pump {pump}".strip()))
    return legend


# --------------------------------------------------------------------------
def generic(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Fallback: envelope only. Honest for a category with no glyph yet — the
    sheet still carries real dimensions and the full TBD schedule."""
    return []


SYMBOLS: dict[str, Callable] = {
    "paint_booth": paint_booth,
    "wet_scrubber": wet_scrubber,
}


def draw_components(canvas, category: str, views: dict, rows: list) -> list[tuple[str, str]]:
    """Draw the category's component glyphs; returns the legend rows."""
    return SYMBOLS.get(category, generic)(canvas, views, rows)
