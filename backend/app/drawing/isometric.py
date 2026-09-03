"""An isometric of the ENVELOPE, for the empty third-angle quadrant.

WHY THIS IS SAFE, which is the first thing to establish for a pictorial view on
a drawing whose whole discipline is not implying geometry.

It draws ONE thing: the box the spec engine already resolved, in axonometric
projection. All three of its edges are dimensions the sheet states elsewhere and
a fabricator could read off the orthographic views; showing the same three
numbers as a shape adds no claim. It is captioned NOT TO SCALE and carries no
dimension of its own, so nothing can be measured off it.

WHAT IT DELIBERATELY DOES NOT DRAW: components. A pictorial view is the most
persuasive thing on a sheet — a reader believes a picture in a way they do not
believe a schematic elevation — and component POSITIONS are indicative until
Vitech supply setting-out rules. Drawing an indicative arrangement in 3D would
make the least reliable information on the sheet look like the most reliable.
The orthographic views carry the components, under a note that says they are
indicative; this carries the envelope, which is not.

It is OPTIONAL (`drawing_type="ga_iso"`), because a third-angle GA is complete
without it and some houses do not want a pictorial on a working drawing.
"""
import math

from .primitives import Line, Text
from .style import (HIDDEN_LINE, L_TEXT, PRIMARY_OUTLINE, TITLE_RULE as
                    CAPTION_RULE, T_CAPTION, T_TINY, T_VIEW_TITLE)

# True isometric: both horizontal axes at 30 degrees to the horizontal, the
# vertical staying vertical. Equal foreshortening on all three, which is what
# makes it readable without a scale.
_COS30 = math.cos(math.radians(30.0))
_SIN30 = math.sin(math.radians(30.0))


def project(x: float, y: float, z: float) -> tuple:
    """Model (length, width, height) -> sheet (x, y), y increasing downward."""
    return ((x - y) * _COS30, (x + y) * _SIN30 - z)


def _fit(env: dict, box_w: float, box_h: float) -> tuple:
    """A uniform factor that puts the whole projected box inside the quadrant."""
    L = float(env.get("length") or 0)
    W = float(env.get("width") or 0)
    H = float(env.get("height") or 0)
    if not (L and W and H):
        return None
    pts = [project(x, y, z) for x in (0, L) for y in (0, W) for z in (0, H)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if span_x <= 0 or span_y <= 0:
        return None
    k = min(box_w / span_x, box_h / span_y)
    return k, min(xs), min(ys), span_x * k, span_y * k


def draw(canvas, env: dict, bx: float, by: float, bw: float, bh: float) -> bool:
    """Draw the envelope isometric into the box, or return False if it cannot.

    Returns False rather than drawing something approximate when any axis is
    unresolved — a pictorial of a partly-unknown box would be exactly the
    confident-looking guess this engine exists to avoid.
    """
    fitted = _fit(env, bw * 0.78, bh * 0.62)
    if not fitted:
        return False
    k, min_x, min_y, draw_w, draw_h = fitted
    L = float(env["length"])
    W = float(env["width"])
    H = float(env["height"])

    ox = bx + (bw - draw_w) / 2 - min_x * k
    oy = by + (bh - draw_h) / 2 - min_y * k + 3.0

    def P(x, y, z):
        px, py = project(x, y, z)
        return (ox + px * k, oy + py * k)

    # The eight corners, indexed [x][y][z] with 0 = origin, 1 = far.
    C = {(i, j, m): P(L if i else 0, W if j else 0, H if m else 0)
         for i in (0, 1) for j in (0, 1) for m in (0, 1)}

    # WHICH VERTEX IS HIDDEN follows from the projection, and getting it wrong
    # makes the box read inside-out. Here a larger (x + y) moves a point DOWN
    # the sheet and a larger z moves it UP, so the viewer stands on the +x, +y
    # side looking down: the visible faces are the top, the x=L face and the
    # y=W face, and the three edges meeting the ORIGIN are the hidden ones.
    hidden_vertex = (0, 0, 0)
    edges = []
    for a in C:
        for b in C:
            if sum(1 for p, q in zip(a, b) if p != q) == 1 and a < b:
                edges.append((a, b))
    for a, b in edges:
        pen = HIDDEN_LINE if hidden_vertex in (a, b) else PRIMARY_OUTLINE
        canvas.add(Line(C[a][0], C[a][1], C[b][0], C[b][1], *pen))

    # Axis letters at the near corner, so the reader knows which way the box is
    # turned. NAMES ONLY — a dimension here would be measurable off a view that
    # is explicitly not to scale.
    # Anchored at the NEAR vertex, not the origin — the origin is the hidden
    # corner, and letters on hidden edges label what the reader cannot see.
    origin = C[(1, 1, 0)]
    # Pushed OUTWARD from the box centre, not by a fixed offset: a constant
    # nudge put "L" straight on the bottom edge it was labelling.
    cx = sum(p[0] for p in C.values()) / 8.0
    cy = sum(p[1] for p in C.values()) / 8.0
    for corner, label in ((C[(0, 1, 0)], "L"), (C[(1, 0, 0)], "W"),
                          (C[(1, 1, 1)], "H")):
        mx, my = (origin[0] + corner[0]) / 2, (origin[1] + corner[1]) / 2
        dx, dy = mx - cx, my - cy
        mag = math.hypot(dx, dy) or 1.0
        canvas.add(Text(mx + dx / mag * 3.0, my + dy / mag * 3.0 + 0.8,
                        label, L_TEXT, T_TINY, "middle"))

    ty = by + bh - 2.0
    canvas.add(Text(bx + bw / 2, ty, "ISOMETRIC", L_TEXT, T_VIEW_TITLE,
                    "middle", bold=True))
    # The same SOLID rule every other view caption carries. A dashed one read
    # as a centre line that happened to sit under some text.
    half = max(len("ISOMETRIC") * T_VIEW_TITLE * 0.30, bw * 0.18)
    canvas.add(Line(bx + bw / 2 - half, ty + 1.6, bx + bw / 2 + half, ty + 1.6,
                    *CAPTION_RULE))
    canvas.add(Text(bx + bw / 2, ty + 5.4,
                    "ENVELOPE ONLY - NOT TO SCALE", L_TEXT, T_CAPTION, "middle"))
    return True


def quadrant(placed: list, ax: float, ay: float, aw: float, ah: float):
    """The free top-right box in a third-angle layout, or None.

    Plan sits top-left, front below it, side to the right of front — which
    leaves the top-right quadrant empty on every sheet this engine draws. That
    is the space a pictorial belongs in, and using it costs no other view.
    """
    views = {v.key: v for v in placed}
    plan, side = views.get("plan"), views.get("side")
    if not (plan and side):
        return None
    bx = side.x
    by = plan.y
    bw = side.w
    bh = plan.h
    if bw < 26.0 or bh < 26.0:
        return None                      # too small to read; leave it empty
    return bx, by, bw, bh
