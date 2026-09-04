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
from .style import DIM_LANE_COMPONENT, DIM_LANE_OVERALL, T_VIEW_TITLE

# Preferred drafting scales, largest first. The engine picks the first that
# fits — a real drawing office uses these, not an arbitrary ratio.
#
# 1:30 and 1:40 were added 2026-09-04 because the ladder jumped 1:25 -> 1:50,
# and that gap was wasting a third of the sheet. A 5 x 3 x 4 m booth needs
# 342 mm of width at 1:25 and only 238 mm exists beside the notes column, so it
# fell all the way to 1:50 and drew at HALF the size the paper could carry. At
# 1:40 the same booth needs 222 mm — it fits, and every view is 25% larger.
#
# These are drawing-office scales, not invented ratios: 1:30 and 1:40 are in
# routine industrial use, and the ladder already carried 1:25, which is no more
# ISO-preferred than they are. The RULE that matters is unchanged — a view is
# drawn at a stated standard scale and every dimension is true at it, which is
# what `dimension_not_true` in the QA gate verifies for whatever scale is
# chosen.
STANDARD_SCALES = [1, 2, 5, 10, 20, 25, 30, 40, 50, 100, 200, 500]

VIEW_GAP = 18.0        # mm between views on the sheet
LABEL_DROP = 6.0       # mm below a view for its caption

# Room that must exist to the RIGHT of the right-hand view, for annotation that
# lives OUTSIDE the view rectangle: the overall dimension lane (7 mm), its text,
# and the level datum caption beyond that ("FFL 0.000" is ~12 mm at caption
# size).
#
# WHY THIS EXISTS. `choose_scale` used to measure the view rectangles ALONE, so
# a scale could "fit" while the marks that belong to it did not. At 1:50 there
# was enough slack that nothing showed; the moment a larger scale used that
# slack, the level datums ran past the notes-column rule and printed over the
# legend. The views fitted and the drawing did not — and the QA gate did not
# catch it, because its reserved-column check reads geometry rather than the
# extent of a text run. Measured off a render, not guessed.
ANNOTATION_GUTTER = 20.0


def annotation_gutter(avail_w: float) -> float:
    """The right-hand annotation reserve for a drawing area this wide.

    Reserved only where it can actually do its job. On A4 the notes column
    takes 148 mm of a 297 mm sheet, leaving a 115 mm drawing column — and there
    the datum captions overrun the column rule at 1:100 WHETHER OR NOT the
    gutter is reserved (measured, both ways). All reserving it achieves is
    dropping A4 to 1:200, which halves every view and thins the powder plant's
    plan below the QA gate's sparse threshold. A reserve that fails to protect
    the annotation AND destroys the drawing is the worst of both.

    So it applies on sheets with room to benefit, and a cramped sheet keeps the
    behaviour it already had. A4's real problem is the width of the notes
    column, not this reserve, and that is a separate decision about what an A4
    sheet is for.
    """
    return ANNOTATION_GUTTER if avail_w >= 150.0 else 0.0


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
    gutter = annotation_gutter(avail_w)
    for s in STANDARD_SCALES:
        if (span_x / s + VIEW_GAP + gutter <= avail_w
                and span_y / s + VIEW_GAP + LABEL_DROP * 2 <= avail_h):
            return s
    return STANDARD_SCALES[-1]


# Which views each drawing type asks for. The studio has offered this choice
# since the studio was built, but nothing consumed it — picking "Plan only"
# silently produced the full three-view GA.
VIEW_SETS = {
    "ga": ("plan", "front", "side"),
    # The same three views PLUS an envelope isometric in the free top-right
    # quadrant. Kept as its own type rather than folded into "ga": a third-angle
    # GA is complete without a pictorial, and some drawing offices do not want
    # one on a working sheet.
    "ga_iso": ("plan", "front", "side"),
    "plan": ("plan",),
    "elevation": ("front", "side"),
}

# Drawing types that also carry the pictorial.
ISO_TYPES = {"ga_iso"}


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
    # Centre within the width MINUS the annotation gutter, not the full width.
    # Reserving the gutter in `choose_scale` alone achieved nothing: the block
    # was then centred in the whole area, which handed half the reserved space
    # back to the left margin and pushed the right-hand level datums over the
    # notes-column rule again. The reservation and the placement have to agree.
    ox += max(0.0, (avail_w - annotation_gutter(avail_w) - block_w) / 2)

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


def draw_view(canvas, v: View, dim_labels: dict, caption: str = "") -> None:
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

    # OVERALL dimensions take the lane nearest the view; anything a glyph adds
    # steps out to the next lane, so parallel dimensions cannot collide.
    # Each OVERALL dimension names the envelope axis it measures, so a click on
    # it can be traced back to the input that produced it. Only these carry an
    # edit key: they are the dimensions that correspond one-to-one with a
    # requirement field. A component dimension has no such input — there is
    # nothing to send the reader to — and labelling it editable would promise
    # an edit the engine cannot honour.
    canvas.add(Dim(v.x, v.y + v.h, v.x + v.w, v.y + v.h,
                   dim_labels.get(v.w_axis, "TBD"), offset=DIM_LANE_OVERALL,
                   edit_key=v.w_axis))
    canvas.add(Dim(v.x + v.w, v.y, v.x + v.w, v.y + v.h,
                   dim_labels.get(v.h_axis, "TBD"), offset=DIM_LANE_OVERALL,
                   vertical=True, edit_key=v.h_axis))

    # View title, underscored the way a drafted sheet does it: the rule is what
    # binds the caption to its view when three views share one field.
    # The caption stays just under the OVERALL dimension. Pushing it below every
    # lane instead put it 29 mm down, which is more than the 28 mm the layout
    # leaves between the plan and the front elevation — the plan's title landed
    # ON the elevation below it. A deeper lane is kept clear by not DRAWING a
    # dimension that would collide (see `_panel_joints`), not by moving the
    # caption the view stack is spaced around.
    ty = v.y + v.h + LABEL_DROP + 8.0
    text = caption or v.label
    canvas.add(Text(v.x + v.w / 2, ty, text, L_TEXT, T_VIEW_TITLE,
                    "middle", bold=True))
    half = max(len(text) * T_VIEW_TITLE * 0.30, v.w * 0.18)
    canvas.add(Line(v.x + v.w / 2 - half, ty + 1.6,
                    v.x + v.w / 2 + half, ty + 1.6, L_TEXT, LW_MED))
