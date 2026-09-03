"""Automated drawing QA: read the SHEET back and report what is wrong with it.

WHY THIS EXISTS, and why it is not just more tests. Every defect this engine has
shipped was invisible in the source and obvious on the paper — a caption through
a door head, an arrowhead on a dimension, a filter bank with no elements, a view
that was simply empty. Each was found by a person rendering a sheet and looking
at it, one sheet at a time. That does not scale to fourteen categories times
three drawing states times two sheet sizes, and it never catches the sheet
nobody happened to render.

So this audits the OUTPUT rather than the code: it takes the finished canvas and
asks the questions a checker would ask of a drawing handed to them. It found the
dust collector's 6-element plan by counting, not by looking.

THE ONE THAT MATTERS MOST is `dimension_not_true`. A dimension is the only mark
on a GA a fabricator can work from, so a dimension whose printed value does not
match the distance it actually spans — at the sheet's own scale — is the single
most dangerous thing this engine could emit. It is golden rule #2 expressed as
an audit: not "did a model invent a number?" but "does this number describe the
geometry it is attached to?"

WHAT THIS IS NOT. It cannot judge whether an arrangement is good engineering,
whether a component belongs where it is drawn, or whether the machine will work.
It checks that the DRAWING is well formed and self-consistent. The engineering
review is still a person's job, which is what the standing notes say.
"""
import math
import re
from typing import NamedTuple, Optional

from . import sheet as sheet_mod
from . import states, symbols, views as views_mod
from .primitives import (L_BORDER, L_COMPONENT, L_DIM, L_HIDDEN, L_OUTLINE,
                         L_TEXT, L_TITLE, Circle, Line, Path, Rect, Text)
from .style import (CHAR_W_BOLD_MEASURED, CHAR_W_REG_MEASURED, MIN_LEGIBLE_MM)

ERROR = "error"
WARNING = "warning"


class Finding(NamedTuple):
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper():7}] {self.code}: {self.message}"


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def _anchor(s) -> Optional[tuple]:
    """A shape's representative point, for asking which view it belongs to."""
    if isinstance(s, Text) or isinstance(s, Circle):
        return (s.x, s.y) if isinstance(s, Text) else (s.cx, s.cy)
    if isinstance(s, Rect):
        return (s.x + s.w / 2, s.y + s.h / 2)
    if isinstance(s, Line):
        return ((s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2)
    if isinstance(s, Path) and getattr(s, "pts", None):
        xs = [p[0] for p in s.pts]
        ys = [p[1] for p in s.pts]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    return None


def _extent(s) -> Optional[tuple]:
    """A shape's bounding box (x0, y0, x1, y1), or None if it has no extent."""
    if isinstance(s, Text):
        w = _text_width(s)
        x0 = {"middle": s.x - w / 2, "end": s.x - w}.get(s.anchor, s.x)
        # SVG text sits ON its baseline, so the box runs upward from y.
        box = (x0, s.y - s.size, x0 + w, s.y + s.size * 0.25)
        rot = float(getattr(s, "rotate", 0.0) or 0.0)
        if not rot:
            return box
        # ROTATED TEXT OCCUPIES A DIFFERENT BOX, and treating it as horizontal
        # is not a small error: a 26 mm vertical caption read as 26 mm of
        # WIDTH swept across a quarter of the sheet and reported collisions
        # that were not there. Rotate the four corners about the anchor and
        # take their extent — correct for any angle, not just the right ones.
        a = math.radians(rot)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for px, py in ((box[0], box[1]), (box[2], box[1]),
                       (box[2], box[3]), (box[0], box[3])):
            dx, dy = px - s.x, py - s.y
            pts.append((s.x + dx * ca - dy * sa, s.y + dx * sa + dy * ca))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))
    if isinstance(s, Circle):
        return (s.cx - s.r, s.cy - s.r, s.cx + s.r, s.cy + s.r)
    if isinstance(s, Rect):
        return (s.x, s.y, s.x + s.w, s.y + s.h)
    if isinstance(s, Line):
        return (min(s.x1, s.x2), min(s.y1, s.y2), max(s.x1, s.x2), max(s.y1, s.y2))
    if isinstance(s, Path) and getattr(s, "pts", None):
        xs = [p[0] for p in s.pts]
        ys = [p[1] for p in s.pts]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def _text_width(t: Text) -> float:
    ratio = CHAR_W_BOLD_MEASURED if t.bold else CHAR_W_REG_MEASURED
    return len(t.text) * t.size * ratio


