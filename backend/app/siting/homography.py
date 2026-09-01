"""Plane-to-image projection, solved exactly from four marked points.

A photograph carries no scale. Nothing in an image tells you whether a floor is
three metres wide or thirty, so nothing can place a machine on it correctly
until a human states one real dimension. That is the whole reason this module
takes point correspondences rather than trying to infer geometry from pixels:
**the scale comes from what the engineer measured, never from what a model
guessed.** It is golden rule #2 applied to a photo.

Given four image points that the engineer says are the corners of a rectangle of
known size on the floor, there is exactly one homography mapping floor metres to
image pixels, and it is found by solving an 8x8 linear system. No dependency, no
iteration, no approximation - the same four clicks always give the same matrix,
so the same photo and the same machine always produce the same drawing.

Heights need one more fact. A ground-plane homography says nothing about the
vertical direction, so a vertical reference of KNOWN height (a door, a column, a
roller shutter) is required before any elevation is drawn. Without it this
module places the FOOTPRINT and says so, rather than inventing a camera.
"""
from typing import NamedTuple, Optional, Sequence

Point = tuple[float, float]


class SolveError(ValueError):
    """The four points do not define a usable plane (collinear, or repeated)."""


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Small, exact enough, and
    dependency-free - an 8x8 system does not justify pulling in a linear-algebra
    stack, and hand-rolling it keeps the numeric behaviour auditable."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise SolveError("the marked points are collinear or coincident")
        a[col], a[pivot] = a[pivot], a[col]
        p = a[col][col]
        for r in range(n):
            if r == col:
                continue
            f = a[r][col] / p
            if f:
                for c in range(col, n + 1):
                    a[r][c] -= f * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


class Homography(NamedTuple):
    """Floor metres -> image pixels, and back."""
    h: tuple[float, ...]        # 9 coefficients, row-major, h[8] == 1

    def project(self, x_m: float, y_m: float) -> Point:
        """A point on the floor, in metres, as a pixel."""
        h = self.h
        d = h[6] * x_m + h[7] * y_m + h[8]
        if abs(d) < 1e-12:                       # on the horizon: not visible
            raise SolveError("point projects to the horizon")
        return ((h[0] * x_m + h[1] * y_m + h[2]) / d,
                (h[3] * x_m + h[4] * y_m + h[5]) / d)

    def horizon_y(self, at_x_px: float) -> Optional[float]:
        """Image y of the ground plane's vanishing line at a given x.

        The floor's horizon is the image of its line at infinity. Heights are
        scaled from a point's distance to this line, so a photo whose horizon
        cannot be computed (a perfectly overhead shot, where the floor has no
        horizon at all) supports a footprint but no elevation - which is
        reported, not worked around.

        Worked in HOMOGENEOUS coordinates on purpose. A camera square-on to the
        floor has one vanishing point at infinity - parallel lines that stay
        parallel in the image - and dividing by w to get a finite point throws
        that case away. The cross product handles it without a special case.
        """
        vp_x = self._vanishing_h(1.0, 0.0)
        vp_y = self._vanishing_h(0.0, 1.0)
        # line through two homogeneous points = their cross product
        a = vp_x[1] * vp_y[2] - vp_x[2] * vp_y[1]
        b = vp_x[2] * vp_y[0] - vp_x[0] * vp_y[2]
        c = vp_x[0] * vp_y[1] - vp_x[1] * vp_y[0]
        if abs(b) < 1e-12:
            return None                       # horizon is vertical: unusable
        return -(a * at_x_px + c) / b

    def _vanishing_h(self, dx: float, dy: float) -> tuple[float, float, float]:
        """Where a floor direction's parallel lines meet, homogeneous - so a
        direction that never converges (w = 0) is still a valid answer."""
        h = self.h
        return (h[0] * dx + h[1] * dy,
                h[3] * dx + h[4] * dy,
                h[6] * dx + h[7] * dy)


def from_rectangle(image_points, width_m: float, depth_m: float) -> Homography:
    """The homography taking floor metres to pixels.

    `image_points` are the four corners the engineer marked, in order:
    near-left, near-right, far-right, far-left. `width_m` and `depth_m` are what
    that rectangle actually measures on site. **Those two numbers ARE the scale
    of the whole photograph**, and everything downstream inherits them - which
    is why they are asked for rather than estimated.
    """
    if len(image_points) != 4:
        raise SolveError("exactly four floor corners are required")
    if width_m <= 0 or depth_m <= 0:
        raise SolveError("the reference rectangle needs a real width and depth")

    world = [(0.0, 0.0), (width_m, 0.0), (width_m, depth_m), (0.0, depth_m)]
    rows: list[list[float]] = []
    rhs: list[float] = []
    for (X, Y), (u, v) in zip(world, image_points):
        rows.append([X, Y, 1, 0, 0, 0, -u * X, -u * Y])
        rhs.append(u)
        rows.append([0, 0, 0, X, Y, 1, -v * X, -v * Y])
        rhs.append(v)
    return Homography(tuple(_solve(rows, rhs)) + (1.0,))


class HeightScale(NamedTuple):
    """Converts metres of height into pixels, anywhere on the floor.

    Calibrated from ONE vertical the engineer measured. The model is a level
    camera (vertical world lines stay vertical in the image), which is what a
    site photo taken at eye level actually is; a heavily tilted photo will read
    slightly tall at the frame edges, and the rendered sheet says so rather than
    pretending otherwise.
    """
    constant: float
    horizon_y: float

    def pixels(self, height_m: float, base_y_px: float) -> float:
        return self.constant * height_m * (base_y_px - self.horizon_y)


def height_scale(hom: Homography, base_px: Point, top_px: Point,
                 known_height_m: float) -> Optional[HeightScale]:
    """Calibrate heights from a vertical object of known size.

    Returns None when the photo cannot support it - no computable horizon, a
    reference standing on the horizon, or a zero-length mark. A None here means
    the caller draws a footprint and states that no elevation could be scaled;
    it must never mean a guessed height.
    """
    if known_height_m <= 0:
        return None
    horizon = hom.horizon_y(base_px[0])
    if horizon is None:
        return None
    span = abs(base_px[1] - horizon)
    pixels = abs(top_px[1] - base_px[1])
    if span < 1e-6 or pixels < 1e-6:
        return None
    return HeightScale(pixels / (known_height_m * span), horizon)
