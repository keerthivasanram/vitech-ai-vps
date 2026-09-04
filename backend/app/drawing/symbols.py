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

from .. import values
from .primitives import (L_COMPONENT, L_TEXT,
                         Circle, Dim, Line, Rect, Text, hatch, poly)
from . import components, detailing
from .style import (AIRFLOW_LINE, BALLOON, BALLOON_R, CENTRE_LINE,
                    DIM_LANE_MAJOR, DOOR, DUCT, EQUIPMENT, FLOOR_LINE,
                    HATCH_LINE, HIDDEN_LINE, INTERNAL_DETAIL, LEADER_DOT_R,
                    LEADER_LINE, OPENING, PANEL_SEAM, PRIMARY_OUTLINE,
                    SECONDARY_OUTLINE, SYMBOL_DETAIL, T_BODY, T_CAPTION,
                    T_DIM, T_SMALL, T_TINY, T_VIEW_TITLE)



def balloon(canvas, x: float, y: float, tag: str, to=None) -> None:
    """A numbered item balloon, with a LEADER to the thing it names.

    Without a leader a balloon is a number floating near several components and
    the reader has to guess which one it belongs to — which on a sheet whose
    whole purpose is to say what each item IS defeats the schedule. The leader
    runs from the balloon's edge (not its centre, which would draw a line
    through the digit) to the feature, and ends in a filled dot, the convention
    for landing on a face rather than an edge.
    """
    canvas.add(Circle(x, y, BALLOON_R, BALLOON.layer, BALLOON.width),
               Text(x, y + 1.0, tag, L_COMPONENT, T_SMALL, "middle"))
    if not to:
        return
    tx, ty = float(to[0]), float(to[1])
    dx, dy = tx - x, ty - y
    dist = math.hypot(dx, dy)
    if dist <= BALLOON_R + 0.6:          # target inside the balloon: no leader
        return
    sx = x + dx / dist * BALLOON_R
    sy = y + dy / dist * BALLOON_R
    canvas.add(Line(sx, sy, tx, ty, *LEADER_LINE),
               Circle(tx, ty, LEADER_DOT_R, BALLOON.layer, BALLOON.width,
                      fill="currentColor"))


def item(canvas, legend: list, x: float, y: float, description: str, to=None) -> str:
    """Draw the next balloon and register its legend row in one go.

    Tags allocate themselves from the legend's length rather than being written
    into each glyph. Most legend rows are CONDITIONAL — a luminaire row only
    exists when the spec states a count — so hard-coded tags left gaps in the
    numbering (a sheet reading 1, 2, 3, 5) whenever an item did not resolve.
    """
    # Count only the numbered rows: lettered `note_item` rows share the legend
    # but not the numbering sequence.
    tag = str(sum(1 for t, _ in legend if t.isdigit()) + 1)
    balloon(canvas, x, y, tag, to)
    legend.append((tag, description.replace("  ", " ").strip()))
    return tag


def airflow(canvas, points, label: str = "") -> None:
    """A direction-of-flow arrow with an optional caption.

    Flow direction is how the equipment WORKS — air enters a scrubber low and
    leaves at the top — so it is a fact of the machine type, not a position we
    invented. It is drawn as direction only and never dimensioned, which keeps
    it on the right side of golden rule #2 while making the sheet far easier to
    read at a glance.
    """
    # Its OWN dash, not the hidden-detail one. Flow is not part of the machine,
    # so it must not read as part of it — and sharing DASH_HIDDEN made an
    # airflow arrow indistinguishable from geometry behind a wall.
    pts = [(float(x), float(y)) for x, y in points]
    for a, b in zip(pts, pts[1:]):
        canvas.add(Line(a[0], a[1], b[0], b[1], *AIRFLOW_LINE))
    (bx, by), (tx, ty) = pts[-2], pts[-1]
    dx, dy = tx - bx, ty - by
    mag = math.hypot(dx, dy) or 1.0
    ux, uy = dx / mag, dy / mag
    px, py = -uy * 1.5, ux * 1.5
    canvas.add(poly([(tx, ty), (tx - ux * 3.4 + px, ty - uy * 3.4 + py),
                     (tx - ux * 3.4 - px, ty - uy * 3.4 - py)],
                    AIRFLOW_LINE.layer, AIRFLOW_LINE.width, "currentColor"))
    if label:
        canvas.add(Text(tx, ty - 2.4, label, L_TEXT, T_CAPTION, "middle"))


def _clip(text: str, limit: int = 54) -> str:
    """Bound a legend description WITHOUT cutting a word in half.

    The glyphs used to hard-slice at a character count, which printed rows like
    "Base frame / supports SS-304 2mm (MS painted base/su". The sheet's own
    `_wrap` is word-safe, but it never got the chance — the string arrived
    already mangled. A truncated engineering value reads as a wrong one, so the
    cut moves to the last space and marks itself as continuing.
    """
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-/")
    return (cut or s[:limit]) + " ..."


def note_item(legend: list, description: str) -> str:
    """A legend row with NO balloon: something the spec resolved but that has no
    engineered position to draw. Lettered, so a reader can tell at a glance that
    numbers are on the drawing and letters are scheduled only."""
    letters = [t for t, _ in legend if t.isalpha()]
    tag = chr(ord("A") + len(letters))
    legend.append((tag, description.replace("  ", " ").strip()))
    return tag


def _int(value, default: int = 0) -> int:
    """First integer inside a spec value like '9 (dry)' or '2 sets/booth'."""
    return values.first_integer(value, default)


def _nos(value, default: int = 0) -> int:
    """A COUNT, only when the value actually states one ('4 nos', '2 sets').

    See `values.stated_count` for why a bare number is refused.
    """
    return values.stated_count(value, default)


# "100 mm rockwool" / "50mm PUF" / "insulation 75 mm" -> the millimetres.
# A bare number is deliberately NOT matched: on an insulation row it is as
# likely to be a grade or a density as a thickness.
_MM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.I)


def _mm_on_sheet(text, v, cap_frac: float = 0.12):
    """A stated millimetre thickness converted to SHEET mm for this view.

    Returns None when the value states no thickness, when the view carries no
    model dimension to scale against, or when the result would be too thin to
    read — below about a third of a millimetre a hatched band prints as a
    smudge, and a smudge that claims to be 100 mm of rockwool is worse than an
    honest symbolic line.

    Capped at a fraction of the view so an implausible parse (a "2000 mm"
    read out of some other phrase) can never swallow the machine.
    """
    if not text or not v or not v.model_w or not v.model_h:
        return None
    m = _MM_RE.search(str(text))
    if not m:
        return None
    mm = float(m.group(1))
    per_mm = min(v.w / float(v.model_w), v.h / float(v.model_h))
    t = mm * per_mm
    if t < 0.35 or t > min(v.w, v.h) * cap_frac:
        return None
    return t


def _resolved(value) -> bool:
    """True when a spec value is a real answer rather than an admitted gap.

    A TBD must never be drawn as though the equipment has it — that is the
    hallucination the TBD contract exists to prevent.
    """
    return values.is_resolved(value)


# `_row`/`_find` read a spec row the same way the BOM does — see `app/values.py`.
_row = values.find_row


def _find(rows, *needles) -> Optional[str]:
    """Value of the first spec row whose label contains all the needles.

    AN ADMITTED GAP IS NOT A VALUE. Glyphs compose captions like
    `f"Insulated panel lining {insulation}"`, so a raw "To be determined"
    reaching here printed "Insulated panel lining To be determined" into the
    legend — which reads as a component whose description is a sentence about
    not knowing. The gap belongs in the TBD schedule, where it already is, and
    the legend simply names the part. Returning None lets every existing
    `or ""` / `.strip()` at the call sites do the right thing unchanged.
    """
    v = values.row_value(rows, *needles)
    return v if _resolved(v) else None


def _part(rows, needles, *keys):
    """A SUB-VALUE of a composite spec field.

    A powder-coating plant records a module as one nested object
    (`{'oven_type': 'batch', 'inner_size_m': '3.0L x 1.8W x 2.5H', ...}`). The
    resolver flattens that to readable text for the specification table but
    keeps the original mapping on the row as `parts`, so the drawing reads the
    module's real size from the SAME resolved value the table prints instead of
    re-parsing it back out of prose.
    """
    parts = (_row(rows, *needles) or {}).get("parts") or {}
    for k in keys:
        if parts.get(k) not in (None, "", []):
            return parts[k]
    return None


# "3L x 1.9W x 2.5H" / "2.4 L x 1.7 W x 5.5 H" -> (3.0, 1.9, 2.5) in metres.
_LWH_RE = re.compile(r"([\d.]+)\s*L\s*[x*]\s*([\d.]+)\s*W\s*[x*]\s*([\d.]+)\s*H", re.I)


def _lwh(value) -> Optional[tuple]:
    """Parse a recorded 'L x W x H' size string into floats, else None.

    Returns None rather than a partial guess: a module drawn from half a size
    would be a fabricated dimension.
    """
    m = _LWH_RE.search(str(value or ""))
    if not m:
        return None
    try:
        out = tuple(float(g) for g in m.groups())
    except ValueError:
        return None
    return out if all(v > 0 for v in out) else None


def _count_in(rows, *needles) -> int:
    """A COUNT from a row whose label names a countable thing.

    Deliberately narrow: it reads the row's leading integer, so it must only be
    pointed at labels like "Process stages" ("7 tank"), never at a size row
    ("Tank size (mm) = 2000 x 1000 x 1200") where the first integer is a
    dimension, not a quantity.
    """
    value = _find(rows, *needles)
    return _nos(value, 0) or _int(value, 0)


# --- Shared enclosure furniture -------------------------------------------
# Several categories are, in drafting terms, the same box with different
# contents: a lit enclosure with a door, an extract face and a fan. These
# helpers keep that shared vocabulary in one place so each glyph below only
# expresses what actually differs.
def _luminaire_label(rows) -> str:
    """The luminaire description the SPEC resolved, never a hardcoded one.

    Every booth glyph printed "Flame-proof LED luminaire" while the
    specification, on the same sheet, said "40 W weatherproof LED". Those are
    different fittings at different prices, and flame-proof is a HAZARDOUS-AREA
    classification — so the drawing was making a safety claim the engineering
    had never made. A drawing must not re-decide what the resolver resolved.
    """
    text = _find(rows, "illumination")
    if not text:
        return "LED luminaire"
    # Drop a leading count so the legend does not print the quantity twice.
    cleaned = re.sub(r"^\s*\d+\s*(?:nos?|no\.?|sets?)\s*", "", str(text), flags=re.I)
    return cleaned.strip() or "LED luminaire"


# Draft direction as the SPEC resolved it. Ordered so "semi down" is matched
# before "down", and "cross" before anything else it contains.
_DRAFTS = (("cross", "CROSS DRAFT", "across"),
           ("semi down", "SEMI DOWN DRAFT", "down"),
           ("full down", "DOWN DRAFT", "down"),
           ("side", "SIDE DRAFT", "across"),
           ("down", "DOWN DRAFT", "down"))


def _draft(rows) -> tuple[str, str]:
    """(caption, axis) for the booth's airflow, read from the resolved type.

    The plan used to print "DOWN DRAFT" with vertical arrows on EVERY booth,
    including one the specification on the same sheet called a Dry Filter CROSS
    Draft. The draft direction is how the machine works and it is the thing a
    reader checks first, so drawing it from a hardcoded caption rather than from
    the resolved type made the sheet contradict its own design data.
    """
    text = (_find(rows, "type of paint booth") or "").lower()
    for needle, caption, axis in _DRAFTS:
        if needle in text:
            return caption, axis
    return "AIRFLOW", "down"


# Vitech's own panel module (`paint_shop_service`): a booth is an assembly of
# 900 x 2500 mm sheets on a 750 mm pitch, which is what its weight is costed
# from. Drawing the joints at that REAL pitch is detail the sheet already knows,
# not a spacing invented to make an elevation look busy — the view carries the
# model mm it represents, so the joints land where they actually fall.
PANEL_PITCH_MM = 750.0
PANEL_COURSE_MM = 2500.0


