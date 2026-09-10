"""Orthogonal routing between ports, and the hop marks where lines cross.

THE CORRIDOR IS ALLOCATED, NOT SEARCHED. A vertical run between two columns sits
at a lane derived from the stream's index among the streams sharing that column
gap, taken in TEMPLATE ORDER. Two parallel drops therefore cannot land on each
other, for the same reason two dimensions cannot in `style.py`: the space is
divided up front rather than negotiated. A router that detects a collision and
nudges is a router whose output depends on the order it happened to consider
things, which is exactly what byte-determinism cannot tolerate.

A ROUTE IS AT MOST THREE SEGMENTS. Anything a template needs beyond that is a
sign the lane assignment is wrong, and the fix belongs in the data.

WHY HOPS EXIST AT ALL. Where two lines cross without one, a reader sees a tee —
a connection the plant does not have. That is the single most dangerous thing a
P&ID can assert, so the crossing is broken by the line whose medium ranks lower
in priority: a main air line is never broken by a utility line.
"""
import math

from ..primitives import Line, poly
from ..style import PROCESS_LINE, UTILITY_LINE
from ...engineering.process_model import MEDIUM_AIR, MEDIUM_RANK
from . import ports as pid_ports

HOP_R = 1.5
MAX_CROSSINGS = 8
CORRIDOR_BASE = 0.30      # fraction of the inter-column gap
CORRIDOR_STEP = 0.14


def pen_for(medium: str):
    """A main process line takes the heavy pen; everything else steps down.

    On a P&ID the line IS the subject of the drawing, so what a reader must see
    first is the process train, not the drain that happens to cross it.
    """
    return PROCESS_LINE if medium == MEDIUM_AIR else UTILITY_LINE


def corridors(streams, placed_by_key: dict) -> dict:
    """Stream tag -> its corridor index within the column gap it crosses.

    Assigned in one deterministic pass in template order. No sets, no sorting by
    anything that could hash differently between runs.
    """
    seen: dict = {}
    out: dict = {}
    for s in streams:
        a, b = placed_by_key.get(s.frm), placed_by_key.get(s.to)
        if not a or not b:
            continue
        gap = (min(a.col, b.col), max(a.col, b.col))
        out[s.tag] = seen.get(gap, 0)
        seen[gap] = seen.get(gap, 0) + 1
    return out


STUB = 5.0                # how far a line steps clear of a symbol


def outward(kind: str, name: str) -> tuple:
    """The direction a line LEAVES a port, as a unit vector.

    A port on the top face departs upwards. This is the fact the first version
    of this router did not have, and the defect it caused was not subtle: a line
    from a tower's top outlet to a fan below it was routed straight back DOWN
    THROUGH THE TOWER, which on a P&ID reads as a connection into the vessel it
    had just left. Departing along the port's own normal makes that impossible.
    """
    fx, fy = pid_ports.port(kind, name) or (1.0, 0.5)
    if fy <= 0.01:
        return (0.0, -1.0)
    if fy >= 0.99:
        return (0.0, 1.0)
    if fx <= 0.01:
        return (-1.0, 0.0)
    if fx >= 0.99:
        return (1.0, 0.0)
    return (1.0, 0.0) if fx > 0.5 else (-1.0, 0.0)


def route(stream, a, b, k: int, col_w: float) -> tuple:
    """The polyline from a's port to b's port.

    Both ends step clear of their symbol along the port normal first, and the
    two stub ends are then joined orthogonally. Which join applies is decided by
    the two departure AXES, never guessed from relative position — that is what
    keeps a pump's discharge leaving vertically out of its volute.
    """
    x1, y1 = pid_ports.port_xy(a.kind, stream.from_port, a.x, a.y, a.w, a.h)
    x2, y2 = pid_ports.port_xy(b.kind, stream.to_port, b.x, b.y, b.w, b.h)
    d1 = outward(a.kind, stream.from_port)
    d2 = outward(b.kind, stream.to_port)

    s1 = (x1 + d1[0] * STUB, y1 + d1[1] * STUB)
    s2 = (x2 + d2[0] * STUB, y2 + d2[1] * STUB)
    v1, v2 = abs(d1[1]) > 0.5, abs(d2[1]) > 0.5

    if not v1 and not v2:
        if abs(s1[1] - s2[1]) < 0.4:
            mid = []
        else:
            # A Z through an ALLOCATED corridor: the fraction comes from the
            # stream's index among those sharing this column gap, so two
            # parallel drops can never land on each other.
            mx = s1[0] + (s2[0] - s1[0]) * (CORRIDOR_BASE + CORRIDOR_STEP * k)
            mid = [(mx, s1[1]), (mx, s2[1])]
    elif v1 and not v2:
        mid = [(s1[0], s2[1])]
    elif v2 and not v1:
        mid = [(s2[0], s1[1])]
    else:
        my = s1[1] + (s2[1] - s1[1]) * (CORRIDOR_BASE + CORRIDOR_STEP * k)
        mid = [(s1[0], my), (s2[0], my)]

    return _clean([(x1, y1), s1] + mid + [s2, (x2, y2)])


