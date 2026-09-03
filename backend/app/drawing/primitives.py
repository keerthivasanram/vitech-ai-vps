"""A tiny 2D vector model in millimetre space, with deterministic SVG output.

No external CAD dependency. Everything the GA sheet is made of is one of these
primitives, every primitive belongs to a LAYER (so the studio can toggle it),
and every emit is byte-stable for a given input — which is what lets the drawing
engine be covered by a golden test the same way the spec engine is.

Coordinates are SHEET millimetres with the origin at the top-left and +y DOWN,
matching SVG's own convention so no flip is needed at emit time. Model geometry
is converted to sheet mm by the caller (see `views.py`), never here.
"""
from typing import NamedTuple, Optional

# Layers, dash patterns and the weight ladder now live in `style.py`, which is
# the drafting standard for the whole engine. They are re-exported here because
# every module already imports them from primitives, and because a shape still
# needs to name its own layer.
from .style import (DASH_CENTRE, DASH_HIDDEN, LAYER_LABELS, LAYER_ORDER,
                    L_BORDER, L_CENTRE, L_COMPONENT, L_DIM, L_HIDDEN,
                    L_OUTLINE, L_TEXT, L_TITLE, T_DIM, W_FINE, W_HAIR,
                    W_HEAVY, W_LIGHT, W_MEDIUM)

# Physical aliases kept for the call sites that still name a weight rather than
# a role. New code should use a role from `style.py` instead.
LW_THICK = W_HEAVY
LW_MED = W_MEDIUM
LW_THIN = W_LIGHT
LW_FINE = W_FINE
LW_HATCH = W_HAIR

ARROW = 2.2         # dimension arrowhead length, mm
EXT_GAP = 1.0       # gap between a feature and its extension line (ISO 129)
TEXT_H = 2.5        # default annotation text height, mm


def n(v: float) -> str:
    """Format a number for SVG: fixed 2dp with trailing zeros trimmed, and no
    negative zero. Deterministic, so identical geometry emits identical bytes."""
    s = f"{float(v):.2f}"
    if s in ("-0.00", "0.00"):
        return "0"
    return s.rstrip("0").rstrip(".") if "." in s else s


def esc(t) -> str:
    """Escape text for XML content."""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class Shape:
    """Base: every shape knows its layer and can emit one SVG element."""
    layer = L_OUTLINE

    def svg(self) -> str:                       # pragma: no cover - interface
        raise NotImplementedError


