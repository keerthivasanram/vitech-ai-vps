"""Guards for placing equipment on a customer's site photograph.

The assertions that matter are the ones about TRUTH, not about pixels. A
perspective overlay is exactly the kind of output people over-trust, so what is
pinned here is that:

  * the geometry is EXACT - a homography solved from four marked points
    reproduces the camera that took the photograph, at points nobody marked;
  * a photograph with no marked reference produces NO placement, because a photo
    carries no scale until a human states one real dimension;
  * a machine with no vertical reference gets a FOOTPRINT and a stated reason,
    never a guessed height;
  * a machine that does not fit is REPORTED as not fitting - the platform never
    nudges a machine to make a picture work, exactly as it never rounds a
    dimension to reach a catalogue size;
  * the standing "not a survey" caveat is always on the sheet.

The fixture photograph is synthesised from a KNOWN camera, which is what makes
the first assertion possible: we can compare the solved projection against the
true one rather than eyeballing a render.
"""
import math
import sys

from app.siting.homography import SolveError, from_rectangle, height_scale
from app.siting.plan import fits_within, place
from app.siting.render import compose

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# --- a known camera: floor X right, Y away, Z up ---------------------------
W, H, F, CAM_H, CAM_X, D0 = 1100, 720, 900.0, 1.6, 3.0, 4.0


def cam(X, Y, Z=0.0):
    d = Y + D0
    return (W / 2 + F * (X - CAM_X) / d, H / 2 + F * (CAM_H - Z) / d)


# The engineer marks an 8 x 7 m floor rectangle whose near-left corner is the
# world point (1, 2), so plane coordinates are offset from world by (1, 2).
marks = [cam(1, 2), cam(9, 2), cam(9, 9), cam(1, 9)]
hom = from_rectangle(marks, 8.0, 7.0)

err = max(math.dist(hom.project(X - 1, Y - 2), cam(X, Y))
          for X, Y in ((3, 3), (5, 4), (7, 6), (2, 7), (8, 2), (1.5, 8.5)))
check(err < 1e-6,
      f"the solved homography reproduces the true camera at UNMARKED points ({err:.2e} px)")

check(abs(hom.horizon_y(550) - H / 2) < 1e-6,
      "the horizon is found exactly where the camera puts it")

# A square-on camera has one vanishing point at infinity; the horizon must still
# be computable, which is why the vanishing points are kept homogeneous.
flat = from_rectangle([(200, 700), (800, 700), (650, 450), (350, 450)], 4.0, 3.0)
check(flat.horizon_y(500) is not None,
      "a symmetric view still yields a horizon (the infinite vanishing point case)")

try:
    from_rectangle([(0, 0), (100, 0), (200, 0), (300, 0)], 4.0, 3.0)
    check(False, "collinear marks are rejected")
except SolveError:
    check(True, "collinear marks are rejected rather than silently solved")

try:
    from_rectangle(marks, 0.0, 7.0)
    check(False, "a zero-size reference is rejected")
except SolveError:
    check(True, "a reference rectangle with no real width is rejected")

# --- heights ---------------------------------------------------------------
hs = height_scale(hom, cam(7, 14), cam(7, 14, 2.1), 2.1)
check(hs is not None, "a marked 2.1 m vertical calibrates the height scale")
near = hom.project(4.0, 1.0)
far = hom.project(4.0, 6.0)
h_near = hs.pixels(4.0, near[1])
h_far = hs.pixels(4.0, far[1])
check(h_near > h_far > 0,
      f"the same 4 m machine is drawn smaller further away ({h_near:.0f} vs {h_far:.0f} px)")
check(height_scale(hom, cam(7, 14), cam(7, 14), 2.1) is None,
      "a zero-length vertical mark calibrates nothing")
check(height_scale(hom, cam(7, 14), cam(7, 14, 2.1), 0) is None,
      "a vertical with no stated height calibrates nothing")

# --- placement -------------------------------------------------------------
pl = place(hom, 5.0, 3.0, 4.0, (4.0, 3.2), 0.0, 0.8, hs)
check(len(pl.footprint_px) == 4 and pl.top_px is not None,
      "a machine with a calibrated height gets a footprint AND an elevation")
check(pl.clearance_px is not None, "the clearance zone is projected too")
fits, problems = fits_within(hom, pl, 8.0, 7.0)
check(fits and not problems, "a machine inside the measured floor is reported as fitting")

big = place(hom, 9.0, 3.0, 4.0, (4.0, 3.2), 0.0, 0.0, hs)
fits_big, problems_big = fits_within(hom, big, 8.0, 7.0)
check(not fits_big and problems_big,
      f"a machine wider than the floor is REPORTED, not nudged ({problems_big[0][:44]}...)")

# THE HONEST-GAP CONTRACT, applied to a photograph.
no_h = place(hom, 5.0, 3.0, 4.0, (4.0, 3.2), 0.0, 0.0, None)
check(no_h.top_px is None, "no vertical reference means NO elevation is drawn")
check(any("vertical reference" in n for n in no_h.notes),
      "and the reason is stated, rather than the height being guessed")

rot = place(hom, 5.0, 3.0, 4.0, (4.0, 3.2), 90.0, 0.0, hs)
check(rot.footprint_px != pl.footprint_px, "rotation changes the projected footprint")
ok_rot, _ = fits_within(hom, rot, 8.0, 7.0)
check(ok_rot, "a 5 x 3 machine turned 90 degrees still fits an 8 x 7 floor")

# --- the sheet -------------------------------------------------------------
svg = compose(b"\x89PNG\r\n\x1a\n-fake-", "image/png", W, H, pl,
              "Paint Booth 5 x 3 x 4 m - indicative siting", "Paint Booth",
              True, [], "Scale from a marked 8.00 x 7.00 m floor rectangle.")
check(svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), "the sheet is one SVG")
check("data:image/png;base64," in svg,
      "the photograph is embedded, so the sheet survives being emailed")
check("INDICATIVE SITING VIEW - not a survey" in svg,
      "the standing caveat is ALWAYS on the sheet")
check("FITS the measured floor area" in svg, "the verdict is printed on the sheet")
check("Paint Booth  5 x 3 x 4 m" in svg, "the machine is labelled with its own size")

svg_bad = compose(b"x", "image/png", W, H, big, "t", "Paint Booth", False,
                  problems_big, "ref")
check("DOES NOT FIT" in svg_bad, "a machine that does not fit says so on the sheet")

check(compose(b"x", "image/png", W, H, pl, "t", "Paint Booth", True, [], "r")
      == compose(b"x", "image/png", W, H, pl, "t", "Paint Booth", True, [], "r"),
      "the sheet is byte-stable for the same inputs")

print()
if FAILS:
    print(f"{len(FAILS)} SITING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL SITING TESTS PASS")