def _overlap(a: tuple, b: tuple, pad: float = 0.0) -> bool:
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _in_box(pt: tuple, box, pad: float = 2.0) -> bool:
    return (box.x - pad <= pt[0] <= box.x + box.w + pad
            and box.y - pad <= pt[1] <= box.y + box.h + pad)


# --------------------------------------------------------------------------
# the audit
# --------------------------------------------------------------------------
# A view carrying fewer than this many of the glyph's own shapes is either
# unfinished or drawing nothing the reader can use. Set from the census: the
# thin glyphs sat at 1-6 and the finished ones at 15-120, so the gap is wide
# and the threshold is not delicate.
SPARSE_VIEW = 8
EMPTY_VIEW = 2

# A dimension's printed value must match the distance it spans, at the sheet's
# scale, to within this. The tolerance exists only for rounding in the printed
# integer, not to excuse a dimension of the wrong feature.
DIM_TOLERANCE = 0.02

_NUM_RE = re.compile(r"^\s*[Ø]?\s*(\d+(?:\.\d+)?)\s*$")
_SECTION_RE = re.compile(r"^SECTION\s+([A-Z])-\1$")
# The sheet says "dropped rows" in more than one wording, and a checker that
# knows only one of them reports a clean sheet while rows are missing. Both the
# side column's "... and N more" and the unresolved table's "N further item(s)"
# must match, which is why this is two alternatives rather than one phrase.
_TRUNCATED_RE = re.compile(
    r"\.\.\.\s*and\s+(\d+)\s+(?:more|further)"
    r"|(?:^|\s)(\d+)\s+further\s+item", re.I)


def audit(spec: dict, sheet_size: str = None, drawing_type: str = "ga") -> list:
    """Build the sheet and report every defect the checks below can see."""
    from .drawing_service import compose          # local: avoids a cycle

    size = sheet_size or sheet_mod.DEFAULT_SIZE
    canvas, pkg = compose(spec, sheet_size=size, drawing_type=drawing_type)
    sw, sh = sheet_mod.SHEET_SIZES[size]
    ax, ay, aw, ah = sheet_mod.drawing_area(sw, sh)

    env = (spec.get("geometry") or {}).get("envelope_mm") or {}
    gstate = states.classify(env)
    scale = pkg.get("scale_divisor") or 1
    schematic = pkg.get("state") == states.SCHEMATIC

    placed = views_mod.layout(env, ax, ay, aw, ah, scale, drawing_type)
    out: list = []

    out += _check_views(canvas, placed, schematic, pkg)
    out += _check_text_legible(canvas)
    out += _check_dim_overlap(canvas)
    out += _check_dims_true(canvas, scale, schematic)
    out += _check_section_planes(canvas)
    out += _check_truncation(canvas, pkg)
    out += _check_bounds(canvas, sw, sh, ax, ay, aw, ah)
    out += _check_leaders(canvas)
    return out


# --- 1 + 8: empty and suspiciously sparse views ---------------------------
def _check_views(canvas, placed, schematic: bool, pkg: dict) -> list:
    """Count the GLYPH's shapes inside each view box.

    The view's own furniture — outline, centre lines, dimensions, caption — is
    excluded, because those are drawn for every view whether or not the glyph
    contributed anything. Counting them is how an empty view passes an audit.
    """
    if schematic:
        # A schematic deliberately draws little: nominal boxes and the symbol.
        # Auditing it for density would report the honest case as a defect.
        return []
    out = []
    for v in placed:
        n = 0
        for s in canvas.shapes:
            if s.layer in (L_DIM, L_BORDER, L_TITLE):
                continue
            if s.layer == L_OUTLINE and isinstance(s, Rect):
                continue                     # the view's own envelope
            pt = _anchor(s)
            if pt and _in_box(pt, v, pad=1.0):
                n += 1
        if n <= EMPTY_VIEW:
            out.append(Finding(ERROR, "empty_view",
                               f"{v.key} view is empty ({n} glyph shapes) - "
                               f"the outline and its dimensions are real, so a "
                               f"reader takes the emptiness as a statement"))
        elif n < SPARSE_VIEW:
            out.append(Finding(WARNING, "sparse_view",
                               f"{v.key} view carries only {n} glyph shapes "
                               f"(expected >= {SPARSE_VIEW})"))
    return out


