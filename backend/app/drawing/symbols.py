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
import math
import re
from typing import Callable, Optional

from .primitives import (DASH_CENTRE, DASH_HIDDEN, LW_MED, LW_THIN, L_COMPONENT,
                         L_HIDDEN, L_TEXT, Circle, Line, Rect, Text, poly)

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
                canvas.add(poly([(nx, sy), (nx - 1.4, sy + 2.6), (nx + 1.4, sy + 2.6)],
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
def hot_air_oven(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Hot air oven GA: insulated chamber lining, door, heater bank,
    circulation blower, heating zones and the conveyor opening."""
    legend: list[tuple[str, str]] = []
    insulation = _find(rows, "insulation") or ""
    heating = _find(rows, "heating source") or _find(rows, "heating mode") or ""
    blower_hp = _find(rows, "circulation blower", "hp") or _find(rows, "circulation fan", "hp") or ""
    blower_qty = _nos(_find(rows, "circulation blower", "nos"), 0)
    zones = _int(_find(rows, "zones"), 0)
    conveyor = _find(rows, "conveyor") or ""

    front = views.get("front")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Insulated lining, drawn as an inner outline. The panel build-up is a
        # schematic thickness — the client has given no wall section — so it is
        # never dimensioned, only labelled with the insulation the spec states.
        t = min(w, h) * 0.05
        canvas.add(Rect(x + t, y + t, w - 2 * t, h - 2 * t, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.07, y + h * 0.20, "1")
        legend.append(("1", f"Insulated panel lining {insulation}".strip()))

        # Full-height double-leaf door on the loading face.
        dw = w * 0.30
        dx = x + w * 0.60
        dy = y + t
        dh = h - 2 * t
        canvas.add(Rect(dx, dy, dw, dh, L_COMPONENT, LW_MED))
        canvas.add(Line(dx + dw / 2, dy, dx + dw / 2, dy + dh, L_COMPONENT, LW_THIN))
        # Hinge ticks on both stiles.
        for hx in (dx, dx + dw):
            for f in (0.25, 0.75):
                canvas.add(Line(hx - 1.2, dy + dh * f, hx + 1.2, dy + dh * f,
                                L_COMPONENT, LW_THIN))
        balloon(canvas, dx + dw * 0.25, dy + dh * 0.30, "2")
        legend.append(("2", "Insulated door, double leaf"))

        # Heater bank along the floor of the chamber.
        hb_h = h * 0.07
        hb_y = y + h - t - hb_h
        canvas.add(Rect(x + t + w * 0.04, hb_y, w * 0.42, hb_h, L_COMPONENT, LW_MED))
        for i in range(1, 6):
            hx = x + t + w * (0.04 + 0.42 * i / 6)
            canvas.add(Line(hx, hb_y, hx, hb_y + hb_h, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.28, hb_y - 5.0, "3")
        legend.append(("3", f"Heater bank - {heating}".strip(" -") or "Heater bank"))

        # Circulation blower on the roof, with its delivery duct into the chamber.
        br = min(w, h) * 0.055
        bcx, bcy = x + w * 0.24, y + t + br + 2.0
        canvas.add(Circle(bcx, bcy, br, L_COMPONENT, LW_MED))
        canvas.add(Line(bcx, bcy + br, bcx, y + h * 0.42, L_COMPONENT, LW_THIN, DASH_HIDDEN))
        balloon(canvas, bcx - br - 5.0, bcy, "4")
        qty = f" ({blower_qty} nos)" if blower_qty else ""
        legend.append(("4", f"Recirculation blower {blower_hp}{qty}".strip()))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        t = min(w, h) * 0.05
        canvas.add(Rect(x + t, y + t, w - 2 * t, h - 2 * t, L_COMPONENT, LW_THIN))
        if zones:
            for i in range(1, min(zones, 6)):
                zx = x + w * i / min(zones, 6)
                canvas.add(Line(zx, y + t, zx, y + h - t, L_COMPONENT, LW_THIN, DASH_HIDDEN))
            balloon(canvas, x + w * 0.30, y + h * 0.20, "5")
            legend.append(("5", f"Heating zone division ({zones} zones)"))
        if conveyor:
            # Inside the outline: the right-hand side carries the height dim.
            cy = y + h * 0.72
            canvas.add(Line(x + t, cy, x + w - t, cy, L_COMPONENT, LW_THIN, DASH_CENTRE))
            canvas.add(Text(x + w * 0.5, cy - 2.0, "CONVEYOR CENTRE LINE",
                            L_TEXT, 2.1, "middle"))
            balloon(canvas, x + w * 0.16, cy + 5.5, "6")
            legend.append(("6", f"Conveyor opening - {conveyor}"[:70]))
    return legend


# --------------------------------------------------------------------------
def dust_collector(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Bag/cartridge dust collector GA: clean-air plenum, filter element array,
    hopper, rotary airlock and the induced-draught fan."""
    legend: list[tuple[str, str]] = []
    bags = _nos(_find(rows, "filter bags"), 0)
    cleaning = _find(rows, "cleaning system") or _find(rows, "collector type") or ""
    fan_hp = _find(rows, "blower motor", "hp") or ""
    fan_type = _find(rows, "blower type") or ""
    airlock = _find(rows, "rotary airlock") or ""

    front = views.get("front")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Clean-air plenum across the top.
        pl_h = h * 0.13
        canvas.add(Rect(x, y, w, pl_h, L_COMPONENT, LW_MED))
        balloon(canvas, x + w * 0.10, y + pl_h * 0.5, "1")
        legend.append(("1", "Clean air plenum / outlet manifold"))

        # Filter elements hanging in the chamber, drawn to the real count.
        hop_h = h * 0.30
        hop_y = y + h - hop_h
        bag_top = y + pl_h
        bag_bot = hop_y - 1.0
        shown = min(bags, 12) if bags else 0
        for i in range(shown):
            bx = x + w * (i + 0.5) / shown
            canvas.add(Line(bx, bag_top, bx, bag_bot, L_COMPONENT, LW_THIN))
        if bags:
            # Off the vertical centre line, which the view already draws.
            balloon(canvas, x + w * 0.22, bag_top + (bag_bot - bag_top) * 0.28, "2")
            legend.append(("2", f"Filter element ({bags} nos)"))

        # Hopper: a trapezoid narrowing to the discharge.
        canvas.add(poly([(x, hop_y), (x + w, hop_y),
                         (x + w * 0.58, y + h), (x + w * 0.42, y + h)],
                        L_COMPONENT, LW_MED, closed=True))
        balloon(canvas, x + w * 0.14, hop_y + hop_h * 0.22, "3")
        legend.append(("3", "Dust hopper"))

        # Rotary airlock at the hopper discharge. Drawn just INSIDE the
        # envelope: below it is the width dimension and the view caption.
        if airlock:
            ar = min(hop_h * 0.20, w * 0.035)
            acx, acy = x + w * 0.5, y + h - ar - 1.0
            canvas.add(Circle(acx, acy, ar, L_COMPONENT, LW_MED))
            for k in range(4):
                ang = math.pi * k / 4
                canvas.add(Line(acx - ar * math.cos(ang), acy - ar * math.sin(ang),
                                acx + ar * math.cos(ang), acy + ar * math.sin(ang),
                                L_COMPONENT, LW_THIN))
            balloon(canvas, x + w * 0.80, acy, "4")
            legend.append(("4", f"Rotary airlock {airlock}".strip()))

        # Induced-draught fan on the clean side. Drawn INSIDE the plenum: the
        # left of the sheet is not free space (the views are centred, and a
        # symbol hung off the outline collided with the frame), and the right
        # carries the height dimension.
        fr = min(pl_h * 0.34, w * 0.05)
        fcx, fcy = x + w * 0.78, y + pl_h * 0.5
        canvas.add(Circle(fcx, fcy, fr, L_COMPONENT, LW_MED))
        canvas.add(Line(fcx - fr, fcy, x + w * 0.60, fcy, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.92, fcy, "5")
        legend.append(("5", f"ID fan {fan_type} {fan_hp} HP".replace("  ", " ").strip()))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        # Filter elements on plan, arranged as the nearest tidy grid to the
        # real count. Rows/columns are indicative; the COUNT is real.
        if bags:
            cols = min(int(math.ceil(math.sqrt(bags))), 10)
            rowsn = min(int(math.ceil(bags / cols)), 8)
            r = min(w / (cols + 1), h / (rowsn + 1)) * 0.30
            for rr in range(rowsn):
                for cc in range(cols):
                    cxp = x + w * (cc + 0.5) / cols
                    cyp = y + h * (rr + 0.5) / rowsn
                    canvas.add(Circle(cxp, cyp, max(r, 0.4), L_COMPONENT, LW_THIN))
            # Inside the outline: below it sits the width dimension and caption.
            canvas.add(Text(x + w * 0.5, y - 2.5,
                            f"{bags} FILTER ELEMENTS - ARRANGEMENT INDICATIVE",
                            L_TEXT, 2.1, "middle"))
        if cleaning:
            legend.append(("6", f"Cleaning - {str(cleaning)[:56]}"))
    return legend


# --------------------------------------------------------------------------
def powder_coating_plant(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Powder coating plant GA.

    NOTE the envelope here is the MAXIMUM COMPONENT the plant must handle (the
    catalog's geometry inputs are the largest component's L/W/H), NOT the plant
    footprint. Drawing plant machinery inside it would be a lie, so the glyph
    annotates the component envelope — hook line, travel direction and clearance
    intent — and the legend names the plant modules the spec resolved.
    """
    legend: list[tuple[str, str]] = []
    booth = _find(rows, "powder coating booth") or _find(rows, "spray booth") or ""
    recovery = _find(rows, "powder recovery") or ""
    oven = _find(rows, "curing oven") or ""
    handling = _find(rows, "material handling") or _find(rows, "conveyor") or ""

    front = views.get("front")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        canvas.add(Text(x + w * 0.5, y + h * 0.62, "MAXIMUM COMPONENT ENVELOPE",
                        L_TEXT, 2.6, "middle", bold=True))
        # Hook / hanging point at the top centre: the component hangs from the
        # conveyor, so the envelope top IS the hook line.
        hx = x + w * 0.5
        hr = min(w, h) * 0.035
        canvas.add(Circle(hx, y - hr - 2.0, hr, L_COMPONENT, LW_MED))
        canvas.add(Line(hx, y - 2.0, hx, y + h * 0.06, L_COMPONENT, LW_THIN))
        canvas.add(Line(x - 6.0, y - hr - 2.0, x + w + 6.0, y - hr - 2.0,
                        L_COMPONENT, LW_THIN, DASH_CENTRE))
        balloon(canvas, x + w * 0.16, y + h * 0.12, "1")
        legend.append(("1", f"Conveyor hook line - {handling}".strip(" -") or
                       "Conveyor hook line"))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        # Direction of travel through the line.
        # Kept INSIDE the outline — the right-hand side carries the height
        # dimension, and an arrow overhanging the view collided with it.
        cy = y + h * 0.30
        canvas.add(Line(x + w * 0.12, cy, x + w * 0.84, cy, L_COMPONENT, LW_THIN, DASH_CENTRE))
        canvas.add(poly([(x + w * 0.88, cy), (x + w * 0.84, cy - 1.6),
                         (x + w * 0.84, cy + 1.6)], L_COMPONENT, LW_THIN, "currentColor"))
        canvas.add(Text(x + w * 0.5, cy - 2.2, "DIRECTION OF TRAVEL", L_TEXT, 2.1, "middle"))
        balloon(canvas, x + w * 0.16, cy + 5.5, "2")
        legend.append(("2", "Plant line direction"))

    # The modules themselves are real resolved values but have no engineered
    # setting-out, so they are scheduled in the legend rather than drawn.
    for tag, label, value in (("A", "Powder coating booth", booth),
                              ("B", "Powder recovery", recovery),
                              ("C", "Curing oven", oven)):
        if value:
            legend.append((tag, f"{label}: {str(value)[:52]} (not to scale)"))
    return legend


# --------------------------------------------------------------------------
def conveyor(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Overhead conveyor GA: track section, carriers at pitch, and drive unit."""
    legend: list[tuple[str, str]] = []
    ctype = _find(rows, "type") or ""
    moc = _find(rows, "moc") or ""
    operation = _find(rows, "operation") or ""

    front = views.get("front")
    plan = views.get("plan")
    side = views.get("side")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Track at the top of the envelope, carriers hanging below it.
        ty = y + h * 0.12
        canvas.add(Line(x, ty, x + w, ty, L_COMPONENT, LW_MED))
        canvas.add(Line(x, ty + 1.6, x + w, ty + 1.6, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.08, ty - 5.0, "1")
        legend.append(("1", f"Track - {ctype or 'overhead conveyor'} {moc}".strip()))

        # Carriers at an indicative pitch (no engineered pitch is given).
        for i in range(8):
            cx = x + w * (i + 0.5) / 8
            canvas.add(Line(cx, ty + 1.6, cx, y + h * 0.55, L_COMPONENT, LW_THIN))
            canvas.add(Line(cx - w * 0.012, y + h * 0.55, cx + w * 0.012, y + h * 0.55,
                            L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.5, y + h * 0.62, "2")
        legend.append(("2", "Carrier / hanger - pitch indicative"))

        # Drive unit at the far end.
        dwid, dhei = w * 0.06, h * 0.10
        canvas.add(Rect(x + w - dwid, ty - dhei, dwid, dhei, L_COMPONENT, LW_MED))
        balloon(canvas, x + w - dwid - 5.5, ty - dhei * 0.5, "3")
        legend.append(("3", f"Drive unit - {operation or 'drive'}".strip()))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        cy = y + h / 2
        canvas.add(Line(x, cy, x + w, cy, L_COMPONENT, LW_THIN, DASH_CENTRE))
        canvas.add(Text(x + w * 0.5, cy - 2.0, "TRACK CENTRE LINE - ROUTING INDICATIVE",
                        L_TEXT, 2.1, "middle"))

    if side:
        x, y, w, h = side.x, side.y, side.w, side.h
        # Track section on the side elevation.
        canvas.add(Line(x + w * 0.5 - w * 0.22, y + h * 0.12, x + w * 0.5 + w * 0.22,
                        y + h * 0.12, L_COMPONENT, LW_MED))
        canvas.add(Line(x + w * 0.5, y + h * 0.12, x + w * 0.5, y + h * 0.55,
                        L_COMPONENT, LW_THIN))
    return legend


# --------------------------------------------------------------------------
def ducting(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Ducting GA: the run shown DEVELOPED (straight), with flanged joints and
    the section on the side view. The developed-length framing matters — the
    length is a total run, not a straight-line distance."""
    legend: list[tuple[str, str]] = []
    duct = _find(rows, "exhaust duct") or _find(rows, "duct") or ""
    material = _find(rows, "material") or ""

    front = views.get("front")
    side = views.get("side")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Flanged joints at an indicative spool pitch.
        for i in range(1, 8):
            jx = x + w * i / 8
            canvas.add(Line(jx, y - 1.6, jx, y + h + 1.6, L_COMPONENT, LW_THIN))
        balloon(canvas, x + w * 0.5, y + h * 0.5, "1")
        legend.append(("1", f"Flanged duct spool {material}".strip()))
        canvas.add(Text(x + w * 0.5, y - 4.0, "DEVELOPED LENGTH - ROUTING NOT SHOWN",
                        L_TEXT, 2.2, "middle"))

    if side:
        x, y, w, h = side.x, side.y, side.w, side.h
        canvas.add(Circle(x + w / 2, y + h / 2, min(w, h) * 0.42, L_COMPONENT, LW_MED))
        balloon(canvas, x + w * 0.5, y + h * 0.5, "2")
        legend.append(("2", f"Duct section {duct}".strip()))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        canvas.add(Line(x, y + h / 2, x + w, y + h / 2, L_COMPONENT, LW_THIN, DASH_CENTRE))
    return legend


# --------------------------------------------------------------------------
def generic(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Fallback: envelope only. Honest for a category with no glyph yet — the
    sheet still carries real dimensions and the full TBD schedule."""
    return []


SYMBOLS: dict[str, Callable] = {
    "paint_booth": paint_booth,
    "wet_scrubber": wet_scrubber,
    "hot_air_oven": hot_air_oven,
    "dust_collector": dust_collector,
    "powder_coating_plant": powder_coating_plant,
    "conveyor": conveyor,
    "ducting": ducting,
}


def draw_components(canvas, category: str, views: dict, rows: list) -> list[tuple[str, str]]:
    """Draw the category's component glyphs; returns the legend rows."""
    return SYMBOLS.get(category, generic)(canvas, views, rows)
