"""Guards for the 2D GA drawing engine (`app/drawing/`).

The engine's contract is the same as the spec engine's: deterministic output,
and an unknown dimension surfaces as a TBD rather than a drawn line. These tests
pin both, plus the SVG structure the studio depends on (one <g> per layer).

Run after any change under `app/drawing/`.
"""
import re
import sys

from app.drawing import sheet, views
from app.drawing.drawing_service import build_drawing
from app.drawing.primitives import Canvas, Dim, LAYER_ORDER, Line, Text, n
from app.drawing.symbols import SYMBOLS, _find, _int, _nos

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


BOOTH = {
    "category": "paint_booth", "category_label": "Paint Booth",
    "geometry": {"envelope_mm": {"length": 5000, "width": 3000, "height": 4000},
                 "ready": True},
    "technical_details": [
        {"label": "Filters", "value": "9 (dry)"},
        {"label": "Exhaust blower", "value": "CLP-4-15-14500"},
        {"label": "Exhaust blower (nos)", "value": "1"},
        {"label": "Illumination", "value": "flame proof LED 700-800 LUX"},
        {"label": "Blower MOC", "value": "To be determined", "origin": "tbd"},
    ],
}
NO_DIMS = {
    "category": "hot_air_oven", "category_label": "Hot Air Oven",
    "geometry": {"envelope_mm": {"length": None, "width": None, "height": None},
                 "ready": False},
    "technical_details": [{"label": "Chamber", "value": "To be determined", "origin": "tbd"}],
}

# --- Determinism -----------------------------------------------------------
a, b = build_drawing(BOOTH), build_drawing(BOOTH)
check(a["svg"] == b["svg"], "identical spec produces byte-identical SVG")
check(len(a["svg"]) > 5000, f"SVG has real content ({len(a['svg'])} bytes)")
check(n(-0.0) == "0" and n(3.10) == "3.1" and n(2.0) == "2",
      "number formatting is canonical (no -0, no trailing zeros)")

# --- SVG structure the studio relies on ------------------------------------
svg = a["svg"]
check(svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), "SVG is a complete document")
check('viewBox="0 0 420 297"' in svg, "A3 landscape viewBox is emitted in mm")
groups = re.findall(r'<g id="layer-([a-z]+)"', svg)
check(groups == [l for l in LAYER_ORDER if l in groups],
      f"layer groups are emitted in canonical order ({groups})")
check(len(groups) == len(set(groups)), "each layer appears exactly once")
check(all(lay["id"] in groups for lay in a["layers"]),
      "every advertised layer really exists in the SVG")
check('fill="currentColor"' in svg and 'stroke="currentColor"' in svg,
      "text is filled and strokes are themeable (invisible-text regression)")

# --- Dimensions come from the envelope, never invented ---------------------
check(">5000<" in svg and ">3000<" in svg and ">4000<" in svg,
      "the real envelope dimensions are printed on the sheet")
check(a["scale"] == "1:50" and a["scale_divisor"] == 50, f"a standard scale is chosen ({a['scale']})")
check([v["key"] for v in a["views"]] == ["plan", "front", "side"],
      "third-angle layout places plan, front and side")

# --- The honest-gap contract ----------------------------------------------
nd = build_drawing(NO_DIMS)
check(nd["views"] == [] and nd["scale"] == "NTS",
      "with no dimensions there are no views and no scale is claimed")
check("NO DIMENSIONED VIEWS" in nd["svg"], "the sheet says so plainly instead of drawing a box")
check(not re.search(r"<rect[^>]*width=\"[1-9]", nd["svg"].split("layer-outline")[-1][:200])
      or "layer-outline" not in nd["svg"],
      "no equipment outline is fabricated without dimensions")
check(len(nd["tbd"]) == 4, f"all four unknowns are scheduled ({len(nd['tbd'])})")
check(all("needs engineering input" in t for t in nd["tbd"]),
      "every TBD says what it needs")
check("Blower MOC - needs engineering input" in a["tbd"],
      "a tbd-origin spec row reaches the sheet's TBD schedule")

# --- Counts must be real counts, not any stray number ----------------------
check(_nos("flame proof LED 700-800 LUX") == 0,
      "a LUX rating is NOT read as a luminaire count")
check(_nos("4 nos") == 4 and _nos("2 sets/booth") == 2, "an explicit count is read")
check(_int("9 (dry)") == 9, "a leading quantity is still read where it is one")
legend = " ".join(l["description"] for l in a["legend"])
check("700 nos" not in legend, "the legend cannot advertise 700 luminaires")
check("9 nos" in legend and "CLP-4-15-14500" in legend,
      "the legend carries the real filter count and blower model")

# --- Scale selection -------------------------------------------------------
small = build_drawing({**BOOTH, "geometry": {
    "envelope_mm": {"length": 1700, "width": 700, "height": 3750}, "ready": True}})
check(small["scale_divisor"] <= a["scale_divisor"],
      "a smaller machine is drawn at an equal or larger scale")
check(small["scale_divisor"] in views.STANDARD_SCALES,
      "the chosen scale is a standard drafting scale")

# --- Sheet sizes -----------------------------------------------------------
a2 = build_drawing(BOOTH, sheet_size="A2")
check(a2["sheet_size"] == "A2" and 'viewBox="0 0 594 420"' in a2["svg"],
      "sheet size is honoured")