# --- 2: illegible text ----------------------------------------------------
def _check_text_legible(canvas) -> list:
    out = []
    seen = set()
    for s in canvas.shapes:
        if not isinstance(s, Text):
            continue
        if not str(s.text).strip():
            out.append(Finding(WARNING, "empty_text",
                               f"an empty text is emitted at ({s.x:.0f}, {s.y:.0f})"))
            continue
        if s.size < MIN_LEGIBLE_MM - 1e-6:
            key = (round(s.size, 2), s.text[:24])
            if key in seen:
                continue
            seen.add(key)
            out.append(Finding(ERROR, "illegible_text",
                               f"{s.size:.2f} mm text below the {MIN_LEGIBLE_MM} mm "
                               f"legible floor: {s.text[:40]!r}"))
    return out


# --- 3: overlapping dimensions -------------------------------------------
def _check_dim_overlap(canvas) -> list:
    """Two dimension TEXTS sharing sheet space.

    Only dimension text is compared. Dimension LINES crossing each other is
    normal drafting (an extension line runs past its neighbour); two numbers
    printed on top of each other is not, and it is the failure the lane system
    exists to prevent.
    """
    texts = [s for s in canvas.shapes
             if isinstance(s, Text) and s.layer == L_DIM and str(s.text).strip()]
    out = []
    for i, a in enumerate(texts):
        ba = _extent(a)
        for b in texts[i + 1:]:
            bb = _extent(b)
            if ba and bb and _overlap(ba, bb):
                out.append(Finding(ERROR, "dimension_overlap",
                                   f"dimension {a.text!r} and {b.text!r} overlap "
                                   f"near ({a.x:.0f}, {a.y:.0f})"))
    return out


# --- 4: a dimension must describe the geometry it is attached to ----------
def _check_dims_true(canvas, scale: int, schematic: bool) -> list:
    """THE LOAD-BEARING CHECK. Printed value vs the distance actually spanned.

    A dimension reading 5000 across 100 mm of sheet at 1:50 is true. One reading
    600 across the same 100 mm is not, whatever the spec says 600 is — the value
    is real and the geometry it labels is not, which is the exact trap that
    stopped the filter cells being dimensioned. Non-numeric labels (TBD) are
    skipped: they claim nothing.
    """
    if schematic:
        return []                    # a schematic emits no dimension at all
    out = []
    for d in getattr(canvas, "dims", []):
        m = _NUM_RE.match(str(d.label))
        if not m:
            continue
        claimed = float(m.group(1))
        span = math.hypot(d.x2 - d.x1, d.y2 - d.y1) * scale
        if claimed <= 0 or span <= 0:
            continue
        err = abs(span - claimed) / claimed
        if err > DIM_TOLERANCE:
            out.append(Finding(
                ERROR, "dimension_not_true",
                f"dimension reads {d.label!r} but spans {span:.0f} mm at 1:{scale} "
                f"({err * 100:.0f}% out) - the value may be real, the geometry "
                f"it labels is not"))
    return out