def _panel_joints(canvas, v, dimension: bool = False) -> None:
    """Panel and course joints on an elevation, at the real module.

    With `dimension`, ONE bay is dimensioned at the MAJOR lane. That figure is
    honest engineering: 750 mm is Vitech's own panel pitch, the module their
    booth weight is costed from, so it is a resolved value and not a position
    inferred from the drawing. Component POSITIONS still carry no dimension at
    all — inventing one is the failure this whole engine is built to avoid.
    """
    if not v.model_w or not v.model_h or v.model_w <= 0 or v.model_h <= 0:
        return
    per_mm_x = v.w / float(v.model_w)
    per_mm_y = v.h / float(v.model_h)
    step_x = PANEL_PITCH_MM * per_mm_x
    if step_x > 1.5:                       # below this the joints read as noise
        n_joints = int(float(v.model_w) // PANEL_PITCH_MM)
        for i in range(1, min(n_joints, 24) + 1):
            jx = v.x + i * step_x
            if jx < v.x + v.w - 0.5:
                canvas.add(Line(jx, v.y, jx, v.y + v.h, *PANEL_SEAM))
        # A single bay, one lane out from the overall dimension. COLLISION
        # CHECK, not a hope: the view caption is centred under the view at this
        # depth, so the bay dimension is drawn only when it ends clear of the
        # caption's own half-width. On a view too narrow for both, the drawing
        # simply does without it — a dimension printed over a title is worse
        # than a dimension not printed.
        title_half = len(v.label) * T_VIEW_TITLE * 0.30 + 2.0
        clear = v.x + step_x < v.x + v.w / 2 - title_half
        if dimension and n_joints >= 1 and step_x > 8.0 and clear:
            canvas.add(Dim(v.x, v.y + v.h, v.x + step_x, v.y + v.h,
                           f"{PANEL_PITCH_MM:g}", offset=DIM_LANE_MAJOR))
    step_y = PANEL_COURSE_MM * per_mm_y
    if step_y > 1.5:
        n_courses = int(float(v.model_h) // PANEL_COURSE_MM)
        for i in range(1, min(n_courses, 8) + 1):
            jy = v.y + v.h - i * step_y
            if jy > v.y + 0.5:
                canvas.add(Line(v.x, jy, v.x + v.w, jy, *PANEL_SEAM))


# Which views are genuinely SECTIONS rather than outside elevations, per
# category. A glyph that draws the filter bank, the blower and the heater inside
# the casing is not showing the outside of the machine — it is showing a cut
# through it, and calling that "FRONT ELEVATION" is simply the wrong caption.
# Naming it correctly costs no geometry and is the single clearest signal that
# a sheet was drafted rather than generated.
#
# ONLY listed where the glyph really does draw internals. A section mark
# pointing at a view that shows nothing inside would be worse than no mark.
SECTION_VIEWS = {
    "paint_booth": {"front": "A"},
    "wet_scrubber": {"front": "A"},
    "dust_collector": {"front": "A"},
    "hot_air_oven": {"front": "A"},
    "paint_drying_oven": {"front": "A"},
    "blast_booth": {"front": "A"},
    "pretreatment_plant": {"front": "A"},
}


def section_tag(category: str, key: str, views: dict) -> Optional[str]:
    """The section letter for this view, or None if it cannot be located.

    ONE decision serves both the caption and the cutting plane. If the plan is
    too small to carry a legible mark, the view must ALSO stop calling itself
    "SECTION A-A" — a section caption with no locating mark is a reference to a
    cut nobody can find, which is worse than an unlabelled elevation.
    """
    tag = (SECTION_VIEWS.get(category) or {}).get(key)
    if not tag:
        return None
    plan = (views or {}).get("plan")
    # The stubs, arrowheads and letters need roughly 9 mm either side. A
    # 750 mm scrubber tower is about 30 mm of plan at 1:25, where they land on
    # the overall dimension and on the view's own captions.
    if plan is None or plan.w < 50.0 or plan.h < 26.0:
        return None
    return tag


def view_caption(category: str, key: str, default: str, views: dict = None) -> str:
    """The caption a view carries, allowing a glyph's section to say so."""
    tag = section_tag(category, key, views or {})
    return f"SECTION {tag}-{tag}" if tag else default


def _section_mark(canvas, plan, category: str) -> None:
    """Put the cutting plane on the PLAN for whichever view is a section.

    Drawn along the machine's long axis at mid-width, which is the cut the
    front view actually shows. It is a drawing statement, not an engineering
    one: it says where the view was taken, and every component inside it is
    still governed by the sheet's indicative-position note.
    """
    tag = section_tag(category, "front", {"plan": plan} if plan else {})
    if not tag:
        return
    cy = plan.y + plan.h / 2
    # Stops SHORT of the overall-width dimension lane on the right. A cutting
    # plane conventionally projects beyond the view, but the lane nearest the
    # view is already spoken for, and a mark drawn over a dimension is worse
    # than one drawn a little shorter.
    detailing.section_marker(canvas, plan.x - 5.0, cy, plan.x + plan.w + 2.5, cy,
                             tag=tag)


def _levels(canvas, v, top_label: str = "") -> None:
    """Datum marks on an elevation: finished floor, and the top of the machine.

    BOTH LEVELS ARE ALREADY ON THE SHEET as engineering — the floor line the
    view stands on, and the overall height the envelope states — so this adds a
    reading convention, not a value. When the height is not resolved the top
    marker is simply not drawn; there is no such thing as an approximate level.
    """
    fy = v.y + v.h * 0.94
    detailing.level_marker(canvas, v.x + v.w + 3.0, fy, "FFL 0.000")
    if v.model_h and v.h_axis == "height":
        detailing.level_marker(canvas, v.x + v.w + 3.0, v.y,
                               top_label or f"+{float(v.model_h) / 1000.0:.3f}")


def _floor(canvas, v, legend: list = None, label: bool = True) -> float:
    """Floor level with a hatched slab band beneath it, and the base frame.

    Returns the y of the floor line. The elevations used to show a bare line
    labelled FLOOR LEVEL floating in an empty box; a hatched slab is what says
    which side of it is ground.
    """
    fy = v.y + v.h * 0.94
    canvas.add(Line(v.x, fy, v.x + v.w, fy, *FLOOR_LINE))
    # Base frame with its bearing points, from the shared library.
    components.structural_base(canvas, v.x, fy, v.w, v.h * 0.035)
    canvas.add(hatch(v.x, fy, v.w, v.h * 0.06, spacing=2.0, slope=-1,
                        layer=HATCH_LINE.layer, width=HATCH_LINE.width))
    if label:
        canvas.add(Text(v.x + v.w * 0.30, fy - v.h * 0.05, "FLOOR LEVEL",
                        L_TEXT, T_CAPTION, "middle"))
    return fy


def _filter_cells(canvas, x: float, y: float, w: float, h: float,
                  count: int, vertical: bool = True) -> None:
    """A filter bank, from the shared component library.

    Kept as a thin adapter so every existing call site inherits the PLEATED
    media without being rewritten: a plain rectangle reads as glazing, and even
    a 45-degree hatch reads as solid material — neither says "filter".
    """
    components.filter_bank(canvas, x, y, w, h, count, across=not vertical)


def _lights(canvas, v, count: int, legend: list, label: str) -> None:
    """A row of luminaires along the roof of an elevation."""
    if not count:
        return
    shown = min(count, 6)
    xs = []
    for i in range(shown):
        lx = v.x + v.w * (0.14 + 0.72 * (i / max(1, shown - 1)))
        xs.append(lx)
        components.luminaire(canvas, lx, v.y + v.h * 0.08,
                             v.w * 0.07, v.h * 0.04)
    # The leader lands on a REAL fitting. Aimed at the view's mid-point it fell
    # in the gap between two of an even-numbered row, pointing at nothing.
    item(canvas, legend, v.x + v.w * 0.5, v.y + v.h * 0.16,
         f"{label} ({count} nos)", to=(xs[len(xs) // 2], v.y + v.h * 0.08))


def _filter_bank(canvas, v, count: int, legend: list, label: str) -> float:
    """An extract filter bank across the rear of a plan view; returns its depth.

    Uses the shared bank so the cells carry PLEATED media. A plain divided
    rectangle is equally true of glazing or a louvre; the pleats are what say
    "filter" without reading the legend.
    """
    depth = v.h * 0.14
    by = v.y + v.h - depth
    components.filter_bank(canvas, v.x, by, v.w, depth, count or 1, across=True)
    item(canvas, legend, v.x + v.w * 0.14, by - 5.0,
         f"{label}" + (f" ({count} nos)" if count else ""),
         to=(v.x + v.w * 0.14, by + depth * 0.5))
    return depth


def _fan(canvas, v, depth: float, legend: list, label: str) -> None:
    """The extract blower inside the footprint, just ahead of the extract face.

    Kept INSIDE the outline on purpose: below the view is the width dimension
    and the caption, and a symbol overhanging the outline collides with both.
    That is also why the RADIUS is derived from the space available — the
    shared blower draws a volute, a tangential discharge and a drive motor, so
    it needs about 1.9r across and 1.6r down from its centre.

    Discharge is DOWN, i.e. out through the rear face the bank sits on: air is
    drawn through the filters and pushed out behind the machine. That is how
    the equipment works, not a position we chose, so it is safe to draw.
    """
    avail_w = v.w * 0.16
    avail_h = max(depth * 1.4, v.h * 0.12)
    r = min(avail_w / 1.9, avail_h / 1.6)
    cx = v.x + v.w / 2
    # The discharge STOPS SHORT of the extract face rather than crossing into
    # it. Drawn overlapping, the throat sat inside the filter bank and read as
    # a blower buried in the media; ending clear of it reads as the connection
    # it is. `blower` puts the throat's far face at 1.55r from the centre.
    cy = v.y + v.h - depth - r * 1.55 - 1.0
    components.blower(canvas, cx, cy, r, discharge="down", motor=True)
    item(canvas, legend, cx + r * 2.0 + 4.0, cy, label,
         to=(cx + r * 1.475, cy))


def _side_enclosure(canvas, v, extract: bool = True, roof_plant: bool = False,
                    lining: bool = False, opening: bool = False) -> None:
    """The enclosure seen from the side: floor, base, panel courses, extract face.

    WHY THIS EXISTS. Nine of the fourteen glyphs drew NOTHING in the side
    elevation — an empty rectangle with two centre lines, on a three-view sheet.
    A reader takes that as "this machine has no side", which is worse than a
    sparse view: the outline and its dimensions are real, so the emptiness reads
    as an engineering statement rather than an unwritten glyph.

    IT DRAWS GEOMETRY AND NO BALLOONS, deliberately. Every component here is
    already scheduled from the plan or the front, and a GA balloons an item
    ONCE — a second balloon on the same filter bank would put two numbers in the
    legend for one thing and make the item list disagree with itself.

    Everything drawn is the same INDICATIVE arrangement the sheet's standing
    note already covers; no new dimension is implied and none is added.
    """
    _floor(canvas, v, None, label=False)
    _panel_joints(canvas, v)

    if lining:
        t = min(v.w, v.h) * 0.05
        canvas.add(Rect(v.x + t, v.y + t, v.w - 2 * t, v.h - 2 * t, *PANEL_SEAM))

    if extract:
        # The extract face seen edge-on: a shallow band down the rear edge.
        # Rear is the RIGHT-hand edge here, which is where the plan's rear face
        # projects to in third angle.
        depth = v.w * 0.10
        bx = v.x + v.w - depth
        components.filter_bank(canvas, bx, v.y + v.h * 0.06, depth,
                               v.h * 0.82, 4, across=False)

    if roof_plant:
        # The plant deck across the roof, shown as the band it occupies.
        canvas.add(Rect(v.x + v.w * 0.16, v.y + v.h * 0.02, v.w * 0.62,
                        v.h * 0.06, *SECONDARY_OUTLINE))

    if opening:
        # A through-machine opening reads on the side as the clear height of
        # the aperture, drawn as an OPENING (a void, not hidden geometry).
        oh = v.h * 0.46
        canvas.add(Rect(v.x + v.w * 0.24, v.y + v.h - oh - v.h * 0.06,
                        v.w * 0.52, oh, *OPENING))


def _door(canvas, v, legend: list, label: str, frac: float = 0.34) -> None:
    """A double-leaf door on the working face of an elevation."""
    dw = v.w * frac
    dx = v.x + (v.w - dw) / 2
    dh = v.h * 0.72
    dy = v.y + v.h - dh
    components.access_door(canvas, dx, dy, dw, dh, leaves=2)
    item(canvas, legend, dx + dw * 0.22, dy + dh * 0.24, label)


def _blower_label(rows) -> str:
    """The extract fan's description from whatever the spec resolved."""
    hp = _find(rows, "blower motor", "hp") or _find(rows, "blower", "hp") or ""
    cfm = _find(rows, "blower", "cfm") or ""
    qty = _nos(_find(rows, "blower", "qty"), 0)
    bits = [b for b in (str(cfm and f"{cfm} CFM"), str(hp and f"{hp} HP")) if b]
    return ("Exhaust blower " + ", ".join(bits) + (f" ({qty} nos)" if qty else "")).strip()


# --------------------------------------------------------------------------
def paint_booth(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Paint booth GA: enclosure, filter bank, extract plant, lighting, services.

    Everything drawn comes from a value the spec resolved (filter count, blower
    model, luminaire count, duct bore, panel rating) or from how the booth type
    works. Setting-out that needs a client standard is scheduled, not invented.
    """
    legend: list[tuple[str, str]] = []
    # The filter count is labelled differently depending on which path resolved
    # it: the standards package emits "Paint arresting filter" (singular), the
    # historical-reuse path "Filters". Reading only the plural silently drew a
    # bank with no elements on every standards-resolved booth.
    filters = (_nos(_find(rows, "arresting filter"), 0)
               or _nos(_find(rows, "paper filter"), 0)
               or _int(_find(rows, "filters"), 0))
    blower = _find(rows, "exhaust blower") or ""
    blower_qty = _nos(_find(rows, "blower", "nos"), 0) or _int(_find(rows, "blower", "nos"), 1)
    blower_hp = _find(rows, "blower motor", "hp") or ""
    lights = _nos(_find(rows, "illumination"), 0)
    duct = _find(rows, "exhaust duct") or ""
    intake = _find(rows, "intake filter") or _find(rows, "inlet filter") or ""
    carbon = _find(rows, "carbon") or ""
    panel = _find(rows, "control panel") or ""
    fire = _find(rows, "fire") or ""
    construction = _find(rows, "construction") or ""

    front = views.get("front")
    side = views.get("side")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Panel and course joints at Vitech's real 750 x 2500 module, so the
        # working face reads as the panelled enclosure it is rather than a box.
        _panel_joints(canvas, front, dimension=True)
        # Extract face on the elevation, hatched as filter media. Which END it
        # sits on follows the draft direction, the same as the plan.
        _, _front_axis = _draft(rows)
        fb_w = w * 0.09 if filters else 0.0
        _bank_right = _front_axis == "across"
        if filters:
            fb_x = x + w - fb_w if _bank_right else x
            _filter_cells(canvas, fb_x, y + h * 0.10, fb_w, h * 0.78,
                          min(filters, 8), vertical=True)
        # Door opening: a double-leaf sliding door across the working face.
        dw = w * 0.44
        dx = x + (w - dw) / 2
        dh = h * 0.66
        dy = y + h - dh
        components.access_door(canvas, dx, dy, dw, dh, leaves=2)
        item(canvas, legend, dx + dw / 2, dy - 5.0, "Manual sliding door, double leaf",
             to=(dx + dw / 2, dy + dh * 0.20))

        # View panels either side of the door.
        for sx in (x + w * 0.10, x + w * 0.78):
            canvas.add(Rect(sx, y + h * 0.26, w * 0.12, h * 0.18, *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.16, y + h * 0.20, "View glass panel",
             to=(x + w * 0.16, y + h * 0.35))

        if lights:
            for i in range(min(lights, 6)):
                lx = x + w * (0.14 + 0.72 * (i / max(1, min(lights, 6) - 1)))
                canvas.add(Rect(lx - w * 0.035, y + h * 0.07, w * 0.07, h * 0.035,
                                *SYMBOL_DETAIL))
            # Offset from the door balloon below it, which sits at dy - 5 mm.
            item(canvas, legend, x + w * 0.36, y + h * 0.135,
                 f"{_luminaire_label(rows)} ({lights} nos)")

        # Control panel against the side wall — a resolved rating, so the panel
        # is a real item rather than assumed switchgear.
        if panel:
            pw, ph = w * 0.07, h * 0.22
            # Clear of the extract bank: at 0.905w the panel was drawn straight
            # over it, two components occupying the same 20 mm of sheet.
            px = (x + w - fb_w - pw - w * 0.02) if _bank_right else x + w * 0.905
            py = y + h * 0.52
            components.control_panel(canvas, px, py, pw, ph)
            item(canvas, legend, px - 6.0, py + ph * 0.5, _clip(f"Control panel {panel}"),
                 to=(px + pw * 0.5, py + ph * 0.5))

        # Floor, slab hatch and the base frame the enclosure stands on. The
        # front elevation had none of this and read as a box floating in space.
        _floor(canvas, front, label=False)

    if side:
        # The side elevation was an EMPTY BOX. It carries the extract face: the
        # filter bank, the duct off the roof, a luminaire and the floor line, so
        # the two elevations read as the same booth.
        x, y, w, h = side.x, side.y, side.w, side.h
        _panel_joints(canvas, side)
        bank_w = w * 0.16
        bx = x + w - bank_w
        _filter_cells(canvas, bx, y + h * 0.12, bank_w, h * 0.76,
                      min(filters, 8) if filters else 4, vertical=True)
        item(canvas, legend, bx - 6.0, y + h * 0.30,
             f"Extract face - arresting filters ({filters} nos)" if filters
             else "Extract face - arresting filters",
             to=(bx + bank_w * 0.5, y + h * 0.30))

        # Exhaust duct off the extract end, drawn INSIDE the outline as a stub:
        # hung off the envelope it would cross the height dimension.
        if duct:
            _dx = x + w * 0.67
            # Stops AT the casing: run past it and the duct walls climb into
            # the overall-height dimension above the view.
            components.duct_run(canvas, _dx, y + h * 0.13, _dx, y + h * 0.005,
                                w * 0.13)
            components.flange(canvas, _dx, y + h * 0.11, w * 0.13)
            airflow(canvas, [(_dx, y + h * 0.16), (_dx, y + h * 0.02)])
            item(canvas, legend, x + w * 0.44, y + h * 0.05, _clip(f"Exhaust duct {duct}"),
                 to=(x + w * 0.67, y + h * 0.045))

        # Filtered-air inlet plenum on the opposite face, as hidden detail:
        # it sits behind the enclosure wall in this view.
        if intake:
            pw = w * 0.10
            components.plenum(canvas, x, y + h * 0.14, pw, h * 0.72)
            item(canvas, legend, x + pw + 6.0, y + h * 0.33,
                 _clip(f"Air intake filter {intake}"),
                 to=(x + pw * 0.5, y + h * 0.33))

        # Airflow through the booth, inlet plenum to extract face.
        airflow(canvas, [(x + w * 0.24, y + h * 0.50), (x + w * 0.66, y + h * 0.50)])

        _floor(canvas, side)
        if construction:
            item(canvas, legend, x + w * 0.30, y + h * 0.72,
                 _clip(f"Enclosure {construction}"))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        # THE EXTRACT FACE FOLLOWS THE DRAFT DIRECTION. A cross or side draft
        # sweeps the booth END TO END and is extracted through an END wall; a
        # down draft is extracted through the REAR. The plan used to draw the
        # bank across the rear wall on every booth while the arrows ran across
        # it, so the sheet showed air entering one face and leaving another it
        # could not reach.
        draft_caption, draft_axis = _draft(rows)
        across = draft_axis == "across"
        shown_filters = min(filters, 12) if filters else 0

        if across:
            bank_w = w * 0.09
            bx0 = x + w - bank_w
            _filter_cells(canvas, bx0, y, bank_w, h, shown_filters, vertical=True)
            if filters:
                item(canvas, legend, bx0 - 6.0, y + h * 0.12,
                     f"Paint arresting filter bank ({filters} nos)",
                     to=(bx0 + bank_w * 0.5, y + h * 0.12))
            # Blower sits ahead of the bank on the extract centre line.
            bw, bh = w * 0.13, h * 0.24
            bx = bx0 - bw - w * 0.03
            byy = y + (h - bh) / 2
        else:
            bank_d = h * 0.14
            by = y + h - bank_d
            _filter_cells(canvas, x, by, w, bank_d, shown_filters, vertical=False)
            if filters:
                item(canvas, legend, x + w * 0.16, by - 5.0,
                     f"Paint arresting filter bank ({filters} nos)",
                     to=(x + w * 0.16, by + bank_d * 0.5))
            bw, bh = w * 0.16, bank_d * 1.4
            bx = x + (w - bw) / 2
            byy = by - bh - 2.0

        # A scroll with a tangential discharge, not a rectangle with a circle in
        # it — the old symbol was equally true of a tank or a pump.
        # Sized so the WHOLE symbol fits — the volute spans about 3.1r with its
        # discharge, and at 0.46 it ran into the filter bank beside it.
        _bl_r = min(bw, bh) * 0.34
        _port = components.blower(canvas, bx + bw / 2, byy + bh / 2, _bl_r,
                                  discharge="right" if across else "up")
        item(canvas, legend, bx - 6.0 if across else bx + bw + 6.0, byy + bh / 2,
             " ".join(t for t in (f"Exhaust blower {blower}".strip(),
                                  f"({blower_qty} no)",
                                  f"{blower_hp} HP" if str(blower_hp).strip() else "") if t))

        # Activated carbon chamber — a resolved item on a liquid-paint booth,
        # sitting after the arresting bank in the extract path.
        if carbon:
            if across:
                cw, ch = w * 0.10, h * 0.30
                cx, cy = bx - cw - w * 0.04, y + (h - ch) / 2
            else:
                cw, ch = w * 0.22, bh * 0.8
                cx, cy = x + w * 0.06, byy - bh * 0.9
            canvas.add(Rect(cx, cy, cw, ch, *SYMBOL_DETAIL))
            item(canvas, legend, cx - 6.0 if across else cx + cw + 5.5, cy + ch / 2,
                 _clip(f"Activated carbon chamber {carbon}"),
                 to=(cx + cw * 0.5, cy + ch * 0.5))

        # Filtered-air inlet on the face OPPOSITE the extract, as hidden detail.
        if across:
            canvas.add(Line(x + w * 0.04, y, x + w * 0.04, y + h,
                            *HIDDEN_LINE))
            # Inboard of the outline: centred at 0.15w the caption started on
            # the envelope line itself.
            canvas.add(Text(x + w * 0.26, y + h * 0.93, "AIR INLET FILTER END",
                            L_TEXT, T_CAPTION, "middle"))
            airflow(canvas, [(x + w * 0.10, y + h * 0.28), (x + w * 0.40, y + h * 0.28)])
            airflow(canvas, [(x + w * 0.10, y + h * 0.72), (x + w * 0.40, y + h * 0.72)])
            canvas.add(Text(x + w * 0.25, y + h * 0.17, draft_caption,
                            L_TEXT, T_CAPTION, "middle"))
        else:
            canvas.add(Line(x, y + h * 0.10, x + w, y + h * 0.10,
                            *HIDDEN_LINE))
            canvas.add(Text(x + w * 0.5, y + h * 0.075, "AIR INLET FILTER SIDE",
                            L_TEXT, T_CAPTION, "middle"))
            # The caption sits BESIDE the arrow, not on its tip, where it was
            # printed over the arrowhead; arrows are inboard of the carbon
            # chamber's balloon.
            airflow(canvas, [(x + w * 0.42, y + h * 0.16), (x + w * 0.42, y + h * 0.52)])
            airflow(canvas, [(x + w * 0.66, y + h * 0.16), (x + w * 0.66, y + h * 0.52)])
            canvas.add(Text(x + w * 0.54, y + h * 0.38, draft_caption,
                            L_TEXT, T_CAPTION, "middle"))

    # Real resolved services with no engineered position, and the setting-out a
    # production GA needs that the platform has not been given. Naming them
    # turns each gap into a request rather than a silent absence.
    if fire:
        note_item(legend, f"Fire protection - {fire}"[:96])
    note_item(legend, "Anchor bolt setting-out - requires the foundation layout")
    note_item(legend, "Maintenance and access clearances - requires the client's standard")
    return legend


# --------------------------------------------------------------------------
def wet_scrubber(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Wet scrubber GA: gas path, contact stage, demister, sump, pump and blower.

    Everything drawn here is either a value the spec resolved (nozzle count, tank
    capacity, blower rating, demister size) or a fact of how the machine type
    WORKS (gas enters low, leaves through the demister; a recirculating sump has
    a drain and an overflow). What the platform cannot yet supply — anchor-bolt
    setting-out, maintenance clearances, connection sizes — is SCHEDULED on the
    sheet rather than drawn at an invented position.
    """
    legend: list[tuple[str, str]] = []
    nozzles = _int(_find(rows, "spray", "nozzle"), 0)
    pump = _find(rows, "pump", "capacity") or ""
    pump_make = _find(rows, "pump", "make") or ""
    tank = _find(rows, "tank", "capacity") or ""
    blower = _find(rows, "blower", "type") or ""
    blower_hp = _find(rows, "blower motor", "hp") or ""
    demister = _find(rows, "eliminator") or _find(rows, "demister") or ""
    chamber = _find(rows, "scrubber chamber") or ""
    supports = _find(rows, "scrubber tank") or ""
    stype = str(_find(rows, "scrubber type") or "").lower()

    # The CONTACT STAGE follows the scrubber type the spec resolved. Vitech's
    # scrubbers are baffle-plate units, so drawing a packed bed would be adding
    # a component this machine does not have — the packing only appears when the
    # spec actually says packed.
    contact = ("baffle" if "baffle" in stype
               else "packing" if ("pack" in stype or "random" in stype)
               else "")

    front = views.get("front")
    side = views.get("side")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        tank_h = h * 0.26
        ty = y + h - tank_h
        base_h = tank_h * 0.16                    # MS base / supports

        # --- outlet duct + blower over the scrubber ------------------------
        # The spec's own scrubber type says the blower is mounted over the unit,
        # so this is the machine's arrangement rather than a chosen position.
        # Outlet duct into the blower, both from the shared library. A wet
        # scrubber view is NARROW — a 750 mm tower is about 30 mm of sheet at
        # 1:25 — so the volute is sized off the view width and its motor is
        # placed inboard, or the symbol walks off the right-hand edge.
        # Gas leaves UPWARD through the blower, so the duct runs from inside the
        # vessel up to the volute and the volute discharges out of the top. The
        # first version ran the duct DOWN from the blower into the vessel and
        # stacked the balloon, the volute, its motor and the gas-out arrow on
        # the same 10 mm of sheet — an unreadable knot at print size.
        duct_w = w * 0.16
        _cx = x + w * 0.60
        _br = min(w * 0.13, h * 0.042)
        _bcy = y + h * 0.085
        components.duct_run(canvas, _cx, y + h * 0.20, _cx, _bcy + _br, duct_w)
        components.blower(canvas, _cx, _bcy, _br, discharge="up")
        item(canvas, legend, x + w * 0.16, y + h * 0.05,
             " ".join(t for t in ("Outlet duct + blower", str(blower).strip(),
                                  f"{blower_hp} HP" if str(blower_hp).strip() else "") if t))

        # --- demister --------------------------------------------------------
        dy = y + h * 0.16
        dh = h * 0.07
        canvas.add(Rect(x + w * 0.10, dy, w * 0.80, dh, *EQUIPMENT))
        for i in range(1, 8):
            hx = x + w * (0.10 + 0.80 * i / 8)
            canvas.add(Line(hx, dy, hx - h * 0.03, dy + dh, *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.16, dy + dh + 4.5,
             _clip(f"Demister / eliminator {demister}", 60))

        # --- contact stage ---------------------------------------------------
        if contact:
            cy = y + h * 0.26
            ch = h * 0.05
            canvas.add(Rect(x + w * 0.10, cy, w * 0.80, ch, *EQUIPMENT))
            if contact == "baffle":
                for i in range(1, 9):
                    bx = x + w * (0.10 + 0.80 * i / 9)
                    canvas.add(Line(bx, cy, bx, cy + ch, *SYMBOL_DETAIL))
                item(canvas, legend, x + w * 0.94, cy + ch / 2, "Baffle plate contact stage")
            else:
                for i in range(1, 6):
                    canvas.add(Line(x + w * 0.10, cy + ch * i / 6, x + w * 0.90,
                                    cy + ch * i / 6, *HIDDEN_LINE))
                item(canvas, legend, x + w * 0.94, cy + ch / 2, "Packing bed")

        # --- spray headers ---------------------------------------------------
        for i in range(3):
            sy = y + h * (0.36 + 0.11 * i)
            canvas.add(Line(x + w * 0.12, sy, x + w * 0.88, sy, *SYMBOL_DETAIL))
            for j in range(4):
                nx = x + w * (0.20 + 0.20 * j)
                canvas.add(poly([(nx, sy), (nx - 1.4, sy + 2.6), (nx + 1.4, sy + 2.6)],
                                SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width))
        item(canvas, legend, x + w * 0.94, y + h * 0.42,
             f"Spray nozzle header ({nozzles} nozzles)" if nozzles else "Spray nozzle header")

        # --- inlet duct ------------------------------------------------------
        in_y = y + h * 0.66
        components.duct_run(canvas, x - w * 0.02, in_y, x + w * 0.14, in_y,
                            h * 0.09, centre=False)
        components.flange(canvas, x + w * 0.13, in_y, h * 0.09, vertical=False)
        # ABOVE the stub: below it the balloon crossed the sump's top edge.
        item(canvas, legend, x + w * 0.42, in_y + h * 0.04, "Inlet duct (gas entry)")

        # --- sump, water level, base -----------------------------------------
        canvas.add(Rect(x, ty, w, tank_h, *EQUIPMENT))
        wl = ty + tank_h * 0.42
        # The scrubbing liquor below its working level, in the horizontal hatch
        # a section uses for a liquid. This view already CUTS the sump — it
        # shows the level inside it — so hatching the contents is what the view
        # was always claiming, drawn properly.
        detailing.material_hatch(canvas, x, wl, w, ty + tank_h - wl,
                                 detailing.LIQUID)
        canvas.add(Line(x, wl, x + w, wl, *HIDDEN_LINE))
        # Right-anchored just inside the wall. Centred, it was overprinted by the
        # pump balloon on a NARROW view (a 750 mm tower is only ~30 mm of sheet at
        # 1:25), which made both illegible.
        canvas.add(Text(x + w - 1.0, wl - 2.0, "WORKING LEVEL", L_TEXT, T_CAPTION, "end"))
        item(canvas, legend, x + w * 0.66, ty + tank_h * 0.24,
             f"Recirculation sump {tank}".strip())

        # MS base / supports — stated by the spec's own tank row, so the legs are
        # a resolved value rather than an assumed detail.
        components.structural_base(canvas, x, y + h, w, base_h)
        # ABOVE the base band: centred on it the balloon dipped below the
        # envelope's bottom outline.
        item(canvas, legend, x + w * 0.22, y + h - base_h - 4.5,
             _clip(f"Base frame / supports {supports}") if supports
             else "Base frame / supports")

        # --- sump connections -------------------------------------------------
        # A recirculating sump necessarily has a drain, an overflow and a
        # make-up feed; the SIZES are not engineered yet and are scheduled below
        # rather than dimensioned here.
        # STACKED, not side by side. Spaced as a fraction of the view width they
        # sat ~2 mm apart on a narrow tower and the two captions printed over each
        # other as one illegible blob. Stacking is also the truer arrangement:
        # the overflow sits above the working level and the make-up feeds at it.
        cr = min(w * 0.016, tank_h * 0.11)
        ocx = x + w - cr - 1.5
        for frac, tag in ((0.16, "OF"), (0.40, "MU")):
            ocy = ty + tank_h * frac
            canvas.add(Circle(ocx, ocy, cr,
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
            canvas.add(Text(ocx - cr - 1.2, ocy + 0.7, tag, L_TEXT, T_TINY, "end"))
        canvas.add(Circle(x + w * 0.50, y + h - base_h - cr - 0.6, cr,
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
        canvas.add(Text(x + w * 0.545, y + h - base_h - cr - 0.6, "DR", L_TEXT, T_TINY, "start"))

        # --- circulation pump -------------------------------------------------
        pr = min(w * 0.05, tank_h * 0.30)
        pcx, pcy = x + w * 0.12, ty + tank_h * 0.45   # clears the base frame below
        canvas.add(Circle(pcx, pcy, pr,
                          EQUIPMENT.layer, EQUIPMENT.width))
        canvas.add(Line(pcx, pcy - pr, pcx, y + h * 0.36, *SYMBOL_DETAIL))
        item(canvas, legend, pcx + pr + 5.5, pcy,
             " ".join(t for t in ("Circulation pump", str(pump).strip() and f"{pump} HP",
                                  str(pump_make).strip()) if t))

        # --- gas path ---------------------------------------------------------
        airflow(canvas, [(x + w * 0.18, in_y), (x + w * 0.30, in_y)], "GAS IN")
        # Arrow to the LEFT of the blower and unlabelled: drawn through it the
        # arrowhead read as part of the fan, and the caption straddled the
        # envelope's top edge. The balloon and legend already name the outlet.
        airflow(canvas, [(_cx, y + h * 0.20), (_cx, y + h * 0.145)])

    if side:
        # The side elevation was an EMPTY BOX — a third of the sheet showing
        # nothing. It carries the sump, the working level, the gas entry and the
        # access door, so the two elevations read as the same machine.
        x, y, w, h = side.x, side.y, side.w, side.h
        tank_h = h * 0.26
        ty = y + h - tank_h
        base_h = tank_h * 0.16
        canvas.add(Rect(x, ty, w, tank_h, *EQUIPMENT))
        canvas.add(Line(x, ty + tank_h * 0.42, x + w, ty + tank_h * 0.42,
                        *HIDDEN_LINE))
        canvas.add(Rect(x, y + h - base_h, w, base_h, *EQUIPMENT))
        canvas.add(Rect(x + w * 0.10, y + h * 0.16, w * 0.80, h * 0.07,
                        *EQUIPMENT))

        in_y = y + h * 0.66
        canvas.add(Rect(x, in_y - h * 0.045, w * 0.18, h * 0.09, *EQUIPMENT))
        airflow(canvas, [(x + w * 0.22, in_y), (x + w * 0.42, in_y)], "GAS IN")

        # Access door: every scrubber needs the spray bank and demister reached
        # for cleaning. Drawn undimensioned, like every other component here.
        # Kept ABOVE the gas entry: at its first position the door bottom landed
        # exactly on the inlet centre line, so the arrow and its caption were
        # drawn inside the door.
        dw2, dh2 = w * 0.44, h * 0.24
        dx2, dy2 = x + w * 0.28, y + h * 0.28
        canvas.add(Rect(dx2, dy2, dw2, dh2, *SYMBOL_DETAIL))
        canvas.add(Circle(dx2 + dw2 * 0.86, dy2 + dh2 * 0.5, min(dw2, dh2) * 0.10,
                          SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width))
        item(canvas, legend, dx2 + dw2 + 5.0, dy2 + dh2 * 0.5, "Access / inspection door")

    if plan:
        # Also empty before. Shows the header runs across the tower, the sump
        # outline and which side the gas enters and leaves.
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        canvas.add(Rect(x + w * 0.06, y + h * 0.10, w * 0.88, h * 0.80,
                        *HIDDEN_LINE))
        runs = 3
        for i in range(runs):
            hy = y + h * (0.28 + 0.22 * i)
            canvas.add(Line(x + w * 0.12, hy, x + w * 0.88, hy, *EQUIPMENT))
            per = max(1, nozzles // runs) if nozzles else 4
            for j in range(min(per, 8)):
                nx = x + w * (0.16 + 0.68 * (j / max(1, min(per, 8) - 1)))
                canvas.add(Circle(nx, hy, min(w, h) * 0.012,
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
        canvas.add(Text(x + w * 0.5, y + h * 0.20,
                        f"{nozzles} NOZZLES ON {runs} HEADERS - ARRANGEMENT INDICATIVE"
                        if nozzles else "SPRAY HEADERS - ARRANGEMENT INDICATIVE",
                        L_TEXT, T_CAPTION, "middle"))
        canvas.add(Text(x + w * 0.02, y + h * 0.955, "GAS IN", L_TEXT, T_CAPTION, "start"))
        canvas.add(Text(x + w * 0.98, y + h * 0.955, "GAS OUT", L_TEXT, T_CAPTION, "end"))

    # --- what a production GA still needs, stated rather than invented -------
    # These are real omissions, not oversights: each needs a client standard or
    # a setting-out rule the platform has not been given. Naming them turns the
    # gap into a request instead of a silent absence.
    if chamber:
        note_item(legend, f"Chamber / tank MOC - {chamber}")
    note_item(legend, "Connection schedule (OF overflow, MU make-up, DR drain) - "
                      "sizes and orientations to be confirmed")
    note_item(legend, "Anchor bolt setting-out - requires the foundation layout")
    note_item(legend, "Maintenance clearances - requires the client's access standard")
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
        # THE LINING IS DRAWN AT ITS REAL THICKNESS WHENEVER THE SPEC STATES
        # ONE. "100 mm rockwool" at 1:50 is 2 mm of sheet — perfectly drawable —
        # and a wall drawn to its stated thickness, hatched as lagging, is a
        # real engineering statement rather than a symbolic band. When no
        # thickness is stated it falls back to the schematic band it always
        # was: indicative, unhatched, and never dimensioned.
        t_real = _mm_on_sheet(insulation, front)
        t = t_real or min(w, h) * 0.05
        canvas.add(Rect(x + t, y + t, w - 2 * t, h - 2 * t, *PANEL_SEAM))
        if t_real:
            # Only the cut jambs and head/sill are hatched — that is what this
            # view passes through.
            for hx, hy, hw, hh in ((x, y, w, t), (x, y + h - t, w, t),
                                   (x, y + t, t, h - 2 * t),
                                   (x + w - t, y + t, t, h - 2 * t)):
                detailing.material_hatch(canvas, hx, hy, hw, hh,
                                         detailing.INSULATION)
            # The thickness is now a TRUE-SCALE feature, so it can be stated as
            # an engineered value. It is called out on a leader rather than
            # dimensioned: at 2 mm of sheet there is no room between witness
            # lines, and this is the convention for exactly that case.
            mm = _MM_RE.search(str(insulation))
            if mm:
                detailing.note_leader(
                    canvas, x + w * 0.34, y + t / 2, x + w * 0.44, y - 5.5,
                    f"{mm.group(1)} THK INSULATION")
        # Dropped clear of the blower balloon, which sits in the roof band at
        # 0.20h; on a short view the two circles overlapped. A leader is what
        # lets it move without losing which feature it names.
        item(canvas, legend, x + w * 0.07, y + h * 0.42,
             f"Insulated panel lining {insulation}".strip(),
             to=(x + t, y + h * 0.42))

        # Full-height double-leaf door on the loading face.
        dw = w * 0.30
        dx = x + w * 0.60
        dy = y + t
        dh = h - 2 * t
        canvas.add(Rect(dx, dy, dw, dh, *DOOR))
        canvas.add(Line(dx + dw / 2, dy, dx + dw / 2, dy + dh, *PANEL_SEAM))
        # Hinge ticks on both stiles.
        for hx in (dx, dx + dw):
            for f in (0.25, 0.75):
                canvas.add(Line(hx - 1.2, dy + dh * f, hx + 1.2, dy + dh * f,
                                *SYMBOL_DETAIL))
        item(canvas, legend, dx + dw * 0.25, dy + dh * 0.30, "Insulated door, double leaf")

        # Heater bank along the floor of the chamber.
        hb_h = h * 0.07
        hb_y = y + h - t - hb_h
        canvas.add(Rect(x + t + w * 0.04, hb_y, w * 0.42, hb_h, *EQUIPMENT))
        for i in range(1, 6):
            hx = x + t + w * (0.04 + 0.42 * i / 6)
            canvas.add(Line(hx, hb_y, hx, hb_y + hb_h, *PANEL_SEAM))
        item(canvas, legend, x + w * 0.28, hb_y - 5.0, f"Heater bank - {heating}".strip(" -") or "Heater bank")

        # Circulation blower on the roof, with its delivery duct into the chamber.
        br = min(w, h) * 0.055
        bcx, bcy = x + w * 0.24, y + t + br * 1.7 + 2.0
        # Discharges DOWN into the chamber it recirculates through — the duct
        # is hidden because it runs behind the panel the elevation cuts.
        port = components.blower(canvas, bcx, bcy, br, discharge="down", motor=True)
        canvas.add(Line(port[0], port[1], port[0], y + h * 0.42, *HIDDEN_LINE))
        qty = f" ({blower_qty} nos)" if blower_qty else ""
        item(canvas, legend, bcx - br - 5.0, bcy,
             f"Recirculation blower {blower_hp}{qty}".strip(),
             to=(bcx - br * 0.707, bcy + br * 0.707))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        t = min(w, h) * 0.05
        canvas.add(Rect(x + t, y + t, w - 2 * t, h - 2 * t, *PANEL_SEAM))
        if zones:
            for i in range(1, min(zones, 6)):
                zx = x + w * i / min(zones, 6)
                canvas.add(Line(zx, y + t, zx, y + h - t, *HIDDEN_LINE))
            item(canvas, legend, x + w * 0.30, y + h * 0.20, f"Heating zone division ({zones} zones)")
        if conveyor:
            # Inside the outline: the right-hand side carries the height dim.
            cy = y + h * 0.72
            canvas.add(Line(x + t, cy, x + w - t, cy, *CENTRE_LINE))
            canvas.add(Text(x + w * 0.5, cy - 2.0, "CONVEYOR CENTRE LINE",
                            L_TEXT, T_CAPTION, "middle"))
            item(canvas, legend, x + w * 0.16, cy + 5.5, f"Conveyor opening - {conveyor}"[:70])
    if views.get("side"):
        # The oven end: insulated lining, roof-mounted recirculation plant, and
        # the conveyor aperture when the spec states one.
        _side_enclosure(canvas, views["side"], extract=False, roof_plant=True,
                        lining=True, opening=bool(conveyor))
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
    solenoids = _nos(_find(rows, "solenoid"), 0)
    suction = _find(rows, "suction duct") or ""
    exhaust = _find(rows, "exhaust duct") or ""
    panel = _find(rows, "control panel") or ""
    vent = _find(rows, "explosion vent") or ""
    moc = _find(rows, "casing") or ""

    front = views.get("front")
    plan = views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Geometry first, balloons after. The plenum band is only 13% of the
        # view height, which on a typical collector is THINNER THAN A BALLOON —
        # placing item balloons inside it stacked three of them on top of each
        # other and pushed one through the envelope edge. Every balloon for a
        # plenum-mounted item is therefore parked in the roomy chamber below,
        # which is normal GA practice and what the leader-free balloon needs.
        pl_h = h * 0.13
        hop_h = h * 0.30
        hop_y = y + h - hop_h
        bag_top = y + pl_h
        bag_bot = hop_y - 1.0
        ch = bag_bot - bag_top                    # clear chamber height
        canvas.add(Rect(x, y, w, pl_h, *EQUIPMENT))
        item(canvas, legend, x + w * 0.06, bag_top + ch * 0.08,
             "Clean air plenum / outlet manifold")

        # Filter elements hanging in the chamber, drawn to the real count.
        shown = min(bags, 12) if bags else 0
        for i in range(shown):
            bx = x + w * (i + 0.5) / shown
            canvas.add(Line(bx, bag_top, bx, bag_bot, *SYMBOL_DETAIL))
        if bags:
            # Off the vertical centre line, which the view already draws.
            item(canvas, legend, x + w * 0.30, bag_top + ch * 0.42, f"Filter element ({bags} nos)")

        # Hopper: a trapezoid narrowing to the discharge.
        canvas.add(poly([(x, hop_y), (x + w, hop_y),
                         (x + w * 0.58, y + h), (x + w * 0.42, y + h)],
                        EQUIPMENT.layer, EQUIPMENT.width, closed=True))
        item(canvas, legend, x + w * 0.14, hop_y + hop_h * 0.22, "Dust hopper")

        # Rotary airlock at the hopper discharge. Drawn just INSIDE the
        # envelope: below it is the width dimension and the view caption.
        if airlock:
            ar = min(hop_h * 0.20, w * 0.035)
            acx, acy = x + w * 0.5, y + h - ar - 1.0
            canvas.add(Circle(acx, acy, ar,
                          EQUIPMENT.layer, EQUIPMENT.width))
            for k in range(4):
                ang = math.pi * k / 4
                canvas.add(Line(acx - ar * math.cos(ang), acy - ar * math.sin(ang),
                                acx + ar * math.cos(ang), acy + ar * math.sin(ang),
                                *SYMBOL_DETAIL))
            item(canvas, legend, x + w * 0.80, acy, f"Rotary airlock {airlock}".strip())

        # Induced-draught fan on the clean side. Drawn INSIDE the plenum: the
        # left of the sheet is not free space (the views are centred, and a
        # symbol hung off the outline collided with the frame), and the right
        # carries the height dimension.
        # A real volute from the shared library. A bare circle was as true of a
        # tank or an airlock as of a fan; moved inboard to 0.70w because the
        # symbol spans about 3.1r with its discharge and ran into the outlet.
        fr = min(pl_h * 0.30, w * 0.042)
        fcx, fcy = x + w * 0.70, y + pl_h * 0.5
        components.blower(canvas, fcx, fcy, fr, discharge="right", motor=False)
        canvas.add(Line(fcx - fr, fcy, x + w * 0.58, fcy, *SYMBOL_DETAIL))
        # Only state what resolved: an empty type and HP printed a legend row
        # reading a bare "ID fan HP", which looks like a missing value on the
        # sheet — because it is one.
        fan_desc = " ".join(t for t in ("ID fan", str(fan_type).strip(),
                                        f"{fan_hp} HP" if str(fan_hp).strip() else "") if t)
        item(canvas, legend, x + w * 0.92, fcy, fan_desc)

        # Tube sheet — the plate the elements hang from, and the boundary
        # between dirty and clean air. It is what makes the section readable as
        # a filter rather than an empty box.
        canvas.add(Line(x, y + pl_h, x + w, y + pl_h, *EQUIPMENT))

        # Pulse-jet cleaning: compressed-air header across the tube sheet with a
        # blow pipe per solenoid. Drawn only when the spec actually resolved a
        # pulse-jet/solenoid arrangement, so a shaker or reverse-air collector
        # never gets a header it does not have.
        if solenoids or "pulse" in str(cleaning).lower():
            hdr_y = y + pl_h * 0.34
            canvas.add(Line(x + w * 0.06, hdr_y, x + w * 0.62, hdr_y, *EQUIPMENT))
            n_sol = max(1, min(solenoids or 4, 8))
            for i in range(n_sol):
                sx = x + w * (0.10 + 0.48 * (i / max(1, n_sol - 1)))
                canvas.add(Line(sx, hdr_y, sx, y + pl_h, *SYMBOL_DETAIL))
                canvas.add(Rect(sx - w * 0.011, hdr_y - pl_h * 0.20,
                                w * 0.022, pl_h * 0.20, *SYMBOL_DETAIL))
            desc = "Pulse-jet compressed air header"
            if solenoids:
                desc += f", solenoid valve ({solenoids} nos)"
            item(canvas, legend, x + w * 0.28, bag_top + ch * 0.08, desc)

        # Differential-pressure gauge across the tube sheet: the instrument that
        # tells the operator when the elements are blinding.
        dpr = min(pl_h * 0.26, w * 0.028)
        dpx, dpy = x + w * 0.06, bag_top + ch * 0.40
        canvas.add(Circle(dpx, dpy, dpr,
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
        canvas.add(Line(dpx, dpy, dpx + dpr * 0.7, dpy - dpr * 0.7, *SYMBOL_DETAIL))
        item(canvas, legend, dpx + dpr + 4.5, dpy, "Differential pressure gauge")

    side = views.get("side")
    if side:
        x, y, w, h = side.x, side.y, side.w, side.h
        pl_h = h * 0.13
        hop_h = h * 0.30
        hop_y = y + h - hop_h
        canvas.add(Line(x, y + pl_h, x + w, y + pl_h, *EQUIPMENT))
        canvas.add(poly([(x, hop_y), (x + w, hop_y),
                         (x + w * 0.62, y + h), (x + w * 0.38, y + h)],
                        EQUIPMENT.layer, EQUIPMENT.width, closed=True))

        # Dirty-air inlet into the chamber, and the clean-air outlet off the
        # plenum. Both are drawn INSIDE the outline as wall stubs: a duct hung
        # off the envelope overhangs the dimension line (the collision this
        # file's header warns about). Direction only, never dimensioned.
        ch2 = hop_y - y - pl_h
        in_y = y + pl_h + ch2 * 0.20
        components.duct_run(canvas, x - w * 0.02, in_y, x + w * 0.14, in_y,
                            h * 0.08, centre=False)
        components.flange(canvas, x + w * 0.13, in_y, h * 0.08, vertical=False)
        airflow(canvas, [(x + w * 0.16, in_y), (x + w * 0.34, in_y)], "DIRTY AIR IN")
        # Balloon BELOW the stub: above it is the arrow's own caption.
        item(canvas, legend, x + w * 0.07, in_y + ch2 * 0.20,
             f"Dirty air inlet {suction}".strip() if suction else "Dirty air inlet")

        # Outlet arrow runs HORIZONTALLY inside the plenum and carries no
        # caption. Drawn vertically it needed a label above the tip, which
        # landed OUTSIDE the envelope's top edge; the balloon already names it.
        canvas.add(Rect(x + w * 0.80, y, w * 0.16, pl_h, *EQUIPMENT))
        airflow(canvas, [(x + w * 0.60, y + pl_h * 0.5), (x + w * 0.78, y + pl_h * 0.5)])
        if exhaust:
            item(canvas, legend, x + w * 0.46, y + pl_h * 0.5, _clip(f"Exhaust duct {exhaust}"))

        # Access door, kept in the LOWER half of the chamber so it clears the
        # inlet arrow and its caption, which sit in the upper third.
        dw2, dh2 = w * 0.30, ch2 * 0.34
        dx2 = x + w * 0.34
        dy2 = y + pl_h + ch2 * 0.52
        canvas.add(Rect(dx2, dy2, dw2, dh2, *SYMBOL_DETAIL))
        canvas.add(Circle(dx2 + dw2 * 0.86, dy2 + dh2 * 0.5, min(dw2, dh2) * 0.09,
                          SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width))
        item(canvas, legend, dx2 + dw2 + 5.0, dy2 + dh2 * 0.5, "Filter access door")

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
                    canvas.add(Circle(cxp, cyp, max(r, 0.4),
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
            # Inside the outline: below it sits the width dimension and caption.
            canvas.add(Text(x + w * 0.5, y - 2.5,
                            f"{bags} FILTER ELEMENTS - ARRANGEMENT INDICATIVE",
                            L_TEXT, T_CAPTION, "middle"))
        # THE PLAN MUST SHOW THE SAME MACHINE THE ELEVATION DOES. It carried
        # the element grid and two side captions while the elevation showed a
        # pulse header, an ID fan, an airlock and a door — so the two views
        # disagreed about what the collector has. Everything added here is a
        # component the elevation already draws, projected onto the plan; no
        # component appears on one view and not the other.

        # Pulse-jet air headers running across the tube sheet, one per row of
        # elements, with the solenoid count the spec resolved.
        # The headers occupy a BAND, leaving the top and bottom of the plan
        # clear for the captions. Spread over the full height they ran straight
        # through "INLET SIDE" — a caption and a component competing for the
        # same 2 mm, which is the collision this file keeps re-learning.
        if solenoids:
            n_hdr = max(1, min(solenoids, 6))
            for i in range(n_hdr):
                hy = y + h * (0.16 + 0.68 * (i + 0.5) / n_hdr)
                canvas.add(Line(x + w * 0.06, hy, x + w * 0.70, hy, *DUCT))
                canvas.add(Rect(x + w * 0.70, hy - h * 0.016, w * 0.035,
                                h * 0.032, *SYMBOL_DETAIL))
            canvas.add(Text(x + w * 0.38, y + h * 0.10,
                            f"PULSE HEADERS ({solenoids} SOLENOID)",
                            L_TEXT, T_TINY, "middle"))

        # The hopper below, seen through the tube sheet: hidden, because in plan
        # it genuinely is behind the elements.
        canvas.add(Rect(x + w * 0.14, y + h * 0.16, w * 0.72, h * 0.68,
                        *HIDDEN_LINE))

        # The ID fan on the outlet side, discharging clear of the casing — the
        # same fan the elevation puts on the clean side.
        fr = min(w * 0.05, h * 0.09)
        components.blower(canvas, x + w * 0.86, y + h * 0.78, fr,
                          discharge="right", motor=True)

        # The airlock at the hopper discharge, on the machine's centre.
        if airlock:
            canvas.add(Circle(x + w * 0.5, y + h * 0.5, min(w, h) * 0.055,
                              INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))

        # Inlet and outlet SIDES on plan, matching the side elevation, so the
        # two views read as the same machine. Sides, not positions.
        canvas.add(Line(x, y + h * 0.93, x + w * 0.14, y + h * 0.93,
                        *HIDDEN_LINE))
        canvas.add(Text(x + w * 0.02, y + h * 0.97, "INLET SIDE", L_TEXT, T_CAPTION, "start"))
        canvas.add(Text(x + w * 0.98, y + h * 0.97, "OUTLET SIDE", L_TEXT, T_CAPTION, "end"))

    # Real resolved hardware with no engineered position on this sheet is
    # SCHEDULED (lettered) rather than drawn — the sheet must still tell the
    # engineer the collector has a panel, a vent and a stated casing gauge.
    for label, value in (("Cleaning", cleaning), ("Casing & hopper", moc),
                         ("Control panel", panel), ("Explosion vent", vent)):
        if _resolved(value):
            note_item(legend, f"{label} - {value}")
    # A production GA also needs the setting-out below, and each item needs a
    # client standard the platform has not been given. Stated as a request
    # rather than drawn at an invented position.
    note_item(legend, "Support structure and discharge bin - arrangement to be confirmed")
    note_item(legend, "Anchor bolt setting-out - requires the foundation layout")
    note_item(legend, "Access platform and maintenance clearances - requires the "
                      "client's access standard")
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
    pretreat = _find(rows, "pretreatment") or ""

    # Real module sizes, read from the composite field's own sub-values rather
    # than re-parsed out of the printed sentence.
    booth_m = _lwh(_part(rows, ("powder coating booth",), "inner_size_m", "size_m")
                   or (booth if "inner size" in str(booth).lower() else ""))
    oven_m = _lwh(_part(rows, ("curing oven",), "inner_size_m", "size_m")
                  or (oven if "inner size" in str(oven).lower() else ""))
    track = _part(rows, ("material handling",), "track_length_m")

    front = views.get("front")
    plan = views.get("plan")
    side = views.get("side")

    def _opening(v, size_m, caption):
        """Overlay a module's INNER OPENING on a component-envelope view, at the
        view's own scale.

        Both numbers are real — the component envelope is the client's stated
        requirement and the opening is the reused module's recorded inner size —
        so showing them concentrically is a clearance comparison, not an
        invented set-out. It is deliberately left undimensioned, and it is
        skipped when it would coincide with the envelope (a dashed line exactly
        on the outline reads as a rendering fault, not as information).
        """
        if not size_m or not v.model_w or not v.model_h:
            return None
        axis = {"length": size_m[0] * 1000.0, "width": size_m[1] * 1000.0,
                "height": size_m[2] * 1000.0}
        mw, mh = axis.get(v.w_axis), axis.get(v.h_axis)
        if not mw or not mh:
            return None
        ow = mw * (v.w / v.model_w)
        oh = mh * (v.h / v.model_h)
        if abs(ow - v.w) < v.w * 0.02 and abs(oh - v.h) < v.h * 0.02:
            return "coincident"
        oy = v.y + (v.h - oh) / 2
        canvas.add(Rect(v.x + (v.w - ow) / 2, oy, ow, oh,
                        *HIDDEN_LINE))
        # Caption INSIDE the overlay when it nearly fills the view: placed above
        # it, a near-full-height opening pushed the text past the envelope's top
        # edge, which is the overhang this file's other glyphs already guard.
        ty = oy - 2.2 if (oy - v.y) > 3.4 else oy + 3.0
        canvas.add(Text(v.x + v.w * 0.5, ty, caption, L_TEXT, T_CAPTION, "middle"))
        return "drawn"

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        canvas.add(Text(x + w * 0.5, y + h * 0.92, "MAXIMUM COMPONENT ENVELOPE",
                        L_TEXT, T_BODY, "middle", bold=True))
        # Hook / hanging point at the top centre: the component hangs from the
        # conveyor, so the envelope top IS the hook line.
        hx = x + w * 0.5
        hr = min(w, h) * 0.035
        canvas.add(Circle(hx, y - hr - 2.0, hr,
                          EQUIPMENT.layer, EQUIPMENT.width))
        canvas.add(Line(hx, y - 2.0, hx, y + h * 0.06, *SYMBOL_DETAIL))
        canvas.add(Line(x - 6.0, y - hr - 2.0, x + w + 6.0, y - hr - 2.0,
                        *CENTRE_LINE))
        track_txt = f" ({track} m track)" if track else ""
        item(canvas, legend, x + w * 0.14, y + h * 0.10,
             _clip(f"Conveyor hook line - {handling}".strip(" -") or "Conveyor hook line") + track_txt)
        _opening(front, booth_m, "BOOTH INNER OPENING")

    if side:
        # THE OVEN OPENING WAS PARSED AND NEVER DRAWN. A component has to clear
        # BOTH apertures, and the curing oven's inner size is resolved from the
        # same composite field the booth's is — showing only the booth told the
        # reader half the constraint. The side view takes the oven so the two
        # views are complementary rather than duplicates.
        if oven_m:
            _opening(side, oven_m, "CURING OVEN INNER OPENING")
        else:
            _opening(side, booth_m, "BOOTH INNER OPENING")

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        # PROCESS SEQUENCE. What is real here is the ORDER the component passes
        # through the plant — the same class of fact as an airflow arrow. The
        # module POSITIONS and spacings are not engineered (Vitech has supplied
        # no setting-out rules), so the blocks are equal-width, captioned
        # SCHEMATIC and never dimensioned. Only stations the spec actually
        # resolved appear; a TBD pretreatment is not drawn as if it existed.
        stations = ["LOAD"]
        if _resolved(pretreat):
            stations.append("PRETREATMENT")
        if _resolved(booth):
            stations.append("POWDER BOOTH")
        if _resolved(oven):
            stations.append("CURING OVEN")
        stations.append("UNLOAD")

        cy = y + h * 0.30
        # Below ~60 mm of drawn width the blocks cannot hold legible text, so
        # the view falls back to the plain direction arrow rather than emitting
        # a row of unreadable boxes.
        if len(stations) >= 3 and w >= 60.0:
            band_h = min(h * 0.24, 13.0)
            band_y = cy - band_h / 2
            gap = w * 0.03
            span = w * 0.90
            bw = (span - gap * (len(stations) - 1)) / len(stations)
            bx0 = x + (w - span) / 2
            for i, name in enumerate(stations):
                bx = bx0 + i * (bw + gap)
                canvas.add(Rect(bx, band_y, bw, band_h, *EQUIPMENT))
                canvas.add(Text(bx + bw / 2, band_y + band_h * 0.60,
                                name[:max(3, int(bw / 1.25))], L_TEXT, T_TINY, "middle"))
                if i:
                    canvas.add(poly([(bx, cy), (bx - gap * 0.85, cy - 1.4),
                                     (bx - gap * 0.85, cy + 1.4)],
                                    SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width, "currentColor"))
            canvas.add(Text(x + w * 0.5, band_y - 2.6,
                            "PROCESS SEQUENCE - SCHEMATIC, NOT TO SCALE",
                            L_TEXT, T_CAPTION, "middle"))
            item(canvas, legend, x + w * 0.06, band_y + band_h + 5.0,
                 f"Plant process line ({len(stations)} stations)")
        else:
            canvas.add(Line(x + w * 0.12, cy, x + w * 0.84, cy,
                            *CENTRE_LINE))
            canvas.add(poly([(x + w * 0.88, cy), (x + w * 0.84, cy - 1.6),
                             (x + w * 0.84, cy + 1.6)], SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width, "currentColor"))
            canvas.add(Text(x + w * 0.5, cy - 2.2, "DIRECTION OF TRAVEL", L_TEXT, T_CAPTION, "middle"))
            item(canvas, legend, x + w * 0.16, cy + 5.5, "Plant line direction")

    # A reused module SMALLER than the component it must accept is a real
    # engineering finding, and the sheet is where an engineer will notice it.
    # Reported as a question, never silently corrected — the fix is the client's
    # to make (a bigger booth, or a different source design).
    env_m = None
    if front and front.model_w and front.model_h:
        env_m = {front.w_axis: front.model_w / 1000.0, front.h_axis: front.model_h / 1000.0}
        if side and side.model_w:
            env_m.setdefault(side.w_axis, side.model_w / 1000.0)
    # BOTH apertures are checked. The component must pass through the booth AND
    # the curing oven; testing only the booth would clear a component that the
    # oven cannot take, which is the more expensive of the two to discover late.
    for _ap_m, _ap_name in ((booth_m, "booth"), (oven_m, "curing oven")):
        if not (_ap_m and env_m):
            continue
        named = {"length": _ap_m[0], "width": _ap_m[1], "height": _ap_m[2]}
        tight = [a for a, v in env_m.items() if named.get(a) and named[a] < v - 0.01]
        if tight:
            note_item(legend, f"CHECK: component exceeds reused {_ap_name} opening "
                              f"on {', '.join(tight)} - confirm {_ap_name} size")

    # The modules themselves are real resolved values but have no engineered
    # setting-out, so they are scheduled in the legend rather than drawn.
    # No truncation here: the sheet's own column wraps these, and cutting the
    # text early is what printed half-values like "Operating temp (".
    for label, value in (("Powder coating booth", booth),
                         ("Powder recovery", recovery),
                         ("Curing oven", oven),
                         ("Material handling", handling)):
        if _resolved(value):
            note_item(legend, f"{label}: {value}")
    if views.get("side"):
        # The end view of a plant is its tallest station's enclosure, with the
        # conveyor aperture through it. The envelope here is the MAXIMUM
        # COMPONENT envelope, not a plant footprint, and the front view already
        # says so — this adds no new claim, only the shape of that component.
        _side_enclosure(canvas, views["side"], roof_plant=True, opening=True)
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
        canvas.add(Line(x, ty, x + w, ty, *EQUIPMENT))
        canvas.add(Line(x, ty + 1.6, x + w, ty + 1.6, *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.08, ty - 5.0,
             f"Track - {ctype or 'overhead conveyor'} {moc}".strip(),
             to=(x + w * 0.08, ty))

        # Carriers at an indicative pitch (no engineered pitch is given).
        for i in range(8):
            cx = x + w * (i + 0.5) / 8
            canvas.add(Line(cx, ty + 1.6, cx, y + h * 0.55, *SYMBOL_DETAIL))
            canvas.add(Line(cx - w * 0.012, y + h * 0.55, cx + w * 0.012, y + h * 0.55,
                            *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.5, y + h * 0.62,
             "Carrier / hanger - pitch indicative",
             to=(x + w * 0.4375, y + h * 0.55))

        # Drive unit at the far end.
        dwid, dhei = w * 0.06, h * 0.10
        components.motor_box(canvas, x + w - dwid, ty - dhei, dwid, dhei)
        item(canvas, legend, x + w - dwid - 5.5, ty - dhei * 0.5,
             f"Drive unit - {operation or 'drive'}".strip(),
             to=(x + w - dwid, ty - dhei * 0.5))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        cy = y + h / 2
        # The track in plan is its two rails about the axis, with the carriers
        # on the SAME pitch the elevation draws them at — the two views were
        # showing different machines, one with eight carriers and one with none.
        rail = min(h * 0.10, 3.0)
        canvas.add(Line(x, cy - rail, x + w, cy - rail, *EQUIPMENT),
                   Line(x, cy + rail, x + w, cy + rail, *EQUIPMENT))
        canvas.add(Line(x, cy, x + w, cy, *CENTRE_LINE))
        for i in range(8):
            cxp = x + w * (i + 0.5) / 8
            canvas.add(Circle(cxp, cy, rail * 0.55,
                              INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
        # Drive at the far end, matching the elevation's drive unit.
        components.motor_box(canvas, x + w - w * 0.06, cy + rail * 1.4,
                             w * 0.05, min(h * 0.16, 5.0))
        canvas.add(Text(x + w * 0.5, cy - rail - 2.4,
                        "TRACK CENTRE LINE - ROUTING INDICATIVE",
                        L_TEXT, T_CAPTION, "middle"))

    if side:
        x, y, w, h = side.x, side.y, side.w, side.h
        # Track section on the side elevation.
        canvas.add(Line(x + w * 0.5 - w * 0.22, y + h * 0.12, x + w * 0.5 + w * 0.22,
                        y + h * 0.12, *EQUIPMENT))
        canvas.add(Line(x + w * 0.5, y + h * 0.12, x + w * 0.5, y + h * 0.55,
                        *SYMBOL_DETAIL))
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
        # Joint lines, NOT `components.flange`. That component projects 0.62 of
        # the BORE either side, which is right for a real flange — and wrong
        # here, because this elevation draws the run at the envelope height
        # (4,000 mm), not at the duct bore (600 mm). Fed the view height it
        # overshot the outline by a fifth and struck the view caption. A
        # component only fits where the view is drawn at the size it assumes.
        for i in range(1, 8):
            jx = x + w * i / 8
            canvas.add(Line(jx, y - 1.6, jx, y + h + 1.6, *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.5, y + h * 0.5, f"Flanged duct spool {material}".strip())
        canvas.add(Text(x + w * 0.5, y - 4.0, "DEVELOPED LENGTH - ROUTING NOT SHOWN",
                        L_TEXT, T_DIM, "middle"))

    if side:
        x, y, w, h = side.x, side.y, side.w, side.h
        canvas.add(Circle(x + w / 2, y + h / 2, min(w, h) * 0.42,
                          DUCT.layer, DUCT.width))
        item(canvas, legend, x + w * 0.5, y + h * 0.5, f"Duct section {duct}".strip(),
             to=(x + w / 2 + min(w, h) * 0.42, y + h / 2))

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        cy = y + h / 2
        # A duct in plan is its two walls about the axis, not a bare centre
        # line — and the joints are the same spool pitch the elevation uses, so
        # the two views describe one run rather than two.
        components.duct_run(canvas, x, cy, x + w, cy, min(h * 0.55, w * 0.10))
        bore = min(h * 0.55, w * 0.10)
        for i in range(1, 8):
            jx = x + w * i / 8
            canvas.add(Line(jx, cy - bore * 0.62, jx, cy + bore * 0.62,
                            *SYMBOL_DETAIL))
    return legend


# --------------------------------------------------------------------------
def cleaning_room(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Cleaning room GA: sealed lit enclosure, door, ceiling inlet filters and
    a low-level extract face."""
    legend: list[tuple[str, str]] = []
    lights = _nos(_find(rows, "illumination"), 0)
    front, plan = views.get("front"), views.get("plan")

    if front:
        _door(canvas, front, legend, "Personnel / component door, double leaf")
        _lights(canvas, front, lights, legend, _luminaire_label(rows))
        # Ceiling inlet plenum: a room is supplied from above and extracted low.
        canvas.add(Rect(front.x, front.y, front.w, front.h * 0.05, *SYMBOL_DETAIL))
        canvas.add(Text(front.x + front.w * 0.5, front.y + front.h * 0.28,
                        "CLEANING ROOM", L_TEXT, T_BODY, "middle"))
    if plan:
        depth = _filter_bank(canvas, plan, 0, legend, "Extract filter face")
        _fan(canvas, plan, depth, legend, _blower_label(rows))
        canvas.add(Line(plan.x, plan.y + plan.h * 0.10, plan.x + plan.w,
                        plan.y + plan.h * 0.10, *HIDDEN_LINE))
        canvas.add(Text(plan.x + plan.w * 0.5, plan.y + plan.h * 0.075,
                        "FILTERED AIR INLET SIDE", L_TEXT, T_CAPTION, "middle"))
    if views.get("side"):
        _side_enclosure(canvas, views["side"], roof_plant=True)
    return legend


# --------------------------------------------------------------------------
def buffing_booth(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Buffing booth GA: open working face, dust filter bank and extract fan."""
    legend: list[tuple[str, str]] = []
    lights = _nos(_find(rows, "illumination"), 0)
    filters = _nos(_find(rows, "paper filter"), 0) or _nos(_find(rows, "filter"), 0)
    front, plan = views.get("front"), views.get("plan")

    if front:
        # Open working face rather than a door: the operator works into it.
        oy = front.y + front.h * 0.20
        canvas.add(Rect(front.x + front.w * 0.10, oy, front.w * 0.80,
                        front.h * 0.66, *OPENING))
        canvas.add(Text(front.x + front.w * 0.5, oy + front.h * 0.36,
                        "OPEN WORKING FACE", L_TEXT, T_SMALL, "middle"))
        item(canvas, legend, front.x + front.w * 0.16, oy + front.h * 0.10, "Open working face (operator side)")
        _lights(canvas, front, lights, legend, _luminaire_label(rows))
    if plan:
        depth = _filter_bank(canvas, plan, filters, legend, "Dust arresting filter bank")
        _fan(canvas, plan, depth, legend, _blower_label(rows))
    if views.get("side"):
        _side_enclosure(canvas, views["side"], opening=True)
    return legend


# --------------------------------------------------------------------------
def flash_off_zone(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Flash off zone GA: a through-tunnel, open both ends, extracted at roof."""
    legend: list[tuple[str, str]] = []
    lights = _nos(_find(rows, "illumination"), 0)
    front, plan = views.get("front"), views.get("plan")

    if front:
        # Entry and exit openings: a flash off zone is a pass-through.
        ow = front.w * 0.12
        oh = front.h * 0.60
        oy = front.y + front.h - oh
        for ox in (front.x, front.x + front.w - ow):
            canvas.add(Rect(ox, oy, ow, oh, *OPENING))
        item(canvas, legend, front.x + ow * 0.5, oy - 5.0,
             "Component entry / exit opening", to=(front.x + ow * 0.5, oy))
        # Roof extract plenum.
        canvas.add(Rect(front.x + front.w * 0.20, front.y, front.w * 0.60,
                        front.h * 0.10, *EQUIPMENT))
        item(canvas, legend, front.x + front.w * 0.5, front.y + front.h * 0.16,
             f"Roof extract plenum - {_blower_label(rows)}".strip(" -"),
             to=(front.x + front.w * 0.5, front.y + front.h * 0.10))
        _lights(canvas, front, lights, legend, _luminaire_label(rows))
    if plan:
        cy = plan.y + plan.h / 2
        canvas.add(Line(plan.x, cy, plan.x + plan.w, cy, *CENTRE_LINE))
        canvas.add(poly([(plan.x + plan.w * 0.90, cy), (plan.x + plan.w * 0.84, cy - 1.8),
                         (plan.x + plan.w * 0.84, cy + 1.8)],
                        SYMBOL_DETAIL.layer, SYMBOL_DETAIL.width, "currentColor"))
        canvas.add(Text(plan.x + plan.w * 0.5, cy - 2.2, "DIRECTION OF TRAVEL",
                        L_TEXT, T_CAPTION, "middle"))
        item(canvas, legend, plan.x + plan.w * 0.16, cy + 5.5,
             "Conveyor / trolley line through zone",
             to=(plan.x + plan.w * 0.16, cy))
    if views.get("side"):
        _side_enclosure(canvas, views["side"], extract=False,
                        roof_plant=True, opening=True)
    return legend


# --------------------------------------------------------------------------
def paint_drying_oven(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Paint drying oven GA: insulated enclosure, heater, recirculation and the
    exhaust stack. Shares the hot air oven's drafting vocabulary but reads the
    paint-shop template's own labels."""
    legend: list[tuple[str, str]] = []
    insulation = _find(rows, "insulation") or ""
    heating = _find(rows, "heating mode") or _find(rows, "heat load") or ""
    lights = _nos(_find(rows, "illumination"), 0)
    front, plan = views.get("front"), views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        t = min(w, h) * 0.05
        canvas.add(Rect(x + t, y + t, w - 2 * t, h - 2 * t, *PANEL_SEAM))
        item(canvas, legend, x + w * 0.07, y + h * 0.42,
             f"Insulated panel lining {insulation}".strip(),
             to=(x + t, y + h * 0.42))

        # Heater / air-handling unit against the end wall.
        hb_w, hb_h = w * 0.18, h * 0.30
        canvas.add(Rect(x + t + w * 0.03, y + h - t - hb_h, hb_w, hb_h,
                        *EQUIPMENT))
        canvas.add(Circle(x + t + w * 0.03 + hb_w / 2, y + h - t - hb_h / 2,
                          min(hb_w, hb_h) * 0.26,
                          INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))
        item(canvas, legend, x + t + w * 0.03 + hb_w + 6.0, y + h - t - hb_h * 0.5,
             f"Heating / recirculation unit {heating}".strip(),
             to=(x + t + w * 0.03 + hb_w, y + h - t - hb_h * 0.5))

        # Exhaust stack rising off the roof, drawn inside the sheet.
        sx = x + w * 0.72
        canvas.add(Line(sx, y + t, sx, y + h * 0.30, *DUCT),
                   Line(sx + w * 0.03, y + t, sx + w * 0.03, y + h * 0.30,
                        *DUCT))
        item(canvas, legend, sx + w * 0.09, y + h * 0.22, "Exhaust stack",
             to=(sx + w * 0.03, y + h * 0.22))
        _lights(canvas, front, lights, legend, _luminaire_label(rows))
    if plan:
        t = min(plan.w, plan.h) * 0.05
        canvas.add(Rect(plan.x + t, plan.y + t, plan.w - 2 * t, plan.h - 2 * t,
                        *PANEL_SEAM))
        # The plan carried the lining and a conveyor line and nothing else, so
        # it showed none of the plant the elevation draws. Both are projected
        # down here: the heating/recirculation unit against the end wall, and
        # the exhaust stack. Nothing appears in plan that the elevation lacks.
        px, py, pw, ph = plan.x, plan.y, plan.w, plan.h
        hu_w, hu_d = pw * 0.18, ph * 0.30
        canvas.add(Rect(px + t + pw * 0.03, py + t + ph * 0.06, hu_w, hu_d,
                        *EQUIPMENT))
        components.blower(canvas, px + t + pw * 0.03 + hu_w / 2,
                          py + t + ph * 0.06 + hu_d / 2,
                          min(hu_w, hu_d) * 0.30, discharge="right", motor=False)
        canvas.add(Circle(px + pw * 0.72, py + ph * 0.18,
                          min(pw, ph) * 0.045,
                          EQUIPMENT.layer, EQUIPMENT.width))
        canvas.add(Text(px + pw * 0.72, py + ph * 0.10, "STACK",
                        L_TEXT, T_TINY, "middle"))
        cy = plan.y + plan.h * 0.72
        canvas.add(Line(plan.x + t, cy, plan.x + plan.w - t, cy,
                        *CENTRE_LINE))
        canvas.add(Text(plan.x + plan.w * 0.5, cy - 2.0, "CONVEYOR CENTRE LINE",
                        L_TEXT, T_CAPTION, "middle"))
    if views.get("side"):
        _side_enclosure(canvas, views["side"], extract=False, roof_plant=True,
                        lining=True, opening=True)
    return legend


# --------------------------------------------------------------------------
def blast_booth(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Blast booth GA: blast enclosure, hopper floor for media recovery, door,
    lighting and the dust take-off."""
    legend: list[tuple[str, str]] = []
    lights = _nos(_find(rows, "illumination"), 0)
    media = _find(rows, "blast media") or _find(rows, "media") or ""
    recovery = _find(rows, "recovery") or ""
    front, plan = views.get("front"), views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Hopper / screw-recovery floor: the defining feature of a blast booth.
        hop_h = h * 0.22
        hy = y + h - hop_h
        canvas.add(poly([(x, hy), (x + w, hy), (x + w * 0.56, y + h),
                         (x + w * 0.44, y + h)], EQUIPMENT.layer, EQUIPMENT.width))
        item(canvas, legend, x + w * 0.16, hy + hop_h * 0.30,
             f"Media recovery hopper {recovery}".strip(), to=(x + w * 0.16, hy))

        _door(canvas, front, legend, "Blast enclosure door", frac=0.28)
        _lights(canvas, front, lights, legend, _luminaire_label(rows))
        # Clear of the door head. At 0.30 this printed straight through the top
        # edge of the door, whose head is at 0.28 — the caption and the leaf
        # outline crossed and neither read cleanly.
        canvas.add(Text(x + w * 0.5, y + h * 0.22,
                        f"BLAST MEDIA: {str(media).upper()[:24]}" if media else "BLAST ENCLOSURE",
                        L_TEXT, T_SMALL, "middle"))
    if plan:
        depth = _filter_bank(canvas, plan, 0, legend, "Dust take-off face")
        _fan(canvas, plan, depth, legend,
             _blower_label(rows) or "Dust collector connection")
    if views.get("side"):
        sv = views["side"]
        _side_enclosure(canvas, sv)
        # The recovery hopper is the defining feature, so it reads on the side
        # too: the floor falls to a centre trough.
        hop_h = sv.h * 0.20
        hy = sv.y + sv.h - hop_h
        canvas.add(poly([(sv.x, hy), (sv.x + sv.w, hy),
                         (sv.x + sv.w * 0.58, sv.y + sv.h),
                         (sv.x + sv.w * 0.42, sv.y + sv.h)],
                        EQUIPMENT.layer, EQUIPMENT.width))
    return legend


# --------------------------------------------------------------------------
def pretreatment_plant(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Pretreatment plant GA: the process tank line.

    The number of tanks is drawn ONLY when the spec states a stage count. With
    no count the line is shown as a single labelled envelope rather than an
    invented number of tanks.
    """
    legend: list[tuple[str, str]] = []
    stages = _count_in(rows, "stage") or _count_in(rows, "process")
    tank_moc = _find(rows, "tank", "moc") or ""
    tank_size = _find(rows, "tank size") or ""
    front, plan = views.get("front"), views.get("plan")

    if plan:
        x, y, w, h = plan.x, plan.y, plan.w, plan.h
        if stages:
            for i in range(stages):
                tx = x + w * i / stages
                tw = w / stages - w * 0.02 / stages
                canvas.add(Rect(tx + w * 0.01 / stages, y + h * 0.16,
                                tw, h * 0.68, *EQUIPMENT))
                # NUMBER each tank. The stage COUNT is resolved, so the
                # sequence is real engineering; an unnumbered row of identical
                # boxes tells a reader there are five of something and nothing
                # about the order they are used in.
                if tw > 5.0:
                    canvas.add(Text(tx + w * 0.01 / stages + tw / 2,
                                    y + h * 0.30, str(i + 1),
                                    L_TEXT, T_BODY, "middle", bold=True))
                # Liquid in each tank, in the horizontal hatch a section uses.
                # The plan cuts the tank line at working level, which is what
                # the front elevation's own working-level line already says.
                detailing.material_hatch(canvas, tx + w * 0.01 / stages + tw * 0.10,
                                         y + h * 0.40, tw * 0.80, h * 0.36,
                                         detailing.LIQUID)
            item(canvas, legend, x + w * 0.5, y + h * 0.08,
                 f"Process tank ({stages} stages) {tank_moc}".strip(),
                 to=(x + w * 0.5, y + h * 0.16))
        else:
            canvas.add(Text(x + w * 0.5, y + h * 0.5,
                            "PROCESS TANK LINE - STAGE COUNT TBD",
                            L_TEXT, T_BODY, "middle", bold=True))
            note_item(legend, f"Process tank line {tank_moc}".strip())
        # Component travel along the line.
        cy = y + h * 0.92
        canvas.add(Line(x, cy, x + w, cy, *CENTRE_LINE))
        canvas.add(Text(x + w * 0.5, cy - 2.0, "HOIST / CONVEYOR TRAVEL",
                        L_TEXT, T_CAPTION, "middle"))
    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Tank tops at a common working level.
        canvas.add(Line(x, y + h * 0.34, x + w, y + h * 0.34, *EQUIPMENT))
        if stages:
            for i in range(1, stages):
                sx = x + w * i / stages
                canvas.add(Line(sx, y + h * 0.34, sx, y + h, *PANEL_SEAM))
        item(canvas, legend, x + w * 0.10, y + h * 0.24,
             f"Tank working level {tank_size}".strip(),
             to=(x + w * 0.10, y + h * 0.34))
    if views.get("side"):
        sv = views["side"]
        # An end view of a tank line is ONE tank in section: shell, liquid
        # level, and the hoist rail over it.
        ty = sv.y + sv.h * 0.34
        canvas.add(Rect(sv.x + sv.w * 0.10, ty, sv.w * 0.80, sv.h * 0.56,
                        *EQUIPMENT))
        canvas.add(Line(sv.x + sv.w * 0.10, ty + sv.h * 0.10,
                        sv.x + sv.w * 0.90, ty + sv.h * 0.10, *HIDDEN_LINE))
        canvas.add(Line(sv.x + sv.w * 0.5, sv.y + sv.h * 0.06,
                        sv.x + sv.w * 0.5, ty, *CENTRE_LINE))
        canvas.add(Line(sv.x + sv.w * 0.24, sv.y + sv.h * 0.06,
                        sv.x + sv.w * 0.76, sv.y + sv.h * 0.06, *EQUIPMENT))
        _floor(canvas, sv, None, label=False)
    return legend


# --------------------------------------------------------------------------
def fume_extraction(canvas, views: dict, rows: list) -> list[tuple[str, str]]:
    """Fume extraction GA: capture hoods on a branch header to the extract fan.

    Hoods are drawn to the stated number of capture points; with none stated
    the header is drawn without hoods rather than with a guessed quantity.
    """
    legend: list[tuple[str, str]] = []
    points = _count_in(rows, "capture") or _count_in(rows, "suction point")
    duct = _find(rows, "exhaust duct") or _find(rows, "duct") or ""
    front, plan = views.get("front"), views.get("plan")

    if front:
        x, y, w, h = front.x, front.y, front.w, front.h
        # Main header at high level, hoods dropping off it.
        hy = y + h * 0.16
        canvas.add(Line(x, hy, x + w, hy, *DUCT),
                   Line(x, hy + 2.0, x + w, hy + 2.0, *SYMBOL_DETAIL))
        item(canvas, legend, x + w * 0.08, hy - 5.0, f"Extract header {duct}".strip(),
             to=(x + w * 0.08, hy))

        if points:
            shown = min(points, 8)
            for i in range(shown):
                hx = x + w * (i + 0.5) / shown
                canvas.add(Line(hx, hy + 2.0, hx, y + h * 0.52, *SYMBOL_DETAIL))
                canvas.add(poly([(hx - w * 0.03, y + h * 0.66), (hx + w * 0.03, y + h * 0.66),
                                 (hx + w * 0.008, y + h * 0.52), (hx - w * 0.008, y + h * 0.52)],
                                EQUIPMENT.layer, EQUIPMENT.width))
            item(canvas, legend, x + w * 0.5, y + h * 0.76, f"Capture hood ({points} nos)",
                 to=(x + w * (shown // 2 + 0.5) / shown, y + h * 0.66))
    if plan:
        depth = _filter_bank(canvas, plan, 0, legend, "Plant / collector connection")
        _fan(canvas, plan, depth, legend, _blower_label(rows))
    if views.get("side"):
        sv = views["side"]
        # A header run seen end-on is its bore, with one hood below it.
        hy = sv.y + sv.h * 0.16
        components.duct_run(canvas, sv.x + sv.w * 0.5, hy,
                            sv.x + sv.w * 0.5, sv.y + sv.h * 0.44,
                            sv.w * 0.16)
        canvas.add(poly([(sv.x + sv.w * 0.30, sv.y + sv.h * 0.60),
                         (sv.x + sv.w * 0.70, sv.y + sv.h * 0.60),
                         (sv.x + sv.w * 0.56, sv.y + sv.h * 0.44),
                         (sv.x + sv.w * 0.44, sv.y + sv.h * 0.44)],
                        EQUIPMENT.layer, EQUIPMENT.width))
        _floor(canvas, sv, None, label=False)
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
    "cleaning_room": cleaning_room,
    "buffing_booth": buffing_booth,
    "flash_off_zone": flash_off_zone,
    "paint_drying_oven": paint_drying_oven,
    "blast_booth": blast_booth,
    "pretreatment_plant": pretreatment_plant,
    "fume_extraction": fume_extraction,
}


def draw_components(canvas, category: str, views: dict, rows: list) -> list[tuple[str, str]]:
    """Draw the category's component glyphs; returns the legend rows.

    The DRAFTING furniture that is true of every category — the cutting plane
    for whichever view is a section, and the floor/height datums — is applied
    here rather than repeated in fourteen glyphs. Both are drawn from values the
    sheet already carries, so neither adds an engineering claim.
    """
    legend = SYMBOLS.get(category, generic)(canvas, views, rows)

    _section_mark(canvas, views.get("plan"), category)
    for key in ("front", "side"):
        v = views.get(key)
        # Only on a view drawn to a real height. A schematic's views carry no
        # model dimensions, and a level marker there would be the one thing on
        # that sheet claiming a number.
        if v is not None and v.model_h:
            _levels(canvas, v)
    return legend
