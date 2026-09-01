"""Third-angle projection of the spec's mm envelope onto the sheet.

The spec engine hands over a numeric envelope in MODEL millimetres
(`geometry.envelope_mm`). This module decides the drawing scale, works out where
the plan / front / side views sit on the sheet, and converts model mm to sheet
mm. It draws the equipment ENVELOPE only — component detail lives in symbols.py.

Third-angle convention (the Indian/ISO norm Vitech drafts to):

        ┌────────────┐
        │    PLAN    │            plan sits ABOVE the front elevation
        └────────────┘
        ┌────────────┐ ┌───────┐
        │   FRONT    │ │ SIDE  │  right-side view sits to the RIGHT of front
        └────────────┘ └───────┘

An axis with no known dimension is NOT drawn to a guessed length: the view is
skipped and the missing dimension is reported so the sheet can carry it as a TBD
schedule entry instead (see drawing_service).
"""
from typing import NamedTuple, Optional

from .primitives import (DASH_CENTRE, LW_MED, LW_THIN, L_CENTRE, L_DIM,
                         L_OUTLINE, L_TEXT, Dim, Line, Rect, Text)

# Preferred drafting scales, largest first. The engine picks the first that
# fits — a real drawing office uses these, not an arbitrary ratio.
STANDARD_SCALES = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500]

VIEW_GAP = 22.0        # mm between views on the sheet
LABEL_DROP = 6.0       # mm below a view for its caption


class View(NamedTuple):
    """One projected view, positioned in sheet mm."""
    key: str
    label: str
    x: float           # top-left on the sheet
    y: float
    w: float           # drawn size in sheet mm
    h: float
    model_w: Optional[int]     # the model mm this view's width represents
    model_h: Optional[int]
    w_axis: str        # which envelope axis the width is ("length"/"width")
    h_axis: str


def choose_scale(env: dict, avail_w: float, avail_h: float) -> int:
    """Smallest standard scale divisor whose full third-angle layout fits.

    The layout's overall extent is (length + width) across and (height + width)
    down, plus the gaps between views — that is what has to fit, not one view.
    """
    L = env.get("length") or 0
    W = env.get("width") or 0
    H = env.get("height") or 0
    span_x = (L + W) / 1000.0 * 1000  # mm model
    span_y = (H + W) / 1000.0 * 1000
    for s in STANDARD_SCALES:
        if span_x / s + VIEW_GAP <= avail_w and span_y / s + VIEW_GAP + LABEL_DROP * 2 <= avail_h:
            return s
    return STANDARD_SCALES[-1]


# Which views each drawing type asks for. The studio has offered this choice
# since the studio was built, but nothing consumed it — picking "Plan only"
# silently produced the full three-view GA.
VIEW_SETS = {
    "ga": ("plan", "front", "side"),
    "plan": ("plan",),
    "elevation": ("front", "side"),
}


def layout(env: dict, ox: float, oy: float, avail_w: float, avail_h: float,
           scale: int, drawing_type: str = "ga") -> list[View]:
    """Place whichever views the known dimensions support, in third angle.

    Returns an empty list when nothing can be drawn to true size, which the
    caller renders as an honest "no dimensioned views" sheet rather than a
    fabricated box.
    """
    wanted = VIEW_SETS.get(str(drawing_type or "ga").lower(), VIEW_SETS["ga"])
    L, W, H = env.get("length"), env.get("width"), env.get("height")

    def s(v):
        return None if v is None else v / scale

    sL, sW, sH = s(L), s(W), s(H)
    views: list[View] = []

    # Front elevation — length x height. The primary view; drawn bottom-left.
    front_h = sH if ("front" in wanted and sH is not None) else None
    plan_h = sW if ("plan" in wanted and sW is not None) else None

    # Vertical stack: plan on top, then gap, then front.
    total_h = (plan_h or 0) + (VIEW_GAP if plan_h and front_h else 0) + (front_h or 0)
    top = oy + max(0.0, (avail_h - total_h - LABEL_DROP * 2) / 2)

    # Centre the view block horizontally in the drawing area. Without this the
    # views hug the left edge and a small-scale drawing leaves a dead band
    # between the geometry and the notes column. The block is as wide as its
    # widest row (plan, or front + side), and the leading gutter also gives the
    # glyphs that sit outside an outline (a scrubber's pump) somewhere to go.
    row_w = 0.0
    if sL is not None and front_h is not None and sW is not None:
        row_w = sL + VIEW_GAP + sW
    elif sL is not None:
        row_w = sL
    block_w = max(row_w, sL or 0.0)
    ox += max(0.0, (avail_w - block_w) / 2)

    y_cursor = top
    if sL is not None and plan_h is not None:
        views.append(View("plan", "PLAN", ox, y_cursor, sL, plan_h, L, W, "length", "width"))
        y_cursor += plan_h + VIEW_GAP + LABEL_DROP

    if sL is not None and front_h is not None:
        views.append(View("front", "FRONT ELEVATION", ox, y_cursor, sL, front_h,
                          L, H, "length", "height"))
        # Side elevation — width x height, to the right of front, same baseline.
        if sW is not None and "side" in wanted:
            views.append(View("side", "SIDE ELEVATION", ox + sL + VIEW_GAP, y_cursor,
                              sW, front_h, W, H, "width", "height"))
    return views


def draw_view(canvas, v: View, dim_labels: dict) -> None:
    """Outline + centre lines + dimensions + caption for one view.

    `dim_labels` maps an envelope axis to the text to print, so a resolved axis
    shows its millimetres and an unresolved one can print "TBD" instead of a
    number nobody has computed.
    """
    canvas.add(Rect(v.x, v.y, v.w, v.h, L_OUTLINE))

    # Centre lines, both axes.
    cx, cy = v.x + v.w / 2, v.y + v.h / 2
    canvas.add(
        Line(v.x - 4, cy, v.x + v.w + 4, cy, L_CENTRE, LW_THIN, DASH_CENTRE),
        Line(cx, v.y - 4, cx, v.y + v.h + 4, L_CENTRE, LW_THIN, DASH_CENTRE),
    )

    # Width dimension below, height dimension to the right.
    canvas.add(Dim(v.x, v.y + v.h, v.x + v.w, v.y + v.h,
                   dim_labels.get(v.w_axis, "TBD"), offset=7.0))
    canvas.add(Dim(v.x + v.w, v.y, v.x + v.w, v.y + v.h,
                   dim_labels.get(v.h_axis, "TBD"), offset=7.0, vertical=True))

    canvas.add(Text(v.x + v.w / 2, v.y + v.h + LABEL_DROP + 8.0, v.label,
                    L_TEXT, 3.2, "middle", bold=True))