class Line(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = L_OUTLINE
    width: float = LW_THICK
    dash: Optional[str] = None

    def svg(self) -> str:
        d = f' stroke-dasharray="{self.dash}"' if self.dash else ""
        return (f'<line x1="{n(self.x1)}" y1="{n(self.y1)}" x2="{n(self.x2)}" '
                f'y2="{n(self.y2)}" stroke-width="{n(self.width)}"{d}/>')


class Rect(NamedTuple):
    x: float
    y: float
    w: float
    h: float
    layer: str = L_OUTLINE
    width: float = LW_THICK
    dash: Optional[str] = None
    fill: str = "none"

    def svg(self) -> str:
        d = f' stroke-dasharray="{self.dash}"' if self.dash else ""
        return (f'<rect x="{n(self.x)}" y="{n(self.y)}" width="{n(self.w)}" '
                f'height="{n(self.h)}" fill="{self.fill}" '
                f'stroke-width="{n(self.width)}"{d}/>')


class Circle(NamedTuple):
    cx: float
    cy: float
    r: float
    layer: str = L_COMPONENT
    width: float = LW_MED
    fill: str = "none"

    def svg(self) -> str:
        return (f'<circle cx="{n(self.cx)}" cy="{n(self.cy)}" r="{n(self.r)}" '
                f'fill="{self.fill}" stroke-width="{n(self.width)}"/>')


class Path(NamedTuple):
    """An arbitrary polyline/polygon.

    `d` is what the SVG emits; `pts` carries the same geometry as real
    coordinates. The non-SVG exporters (DXF, PDF) need coordinates, and
    re-parsing an SVG `d` string to recover them would be a second, drifting
    definition of the same shape — so shapes are built from points via `poly()`
    and the `d` string is derived from them, never the other way round.
    """
    d: str
    layer: str = L_COMPONENT
    width: float = LW_MED
    fill: str = "none"
    pts: tuple = ()
    closed: bool = True

    def svg(self) -> str:
        return (f'<path d="{self.d}" fill="{self.fill}" '
                f'stroke-width="{n(self.width)}"/>')


def poly(points, layer: str = L_COMPONENT, width: float = LW_MED,
         fill: str = "none", closed: bool = True) -> Path:
    """A polyline/polygon from points, carrying both representations."""
    pts = tuple((float(x), float(y)) for x, y in points)
    d = "M" + " L".join(f"{n(x)},{n(y)}" for x, y in pts) + (" Z" if closed else "")
    return Path(d, layer, width, fill, pts, closed)


def hatch(x: float, y: float, w: float, h: float, spacing: float = 2.5,
          slope: int = 1, layer: str = L_COMPONENT,
          width: float = LW_HATCH) -> list:
    """Section hatch over a rectangle, as REAL LINE SEGMENTS at 45 degrees.

    Deliberately not an SVG `<pattern>` fill. The DXF and PDF exporters consume
    coordinates, not markup, so a pattern would render on screen and then vanish
    from both — the same drift the `Path.pts` comment above exists to prevent.
    Drafting hatch is line work anyway.

    `slope` is +1 for lines running down-right and -1 for down-left, so two
    adjacent materials can be told apart the way a section drawing does it.
    """
    if w <= 0 or h <= 0 or spacing <= 0:
        return []
    # A 45-degree line is y = slope*x + c; sweep c across the rectangle's corners.
    corners = [slope * cx for cx in (x, x + w)]
    lo = min(y - max(corners), y - min(corners))
    hi = max(y + h - max(corners), y + h - min(corners))
    out: list = []
    c = lo
    while c <= hi:
        pts = []
        for ex in (x, x + w):                       # left / right edges
            ey = slope * ex + c
            if y - 1e-9 <= ey <= y + h + 1e-9:
                pts.append((ex, ey))
        for ey in (y, y + h):                       # top / bottom edges
            ex = (ey - c) / slope
            if x - 1e-9 <= ex <= x + w + 1e-9:
                pts.append((ex, ey))
        # De-duplicate: a line through a corner meets two edges at one point.
        uniq: list = []
        for p in pts:
            if not any(abs(p[0] - q[0]) < 1e-7 and abs(p[1] - q[1]) < 1e-7 for q in uniq):
                uniq.append(p)
        if len(uniq) >= 2:
            (x0, y0), (x1, y1) = uniq[0], uniq[1]
            if abs(x1 - x0) > 1e-6 or abs(y1 - y0) > 1e-6:
                out.append(Line(x0, y0, x1, y1, layer, width))
        c += spacing
    return out


class Text(NamedTuple):
    x: float
    y: float
    text: str
    layer: str = L_TEXT
    size: float = TEXT_H
    anchor: str = "start"          # start | middle | end
    bold: bool = False
    rotate: float = 0.0
    # WHICH REQUIREMENT FIELD this text reports, when it reports one. Emitted as
    # `data-edit`, and it is the whole mechanism behind editing a drawing by
    # changing its INPUTS: the studio can tell that a click landed on the
    # overall length, and send the reader to the length input rather than
    # letting them type a new number onto the sheet. A drawing must never be
    # hand-edited; this is what makes the alternative reachable.
    edit_key: Optional[str] = None

    def svg(self) -> str:
        w = ' font-weight="bold"' if self.bold else ""
        r = (f' transform="rotate({n(self.rotate)} {n(self.x)} {n(self.y)})"'
             if self.rotate else "")
        e = f' data-edit="{esc(self.edit_key)}"' if self.edit_key else ""
        # fill MUST be set explicitly: the document group paints fill="none" so
        # that outlines stay hollow, and without this override every glyph
        # renders invisibly.
        return (f'<text x="{n(self.x)}" y="{n(self.y)}" font-size="{n(self.size)}" '
                f'text-anchor="{self.anchor}"{w}{r}{e} stroke="none" fill="currentColor">'
                f'{esc(self.text)}</text>')


def _arrowhead(x: float, y: float, dx: float, dy: float) -> Path:
    """Solid triangular arrowhead at (x,y) pointing along the unit vector."""
    bx, by = x - dx * ARROW, y - dy * ARROW
    px, py = -dy * ARROW * 0.28, dx * ARROW * 0.28
    return poly([(x, y), (bx + px, by + py), (bx - px, by - py)],
                L_DIM, LW_THIN, "currentColor")


class Dim:
    """A linear dimension: extension lines, a dimension line with arrowheads at
    both ends, and the measured text. `label` overrides the numeric text, which
    is how a TBD dimension is drawn honestly (see the drawing service)."""

    layer = L_DIM

    def __init__(self, x1, y1, x2, y2, label: str, offset: float = 8.0,
                 vertical: bool = False, edit_key: str = None):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.label = label
        self.offset = offset
        self.vertical = vertical
        self.edit_key = edit_key

    def shapes(self) -> list:
        out: list = []
        # ISO 129: an extension line does NOT touch the feature it measures —
        # it starts a short gap away and runs a little PAST the dimension line.
        # Drawn hard against the outline, it read as part of the machine.
        gap = EXT_GAP
        if self.vertical:
            dx = self.offset
            ax, ay = self.x1 + dx, self.y1
            bx, by = self.x2 + dx, self.y2
            g = gap if dx > 0 else -gap
            out += [Line(self.x1 + g, self.y1, ax + 1.5, ay, L_DIM, LW_FINE),
                    Line(self.x2 + g, self.y2, bx + 1.5, by, L_DIM, LW_FINE),
                    Line(ax, ay, bx, by, L_DIM, LW_FINE)]
            u = 1.0 if by > ay else -1.0
            out += [_arrowhead(ax, ay, 0, -u), _arrowhead(bx, by, 0, u)]
            out.append(Text(ax - 1.2, (ay + by) / 2, self.label, L_DIM,
                            T_DIM, "middle", rotate=-90,
                            edit_key=self.edit_key))
        else:
            dy = self.offset
            ax, ay = self.x1, self.y1 + dy
            bx, by = self.x2, self.y2 + dy
            g = gap if dy > 0 else -gap
            out += [Line(self.x1, self.y1 + g, ax, ay + 1.5, L_DIM, LW_FINE),
                    Line(self.x2, self.y2 + g, bx, by + 1.5, L_DIM, LW_FINE),
                    Line(ax, ay, bx, by, L_DIM, LW_FINE)]
            u = 1.0 if bx > ax else -1.0
            out += [_arrowhead(ax, ay, -u, 0), _arrowhead(bx, by, u, 0)]
            out.append(Text((ax + bx) / 2, ay - 1.2, self.label, L_DIM,
                            T_DIM, "middle", edit_key=self.edit_key))
        return out


class Canvas:
    """Collects shapes and emits one SVG document, grouped by layer.

    Grouping matters: the studio toggles a layer by hiding its <g>, so the SVG
    has to carry the structure rather than a flat soup of elements.
    """

    def __init__(self, width_mm: float, height_mm: float):
        self.w = width_mm
        self.h = height_mm
        self.shapes: list = []
        # THE DIMENSIONS AS THEY WERE ASKED FOR, kept alongside the lines they
        # expand into. A `Dim` becomes extension lines, arrowheads and a text
        # the moment it is added, so by the time anything looks at `shapes`
        # there is no way to ask "what did this dimension claim, and over what
        # distance?" — which is exactly what the QA audit has to ask in order to
        # catch a dimension attached to geometry that is not at that size.
        # Purely additive: the emitted SVG does not read this list.
        self.dims: list = []

    def add(self, *shapes):
        for s in shapes:
            if isinstance(s, Dim):
                self.dims.append(s)
                self.shapes.extend(s.shapes())
            elif isinstance(s, (list, tuple)) and not hasattr(s, "svg"):
                self.add(*s)
            elif s is not None:
                self.shapes.append(s)
        return self

    def layers_present(self) -> list[str]:
        seen = {s.layer for s in self.shapes}
        return [l for l in LAYER_ORDER if l in seen]

    def svg(self) -> str:
        """The full SVG document. `currentColor` throughout so the studio can
        theme the drawing (light/dark) without re-rendering it server-side."""
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(self.w)}mm" '
            f'height="{n(self.h)}mm" viewBox="0 0 {n(self.w)} {n(self.h)}" '
            # NO `text-rendering` hint here. "geometricPrecision" looked like a
            # free crispness win and rendered every label as an illegible
            # outlined blob — caught only by rasterising the sheet and looking
            # at it, which is the standing rule for this engine.
            f'font-family="Helvetica, Arial, sans-serif">',
            # BUTT caps, not round. A round cap adds half a line width at every
            # end, which on 0.10 mm hatching bulges each stroke into a blob and
            # makes a dimension line overshoot its own arrowhead. Drafting lines
            # stop where they are told to stop. Joins stay round so a rectangle
            # corner does not spike.
            '<g stroke="currentColor" fill="none" stroke-linecap="butt" '
            'stroke-linejoin="round" vector-effect="non-scaling-stroke">',
        ]
        for layer in self.layers_present():
            out.append(f'<g id="layer-{layer}" data-layer="{layer}">')
            out += [s.svg() for s in self.shapes if s.layer == layer]
            out.append("</g>")
        out += ["</g>", "</svg>"]
        return "\n".join(out)