# --- leaders must not be drawn THROUGH text ------------------------------
def _seg_crosses_box(x1, y1, x2, y2, box) -> bool:
    """Does a segment pass through a rectangle? (Liang-Barsky, clipped.)"""
    x0, y0, x3, y3 = box
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - x0), (dx, x3 - x1), (-dy, y1 - y0), (dy, y3 - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 < t1


def _check_leaders(canvas) -> list:
    """A balloon leader that runs through a label.

    A leader exists to say WHICH component a number refers to, so one drawn
    across a caption damages both: the caption becomes hard to read and the
    leader looks like it is pointing at the text. This is the collision the
    balloon system cannot prevent by construction, because a glyph chooses the
    balloon position and the caption position independently.
    """
    from .style import LEADER_LINE
    leaders = [s for s in canvas.shapes
               if isinstance(s, Line) and s.layer == LEADER_LINE.layer
               and abs(s.width - LEADER_LINE.width) < 1e-9]
    texts = [s for s in canvas.shapes
             if isinstance(s, Text) and str(s.text).strip()
             and s.layer in (L_TEXT, L_COMPONENT)]
    out = []
    seen = set()
    for ln in leaders:
        for t in texts:
            box = _extent(t)
            # Shrink the box slightly: a leader grazing a descender is not a
            # collision, and reporting those would bury the real ones.
            box = (box[0] + 0.4, box[1] + 0.4, box[2] - 0.4, box[3] - 0.4)
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            if _seg_crosses_box(ln.x1, ln.y1, ln.x2, ln.y2, box):
                key = t.text[:24]
                if key in seen:
                    continue
                seen.add(key)
                out.append(Finding(WARNING, "leader_through_text",
                                   f"a balloon leader crosses the label "
                                   f"{t.text[:36]!r}"))
    return out


# --- 5: a section caption needs a cutting plane ---------------------------
def _check_section_planes(canvas) -> list:
    """A view captioned SECTION A-A must have an A-A mark somewhere on the sheet.

    Otherwise the caption points at a cut nobody can locate, which is worse than
    an unlabelled elevation — the reader looks for a plane that is not there and
    concludes a drawing is missing.
    """
    captions, tags = [], {}
    for s in canvas.shapes:
        if not isinstance(s, Text):
            continue
        t = str(s.text).strip()
        m = _SECTION_RE.match(t)
        if m:
            captions.append(m.group(1))
        elif len(t) == 1 and t.isalpha() and t.isupper():
            tags[t] = tags.get(t, 0) + 1
    out = []
    for tag in sorted(set(captions)):
        # A cutting plane is labelled at BOTH ends, so a located section shows
        # its letter at least twice.
        if tags.get(tag, 0) < 2:
            out.append(Finding(ERROR, "section_without_plane",
                               f"a view is captioned SECTION {tag}-{tag} but the "
                               f"sheet carries {tags.get(tag, 0)} '{tag}' cutting-"
                               f"plane label(s) (needs 2)"))
    return out


# --- 6: truncated schedules ----------------------------------------------
def _check_truncation(canvas, pkg: dict) -> list:
    """A schedule that stopped short, and said so.

    The notice itself is right — dropping rows silently would be far worse. The
    finding is that rows were dropped at all, and it is an ERROR for the
    unresolved/TBD schedule (those rows are what the reader must act on) and a
    WARNING elsewhere (an item list conventionally refers out to a full BOM).
    """
    out = []
    for s in canvas.shapes:
        if not isinstance(s, Text):
            continue
        m = _TRUNCATED_RE.search(str(s.text))
        if not m:
            continue
        txt = str(s.text)
        # ERROR only for the UNRESOLVED schedule: those rows are what the reader
        # has to act on to get a real drawing, so losing them off the bottom of
        # a column is a different kind of failure from an item list that
        # conventionally refers out to a full BOM. The notices name themselves
        # for exactly this reason — keying on the bare word "specification"
        # graded the DESIGN DATA table as an error, which it is not.
        low = txt.lower()
        tbd_like = "unresolved" in low or "sheet space exhausted" in low
        dropped = m.group(1) or m.group(2)
        out.append(Finding(ERROR if tbd_like else WARNING, "schedule_truncated",
                           f"a schedule dropped {dropped} row(s): {txt[:60]!r}"))
    if pkg.get("unresolved") and pkg.get("state") == states.SCHEMATIC:
        # The schematic's whole purpose is to carry the complete list.
        pass
    return out


# --- 7: nothing outside the sheet, or in the reserved zones --------------
def _check_bounds(canvas, sw: float, sh: float,
                  ax: float, ay: float, aw: float, ah: float) -> list:
    """Off-sheet geometry, and drawing-area geometry that has walked into the
    side column or the title block.

    The column and the title block are RESERVED: the notes, the schedules and
    the stationery live there, and a glyph that reaches into them prints on top
    of text a reader needs.
    """
    out = []
    col_x = ax + aw                      # the drawing area's right edge
    for s in canvas.shapes:
        box = _extent(s)
        if not box:
            continue
        x0, y0, x1, y1 = box
        if x0 < -0.5 or y0 < -0.5 or x1 > sw + 0.5 or y1 > sh + 0.5:
            out.append(Finding(ERROR, "off_sheet",
                               f"{type(s).__name__} on layer {s.layer} extends to "
                               f"({x1:.1f}, {y1:.1f}) outside the {sw:.0f}x{sh:.0f} sheet"))
            continue
        # Only equipment layers are policed: the side column's own text and the
        # title block legitimately live to the right of the drawing area.
        if s.layer in (L_COMPONENT, L_OUTLINE, L_HIDDEN) and x0 > col_x + 1.0:
            out.append(Finding(ERROR, "in_reserved_column",
                               f"{type(s).__name__} on layer {s.layer} at "
                               f"x={x0:.1f} has walked into the notes column "
                               f"(drawing area ends at {col_x:.1f})"))
    return out


# --------------------------------------------------------------------------
def summarise(findings: list) -> str:
    errs = sum(1 for f in findings if f.severity == ERROR)
    warns = len(findings) - errs
    return f"{errs} error(s), {warns} warning(s)"
