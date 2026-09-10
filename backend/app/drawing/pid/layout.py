"""Nodes onto the sheet: a declared column/lane grid, resolved by arithmetic.

WHY THERE IS NO SOLVER. The template already declared where each item belongs in
the process — `col` is its step left to right, `lane` is which band it sits in.
Turning that into millimetres is division. A packing search would be slower, far
harder to keep byte-deterministic, and would take a drafting judgement away from
the person best placed to make it: whoever wrote the template can move a node by
changing one integer.

COLLISIONS ARE MADE IMPOSSIBLE, NOT DETECTED. This is `style.py`'s dimension-lane
argument (DIM_LANE_OVERALL / MAJOR / COMPONENT) applied to equipment: every node
in a lane shares one baseline, lanes are a fixed pitch apart, and the pitch is
sized from the tallest symbol plus the deepest tag block. Two nodes cannot
overlap because there is nowhere for them to overlap.
"""
from typing import NamedTuple

from . import symbols as pid_symbols

PID_MARGIN = 6.0          # inset from the drawing area's edge
LANE_PITCH = 46.0         # centre-to-centre between process bands
INSTRUMENT_CLEAR = 15.0   # room above lane 0 for the bubbles that sit there
NODE_W_MAX = 26.0
NODE_H = pid_symbols.NODE_H
TAG_BLOCK_H = 3.0 + 2.6 * 3   # tag line plus up to three attribute lines


class Placed(NamedTuple):
    """One node, positioned in sheet millimetres."""
    key: str
    tag: str
    kind: str
    label: str
    x: float
    y: float
    w: float
    h: float
    lane: int
    col: int
    node: object          # the process_model.Node it came from

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def box(self) -> tuple:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


def band_geometry(nodes, ax: float, ay: float, aw: float, ah: float) -> tuple:
    """The drawing band the train occupies, and how wide a column is.

    The train takes the TOP of the drawing area and the schedules take what is
    left, because a reader looks at the process first and consults the schedule
    second. Returning the split here keeps `service.py` from deciding it twice.
    """
    cols = max((n.col for n in nodes), default=0) + 1
    lanes = sorted({n.lane for n in nodes}) or [0]
    lo, hi = min(lanes), max(lanes)
    col_w = (aw - PID_MARGIN * 2) / max(cols, 1)
    band_h = (hi - lo + 1) * LANE_PITCH
    top = ay + PID_MARGIN + INSTRUMENT_CLEAR
    return col_w, top, band_h, lo


def layout(nodes, ax: float, ay: float, aw: float, ah: float) -> list:
    """Place every node. Pure arithmetic; identical input, identical output.

    A node declared `inside` another is positioned RELATIVE TO ITS HOST rather
    than on the grid — a demister is a feature of the tower, not a step in the
    process, and giving it a column of its own would tell the reader the gas
    leaves the vessel and comes back.
    """
    if not nodes:
        return []
    col_w, top, _band_h, lane0 = band_geometry(nodes, ax, ay, aw, ah)
    node_w = min(col_w * 0.72, NODE_W_MAX)

    placed: list = []
    hosts: dict = {}
    for n in nodes:
        if n.inside:
            continue
        w = node_w * n.span + (col_w - node_w) * (n.span - 1)
        h = pid_symbols.node_height(n.kind)
        x = ax + PID_MARGIN + n.col * col_w + (col_w * n.span - w) / 2
        # Lanes are BASELINE-ALIGNED on their centre, so a tall vessel grows
        # about its own middle instead of pushing its lane's lines off-axis.
        y = top + (n.lane - lane0) * LANE_PITCH + (NODE_H - h) / 2
        p = Placed(n.key, n.tag, n.kind, n.label, x, y, w, h,
                   n.lane, n.col, n)
        hosts[n.key] = p
        placed.append(p)

    # Internals, second, so their host is already positioned.
    for n in nodes:
        if not n.inside:
            continue
        host = hosts.get(n.inside)
        if not host:
            continue
        w = host.w * 0.42
        h = 3.2
        x = host.x + (host.w - w) / 2
        y = host.y + host.h * n.at - h / 2
        placed.append(Placed(n.key, n.tag, n.kind, n.label, x, y, w, h,
                             host.lane, host.col, n))
    return placed


def by_key(placed: list) -> dict:
    return {p.key: p for p in placed}


def band_bottom(placed: list) -> float:
    """Where the process band ends, tag blocks included — the schedules start
    below this, and nothing may be drawn into the gap."""
    if not placed:
        return 0.0
    return max(p.y + p.h for p in placed) + TAG_BLOCK_H + 4.0