check(build_drawing(BOOTH, sheet_size="NOPE")["sheet_size"] == sheet.DEFAULT_SIZE,
      "an unknown sheet size falls back to the default rather than erroring")

# --- Title block + BOM -----------------------------------------------------
titled = build_drawing(BOOTH, client="CRI Pumps", ref="VT/GA/001", drawn_by="RK")
check("CRI Pumps" in titled["svg"] and "VT/GA/001" in titled["svg"],
      "client and drawing number reach the title block")
check("VITECH ENVIRO SYSTEMS PVT. LTD" in titled["svg"],
      "the title block carries the shared company identity")
check("DRAFT" in titled["svg"], "every sheet is marked DRAFT (golden rule #3)")
check(any(r["item"] == "Exhaust blower" for r in a["bom"]), "the BOM lists real hardware")
check(all(str(r["spec"]).lower() != "to be determined" for r in a["bom"]),
      "the BOM never lists an undetermined item as if it were supplied")

# --- Categories without a glyph still produce a valid sheet ----------------
generic = build_drawing({**NO_DIMS, "category": "ducting", "category_label": "Ducting",
                         "geometry": {"envelope_mm": {"length": 2000, "width": 600,
                                                      "height": 600}, "ready": True}})
check(generic["ok"] and generic["legend"] == [],
      "a category with no glyph draws its envelope with an empty legend")
check(len(generic["views"]) == 3, "envelope views still project without component glyphs")
check("wet_scrubber" in SYMBOLS and "paint_booth" in SYMBOLS,
      "the glyph registry exposes the implemented categories")

# --- Markdown summary is a summary, not vector data ------------------------
check("<svg" not in a["drawing_markdown"] and "<path" not in a["drawing_markdown"],
      "the agent summary never contains raw SVG")
check("DRAFT" in a["drawing_markdown"], "the agent summary states the draft status")

# --- Derived envelopes (categories that never state L x W x H) -------------
from app.drawing.envelope import derive_envelope

SCRUBBER_ROWS = [
    {"label": "Tower diameter (mm)", "value": "750", "origin": "given"},
    {"label": "Tower height (m)", "value": "4", "origin": "rule"},
]
env = derive_envelope("wet_scrubber", SCRUBBER_ROWS)
check(env == {"length": 750, "width": 750, "height": 4000},
      f"wet scrubber envelope derives from tower diameter + computed height ({env})")
check(derive_envelope("paint_booth", SCRUBBER_ROWS) is None,
      "a category with no deriver returns None rather than borrowing another's rule")
check(derive_envelope("wet_scrubber", [SCRUBBER_ROWS[0]]) is None,
      "a PARTIAL envelope is refused - never a guessed extent on a dimensioned view")
check(derive_envelope("wet_scrubber", [
        {"label": "Tower diameter (mm)", "value": "750", "origin": "reused"},
        {"label": "Tower height (m)", "value": "4", "origin": "rule"}]) is None,
      "a REUSED historical value cannot become this machine's drawn size")
check(derive_envelope("wet_scrubber", [
        {"label": "Tower diameter (mm)", "value": "750", "origin": "From Requirement"},
        {"label": "Tower height (m)", "value": "4", "origin": "Calculated (Engineering Rule)"}])
      == {"length": 750, "width": 750, "height": 4000},
      "display-form origins are accepted too (the tool response labels them)")

derived_drawing = build_drawing({
    "category": "wet_scrubber", "category_label": "Wet Scrubber",
    "geometry": {"envelope_mm": env, "ready": True},
    "technical_details": [{"label": "Spray nozzles (nos)", "value": "19"}]})
check(len(derived_drawing["views"]) == 3 and derived_drawing["scale"] != "NTS",
      "a derived envelope produces a real scaled drawing, not an NTS blank")

# --- The input-field contract (studio form <-> render endpoint) ------------
from app.drawing import fields as fieldspec

check(fieldspec.is_number("length_m") and fieldspec.is_number("air_volume_cfm")
      and fieldspec.is_number("qty") and fieldspec.is_number("ach"),
      "dimensional and count inputs are typed as numbers")
check(not fieldspec.is_number("paint_type") and not fieldspec.is_number("draft_type"),
      "descriptive inputs are typed as text")

# The 500 this replaced: a text field holding digits was coerced to a float and
# reached the material engine, which called .lower() on it.
coerced = fieldspec.coerce({"length_m": "10", "width_m": "10", "height_m": "10",
                            "paint_type": "10"})
check(coerced["length_m"] == 10.0 and isinstance(coerced["length_m"], float),
      "a numeric field is coerced to a float")
check(coerced["paint_type"] == "10" and isinstance(coerced["paint_type"], str),
      "a TEXT field holding digits stays a string (the 500-error regression)")
check(fieldspec.coerce({"length_m": "abc"}) == {},
      "an unparseable number is dropped, not passed through as text")
check(fieldspec.coerce({"length_m": "", "width_m": None, "qty": "  "}) == {},
      "blank inputs are omitted so they surface as TBD, not as zero")

print()
if FAILS:
    print(f"{len(FAILS)} DRAWING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL DRAWING TESTS PASS")