def _clean(pts) -> tuple:
    """Drop duplicate and collinear points, so a segment count means something
    and the QA gate is not counting joints that are not there."""
    out = []
    for p in pts:
        if out and abs(p[0] - out[-1][0]) < 0.01 and abs(p[1] - out[-1][1]) < 0.01:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        if ((abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01)
                or (abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01)):
            out.pop(i)
        else:
            i += 1
    return tuple(out)


def segments(pts) -> list:
    return [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            for i in range(len(pts) - 1)]


def crossings(routed: list) -> list:
    """Every true intersection between two routed lines.

    Both are axis-aligned, so this is an interval test rather than a general
    line intersection — and a shared endpoint is NOT a crossing, because two
    lines meeting at a port is a tee the plant really has.
    """
    out: list = []
    for i, (tag_a, med_a, segs_a) in enumerate(routed):
        for tag_b, med_b, segs_b in routed[i + 1:]:
            for sa in segs_a:
                for sb in segs_b:
                    pt = _cross(sa, sb)
                    if pt:
                        out.append((tag_a, med_a, sa, tag_b, med_b, sb, pt))
    return out


def _cross(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    a_h = abs(ay1 - ay2) < 0.01
    b_h = abs(by1 - by2) < 0.01
    if a_h == b_h:
        return None                      # parallel; lanes keep them apart
    if a_h:
        hx1, hx2, hy = min(ax1, ax2), max(ax1, ax2), ay1
        vy1, vy2, vx = min(by1, by2), max(by1, by2), bx1
    else:
        hx1, hx2, hy = min(bx1, bx2), max(bx1, bx2), by1
        vy1, vy2, vx = min(ay1, ay2), max(ay1, ay2), ax1
    # A strict interior test: touching at an end is a connection, not a cross.
    if hx1 + 0.5 < vx < hx2 - 0.5 and vy1 + 0.5 < hy < vy2 - 0.5:
        return (vx, hy)
    return None


def draw_line(canvas, pts, medium: str, hops: list) -> None:
    """One routed line, broken by any hop that belongs to it."""
    pen = pen_for(medium)
    for x1, y1, x2, y2 in segments(pts):
        on_seg = [h for h in hops
                  if _on(h, x1, y1, x2, y2)]
        if not on_seg:
            canvas.add(Line(x1, y1, x2, y2, *pen))
            continue
        horiz = abs(y1 - y2) < 0.01
        order = sorted(on_seg, key=lambda p: (p[0] if horiz else p[1]),
                       reverse=(x2 < x1 if horiz else y2 < y1))
        cx, cy = x1, y1
        for hx, hy in order:
            if horiz:
                sign = 1.0 if x2 > x1 else -1.0
                canvas.add(Line(cx, cy, hx - HOP_R * sign, hy, *pen))
                canvas.add(poly(_hop_arc(hx, hy, True, sign),
                                pen.layer, pen.width, closed=False))
                cx, cy = hx + HOP_R * sign, hy
            else:
                sign = 1.0 if y2 > y1 else -1.0
                canvas.add(Line(cx, cy, hx, hy - HOP_R * sign, *pen))
                canvas.add(poly(_hop_arc(hx, hy, False, sign),
                                pen.layer, pen.width, closed=False))
                cx, cy = hx, hy + HOP_R * sign
        canvas.add(Line(cx, cy, x2, y2, *pen))


def _on(pt, x1, y1, x2, y2) -> bool:
    px, py = pt
    if abs(y1 - y2) < 0.01:
        return (abs(py - y1) < 0.01
                and min(x1, x2) - 0.01 <= px <= max(x1, x2) + 0.01)
    if abs(x1 - x2) < 0.01:
        return (abs(px - x1) < 0.01
                and min(y1, y2) - 0.01 <= py <= max(y1, y2) + 0.01)
    return False


def _hop_arc(cx: float, cy: float, horizontal: bool, sign: float,
             steps: int = 8) -> list:
    """A half-circle bridge, as a real polyline.

    Not an SVG arc command, for the reason `primitives.hatch` gives for refusing
    a pattern fill: the DXF and PDF exporters consume coordinates, so a curve
    expressed only in markup would render on screen and vanish from both.
    """
    out = []
    for i in range(steps + 1):
        a = math.pi * i / steps
        if horizontal:
            out.append((cx - HOP_R * sign * math.cos(a),
                        cy - HOP_R * math.sin(a)))
        else:
            out.append((cx + HOP_R * math.sin(a),
                        cy - HOP_R * sign * math.cos(a)))
    return out


def hop_owner(med_a: str, med_b: str) -> bool:
    """True when A hops over B. The lower-priority medium is the one broken."""
    return MEDIUM_RANK.get(med_a, 9) > MEDIUM_RANK.get(med_b, 9)
