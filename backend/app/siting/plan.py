"""Place a machine on a site photograph, to scale and in perspective.

This turns "will it fit, and what will it look like there?" into something the
platform can answer from the engineer's own measurements rather than a sketch.

WHAT IS REAL HERE AND WHAT IS NOT, stated plainly because a photo-realistic
overlay is exactly the kind of output people over-trust:

  * The FOOTPRINT is real. It is the resolved envelope, projected through a
    homography built from a rectangle the engineer measured on site.
  * The HEIGHT is real only when a vertical reference was marked. Without one
    the elevation is not drawn at all and the sheet says why.
  * The POSITION is the engineer's. Nothing here decides where a machine should
    go - that is a layout decision involving services, access, fire routes and
    the customer's own plans, none of which is in a photograph.
  * NOTHING here is a survey. The output is an indicative siting view for
    discussion, and it is labelled as one.
"""
import math
from typing import NamedTuple, Optional

from .homography import Homography, HeightScale, SolveError

Point = tuple[float, float]


class Placement(NamedTuple):
    """One machine placed on the floor plane."""
    footprint_px: list[Point]          # the four base corners, in image pixels
    top_px: Optional[list[Point]]      # the four top corners, when height is scaled
    clearance_px: Optional[list[Point]]
    length_m: float
    width_m: float
    height_m: Optional[float]
    clearance_m: float
    origin_m: Point
    rotation_deg: float
    notes: tuple[str, ...]


def _rect(cx: float, cy: float, length_m: float, width_m: float,
          rotation_deg: float) -> list[Point]:
    """Floor-plane corners of a machine centred at (cx, cy)."""
    a = math.radians(rotation_deg)
    ca, sa = math.cos(a), math.sin(a)
    half_l, half_w = length_m / 2.0, width_m / 2.0
    corners = [(-half_l, -half_w), (half_l, -half_w), (half_l, half_w), (-half_l, half_w)]
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in corners]


def place(hom: Homography,
          length_m: float,
          width_m: float,
          height_m: Optional[float],
          origin_m: Point,
          rotation_deg: float = 0.0,
          clearance_m: float = 0.0,
          height_scale: Optional[HeightScale] = None) -> Placement:
    """Project a machine's envelope onto the photograph.

    `origin_m` is the centre of the footprint in the same floor coordinates the
    reference rectangle defined - so (2, 1.5) means two metres along the
    rectangle's near edge and one and a half into the room, which is a thing an
    engineer can actually point at on site.
    """
    notes: list[str] = []
    if length_m <= 0 or width_m <= 0:
        raise SolveError("the machine needs a real length and width")

    cx, cy = origin_m
    base_world = _rect(cx, cy, length_m, width_m, rotation_deg)
    try:
        base_px = [hom.project(x, y) for x, y in base_world]
    except SolveError:
        raise SolveError("the machine falls outside the photographed floor area")

    top_px: Optional[list[Point]] = None
    if height_m and height_scale is not None:
        top_px = [(u, v - height_scale.pixels(height_m, v)) for u, v in base_px]
    elif height_m:
        notes.append("No vertical reference was marked, so the height is NOT drawn: "
                     "a photograph cannot be scaled vertically without one.")
    else:
        notes.append("The resolved envelope has no height, so only the footprint is shown.")

    clearance_px = None
    if clearance_m > 0:
        c_world = _rect(cx, cy, length_m + 2 * clearance_m,
                        width_m + 2 * clearance_m, rotation_deg)
        try:
            clearance_px = [hom.project(x, y) for x, y in c_world]
        except SolveError:
            notes.append(f"The {clearance_m:g} m clearance zone extends beyond the "
                         "photographed floor and is not drawn.")

    return Placement(base_px, top_px, clearance_px, length_m, width_m, height_m,
                     clearance_m, origin_m, rotation_deg, tuple(notes))


def fits_within(hom: Homography, placement: Placement,
                floor_width_m: float, floor_depth_m: float) -> tuple[bool, list[str]]:
    """Does the machine, plus its clearance, stay inside the stated floor area?

    A REPORT, not a correction. If it does not fit the answer is that it does
    not fit - the platform never nudges a machine to make a picture work, any
    more than it rounds a dimension to reach a catalogue size.
    """
    problems: list[str] = []
    cx, cy = placement.origin_m
    reach_l = placement.length_m / 2.0 + placement.clearance_m
    reach_w = placement.width_m / 2.0 + placement.clearance_m
    # Rotation means the axis-aligned reach is the diagonal projection.
    a = math.radians(placement.rotation_deg)
    ext_x = abs(reach_l * math.cos(a)) + abs(reach_w * math.sin(a))
    ext_y = abs(reach_l * math.sin(a)) + abs(reach_w * math.cos(a))

    for label, lo, hi, limit in (("left", cx - ext_x, cx + ext_x, floor_width_m),
                                 ("near", cy - ext_y, cy + ext_y, floor_depth_m)):
        if lo < -1e-6:
            problems.append(f"overhangs the {label} edge of the measured floor "
                            f"by {abs(lo):.2f} m")
        if hi > limit + 1e-6:
            problems.append(f"extends {hi - limit:.2f} m beyond the measured floor "
                            f"({limit:g} m)")
    return (not problems), problems
