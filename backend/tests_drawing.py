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

# --- A category with no glyph still produces a valid sheet -----------------
# Every catalog category now carries a glyph, so the fallback is exercised
# directly: it is the contract for whatever the client adds next.
generic = build_drawing({**NO_DIMS, "category": "not_yet_supported",
                         "category_label": "New Equipment",
                         "geometry": {"envelope_mm": {"length": 2000, "width": 600,
                                                      "height": 600}, "ready": True}})
check(generic["ok"] and generic["legend"] == [],
      "a category with no glyph draws its envelope with an empty legend")
check(len(generic["views"]) == 3, "envelope views still project without component glyphs")

from app.catalog import CATEGORY_PROFILES as _PROFILES
missing = sorted(set(_PROFILES) - set(SYMBOLS))
check(not missing, f"every catalog category has a component glyph (missing: {missing})")

# Legend tags allocate themselves, so a conditional item that does not resolve
# cannot leave a hole in the numbering (a sheet reading 1, 2, 3, 5).
for cat in SYMBOLS:
    d = build_drawing({"category": cat, "category_label": cat,
                       "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                    "height": 4000}, "ready": True},
                       "technical_details": [{"label": "Illumination", "value": "LED 6 nos"},
                                             {"label": "Blower motor hp", "value": "15"}]})
    nums = [l["tag"] for l in d["legend"] if l["tag"].isdigit()]
    check(nums == [str(i + 1) for i in range(len(nums))],
          f"{cat} legend numbering has no gaps ({nums})")

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

# A dust collector's casing size is drawable only when the CLIENT stated it.
# There is deliberately no airflow -> casing fallback: that needs an
# air-to-cloth ratio and hopper proportions Vitech has not supplied.
DC_SIZE = "3.9L x 4.0W x 8.3H"
check(derive_envelope("dust_collector",
                      [{"label": "Collector size (m)", "value": DC_SIZE,
                        "origin": "given"}], {})
      == {"length": 3900, "width": 4000, "height": 8300},
      "dust collector envelope reads a client-stated casing size")
check(derive_envelope("dust_collector",
                      [{"label": "Collector size (m)", "value": DC_SIZE,
                        "origin": "reused"}], {}) is None,
      "a historical collector's casing is refused - it is a different machine")
check(derive_envelope("dust_collector",
                      [{"label": "Collector size (mm)", "value": "900 x 900 x 1400",
                        "origin": "given"}], {})
      == {"length": 900, "width": 900, "height": 1400},
      "a collector size already in mm is not scaled again")
check(derive_envelope("dust_collector", [], {"air_volume_cmh": 25000}) is None,
      "airflow alone never sizes a casing (no client air-to-cloth standard yet)")

# A duct run: client-given length by the diameter the client's own transport
# velocity standard selects.
check(derive_envelope("ducting", [], {"layout_length_m": 40, "air_volume_cmh": 25000})
      == {"length": 40000, "width": 800, "height": 800},
      "ducting envelope = given run length x duct dia from select_duct")
check(derive_envelope("ducting", [], {"layout_length_m": 40, "air_volume_cfm": 14715})
      == {"length": 40000, "width": 800, "height": 800},
      "ducting accepts either airflow unit basis")
check(derive_envelope("ducting", [], {"layout_length_m": 40}) is None,
      "ducting without an airflow cannot compute a section, so it refuses")

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

# Categories specified by duty, not size, still need a way to be DRAWN.
from app.catalog import CATEGORY_PROFILES

dc_size = fieldspec.size_fields(CATEGORY_PROFILES["dust_collector"])
check([f["key"] for f in dc_size] == ["length_m", "width_m", "height_m"],
      "a duty-specified category is offered optional overall-size drawing inputs")
check(all(f["drawing_only"] and not f["required"] for f in dc_size),
      "those size inputs are drawing-only and never required")
check(fieldspec.size_fields(CATEGORY_PROFILES["paint_booth"]) == [],
      "a category that already declares dimensions is not offered duplicates")

# --- Component glyphs ------------------------------------------------------
GLYPH_CASES = {
    "hot_air_oven": ([
        {"label": "Insulation", "value": "150mm rock wool"},
        {"label": "Heating source", "value": "LPG burner"},
        {"label": "Circulation blower (HP)", "value": "10"},
        {"label": "Circulation blower (nos)", "value": "2 nos"},
        {"label": "No. of heating zones", "value": "3"},
        {"label": "Conveyor", "value": "overhead chain"}], "3 zones"),
    "dust_collector": ([
        {"label": "Filter bags", "value": "polyester, Dia 160 x 2500mm - 225 nos"},
        {"label": "Blower motor (HP)", "value": "60"},
        {"label": "Rotary airlock", "value": "0.5 HP - 2 nos"}], "225 nos"),
    "powder_coating_plant": ([
        {"label": "Powder coating booth", "value": "downside draft"},
        {"label": "Curing oven", "value": "batch 180 C"}], "Curing oven"),
    "conveyor": ([{"label": "Type", "value": "overhead"},
                  {"label": "Operation", "value": "manual"}], "Track"),
    "ducting": ([{"label": "Exhaust duct", "value": "GI 300mm"}], "Duct section"),
}
for cat, (rows_in, needle) in GLYPH_CASES.items():
    check(cat in SYMBOLS, f"{cat} has a component glyph")
    drawn = build_drawing({"category": cat, "category_label": cat,
                           "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                        "height": 4000}, "ready": True},
                           "technical_details": rows_in})
    legend_text = " | ".join(l["description"] for l in drawn["legend"])
    check(drawn["legend"] and needle in legend_text,
          f"{cat} legend carries the resolved value ({needle})")
    check(build_drawing({"category": cat, "category_label": cat,
                         "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                      "height": 4000}, "ready": True},
                         "technical_details": rows_in})["svg"] == drawn["svg"],
          f"{cat} glyph is deterministic")

# A count is only drawn when the value states one. "700-800 LUX" is not 700
# luminaires, and a glyph must omit the symbol rather than invent a quantity.
oven_no_counts = build_drawing({
    "category": "hot_air_oven", "category_label": "Hot Air Oven",
    "geometry": {"envelope_mm": {"length": 6000, "width": 3000, "height": 4000},
                 "ready": True},
    "technical_details": [{"label": "Circulation blower (nos)", "value": "700-800 LUX"}]})
check(not any("700" in l["description"] for l in oven_no_counts["legend"]),
      "a glyph never reads a non-count number as a quantity")

# Nothing a glyph draws may escape the sheet frame.
for cat, (rows_in, _) in GLYPH_CASES.items():
    d = build_drawing({"category": cat, "category_label": cat,
                       "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                    "height": 4000}, "ready": True},
                       "technical_details": rows_in})
    coords = [float(v) for v in re.findall(r'(?:x|cx|x1|x2)="(-?\d+\.?\d*)"', d["svg"])]
    check(coords and min(coords) >= 0 and max(coords) <= 420,
          f"{cat} glyph geometry stays inside the sheet")

# --- Exports (DXF / PDF) ---------------------------------------------------
from app.drawing import export as exporter
from app.drawing.drawing_service import compose

canvas, pkg = compose(BOOTH)
check(pkg["svg"] == a["svg"], "compose() and build_drawing() produce the same sheet")

dxf = exporter.to_dxf(canvas)
check(dxf.startswith("0\nSECTION") and dxf.rstrip().endswith("EOF"),
      "DXF is a complete R12 document")
check("\nENTITIES\n" in dxf and "\nLAYER\n" in dxf and "\nLTYPE\n" in dxf,
      "DXF declares its tables and an entities section")
for lay in [l["id"] for l in pkg["layers"]]:
    check(f"\n{lay}\n" in dxf, f"DXF carries the '{lay}' layer")
check("5000" in dxf, "DXF keeps the dimension text as text, not as outlines")
# DXF is +y UP while the sheet model is +y DOWN; a mirrored sheet is the
# classic symptom of getting this backwards.
ys = [float(v) for v in re.findall(r"\n20\n(-?\d+\.\d+)\n", dxf)]
check(ys and min(ys) >= -0.01 and max(ys) <= 297.01,
      f"DXF ordinates are flipped into sheet extents ({min(ys):.1f}..{max(ys):.1f})")
check(exporter.to_dxf(canvas) == dxf, "DXF export is deterministic")

pdf = exporter.to_pdf(canvas)
check(pdf.startswith(b"%PDF"), "PDF export is a real PDF")
check(len(pdf) > 3000, f"PDF has vector content ({len(pdf)} bytes)")
# The sheet is 420x297: fpdf2 SWAPS an explicit format tuple when told "L",
# which silently produced a portrait page.
check(b"/MediaBox [0 0 1190.55 841.89]" in pdf or b"1190.55 841.89" in pdf,
      "PDF page is the true landscape sheet size, not rotated to portrait")
check(exporter._pt(2.5) == 7.09, "text height in mm converts to points")
check(exporter._dash_mm("2,1.5") == (2.0, 1.5) and exporter._dash_mm(None) == (),
      "SVG dash patterns map to fpdf dash/gap")

# --- A generated specification is itself drawable --------------------------
from app.drawing.spec_parser import looks_like_spec, parse_spec

SPEC_DOC = """**ENGINEERING SPECIFICATION - DRAFT**
Equipment: Paint Booth   |   Confidence: High (93%)

**Customer Requirement**
| Parameter | Value |
| --- | --- |
| Length m | 5 |
| Width m | 3 |
| Height m | 4 |

**Technical Specification**
| Parameter | Value | Basis / Calculation |
| --- | --- | --- |
| Exhaust airflow | 19440 m3/h | Calculated: face area 3.0x4.0 x 0.45 m/s x 3600. |
| Construction | panels MS 1.6mm | Reused from historical offer OFF-CRI-PB-082406R4. |
| Construction material | Recommended GI panels | Recommended: material matrix (advisory). |
| Paint arresting filter | 16 nos 600 x 600 x 50 mm | Calculated: required area 5.4 m2. |
| Illumination | 3 nos 40 W LED | Calculated: 15 m2 x 750 lux. |
| Dry scrubber | To be determined | Needs a standard selection or a historical match. |
"""

check(looks_like_spec(SPEC_DOC) and not looks_like_spec("draw me a paint booth"),
      "a generated specification is told apart from a plain request")
parsed = parse_spec(SPEC_DOC)
check(parsed and parsed["category"] == "paint_booth",
      "the specification's Equipment line resolves to a catalog category")
# The two tables have DIFFERENT widths (Parameter|Value vs Parameter|Value|Basis).
# A fixed three-column row pattern skipped every requirement row, so a fully
# dimensioned spec drew as an NTS blank.
check(parsed["geometry"]["envelope_mm"] == {"length": 5000, "width": 3000, "height": 4000},
      f"the 2-column requirement table still yields the envelope ({parsed['geometry']['envelope_mm']})")
check(parsed["geometry"]["ready"], "a fully dimensioned specification is drawable")
origins = {r["label"]: r["origin"] for r in parsed["technical_details"]}
check(origins.get("Exhaust airflow") == "rule"
      and origins.get("Construction") == "reused"
      and origins.get("Construction material") == "advisory"
      and origins.get("Dry scrubber") == "tbd",
      f"each row's basis wording maps back to its origin ({origins.get('Dry scrubber')})")

from_spec = build_drawing(parsed)
check(from_spec["scale"] != "NTS" and len(from_spec["views"]) == 3,
      "a pasted specification produces a real scaled drawing")
check(any("16 nos" in l["description"] for l in from_spec["legend"]),
      "counts stated in the specification reach the drawing")
check(any("Dry scrubber" in t for t in from_spec["tbd"]),
      "a TBD the engineer accepted carries through to the sheet's schedule")
check(parse_spec("please draw me something nice") is None,
      "arbitrary prose is never salvaged into geometry")

# --- Sheet furniture: the drawing must stand on its own ---------------------
# Reading a printed or emailed GA should not require the studio panel beside it.
SCRUB = {
    "category": "wet_scrubber", "category_label": "Wet Scrubber",
    "geometry": {"envelope_mm": {"length": 5000, "width": 3000, "height": 2500},
                 "ready": True},
    "technical_details": [
        {"label": "Exhaust airflow", "value": "10000 m3/h", "origin": "rule"},
        {"label": "Spray nozzles", "value": "12 nos", "origin": "rule"},
        {"label": "Pump capacity", "value": "5 HP", "origin": "reused"},
    ],
}
full = build_drawing(SCRUB, client="ABC Engineering",
                     title_block={"drawn": "LR", "checked": "MS", "rev": "1"},
                     revisions=[{"rev": "0", "description": "Initial draft", "date": "02-08-2026"},
                                {"rev": "1", "description": "Tank revised", "date": "02-08-2026"}])
check("ITEM LIST" in full["svg"] and "Spray nozzles" in full["svg"],
      "the sheet carries an item list, not just balloons")
check("REVISIONS" in full["svg"] and "Initial draft" in full["svg"],
      "the sheet states which revision it is and what changed")
check(full["title_block"]["duty"] == "Exhaust airflow: 10000 m3/h",
      f"the title block states the DUTY, so a GA says which machine it is "
      f"({full['title_block'].get('duty')})")
check("MS" in full["svg"] and "ABC Engineering" in full["svg"],
      "checked-by and client reach the title block")
# Gas path. The captions read GAS rather than AIR on a scrubber, and the OUTLET
# arrow is deliberately UNLABELLED — captioned, its text straddled the envelope's
# top edge and its arrowhead was drawn through the blower. The balloon and the
# legend name the outlet, so the direction is still stated without the collision.
check("GAS IN" in full["svg"],
      "gas entry direction is shown - how the machine works, never a set-out")
check(full["svg"].count("stroke-dasharray") > 0 and "Outlet duct" in
      " ".join(l["description"] for l in full["legend"]),
      "the outlet is identified by its balloon rather than a clipped caption")

bare = build_drawing(SCRUB)
check("REVISIONS" not in bare["svg"],
      "with no revision history the sheet does not print an empty block")

# The studio has offered Plan-only / Elevations-only since it was built, and
# nothing consumed it: picking either silently produced the full three-view GA.
check([v["key"] for v in build_drawing(SCRUB, drawing_type="ga")["views"]]
      == ["plan", "front", "side"], "drawing type 'ga' gives all three views")
check([v["key"] for v in build_drawing(SCRUB, drawing_type="plan")["views"]] == ["plan"],
      "drawing type 'plan' gives the plan alone")
check([v["key"] for v in build_drawing(SCRUB, drawing_type="elevation")["views"]]
      == ["front", "side"], "drawing type 'elevation' drops the plan")
check([v["key"] for v in build_drawing(SCRUB, drawing_type="nonsense")["views"]]
      == ["plan", "front", "side"], "an unknown drawing type falls back to the full GA")

# Nothing a glyph draws may escape the sheet -- re-checked with the new
# airflow arrows and the relocated pump.
coords = [float(v) for v in re.findall(r'(?:x|cx|x1|x2)="(-?\d+\.?\d*)"', full["svg"])]
check(min(coords) >= 0 and max(coords) <= 420,
      "airflow arrows and the pump stay inside the sheet")

# --- Dust collector and powder coating plant -------------------------------
# Both categories drew an almost EMPTY sheet, and the cause was not the glyphs:
# neither is "adaptable", so the router resolved them from knowledge and handed
# the drawing an empty row list. These pin the component set that reaching the
# glyph with real rows produces.
DUST = {
    "category": "dust_collector", "category_label": "Dust Collector",
    "geometry": {"envelope_mm": {"length": 2500, "width": 1200, "height": 1200},
                 "ready": True},
    "technical_details": [
        {"label": "Filter bags", "value": "cartridge polyester, Dia 225 x 1000mm - 24 nos"},
        {"label": "Solenoid valve", "value": "2 inch - 4 nos"},
        {"label": "Blower type", "value": "centrifugal"},
        {"label": "Blower motor (HP)", "value": "25"},
        {"label": "Rotary airlock", "value": "0.5 HP"},
        {"label": "Suction ducts", "value": "MS 2mm Dia 114 to 400mm - 135m"},
        {"label": "Exhaust duct", "value": "MS 2mm Dia 500mm - 6m"},
        {"label": "Casing & hopper MOC", "value": "MS 3mm"},
        {"label": "Control panel", "value": "VFD ABB, PLC Delta"},
        {"label": "Cleaning system", "value": "To be determined", "origin": "tbd"},
    ],
}
dust = build_drawing(DUST)
dust_desc = " | ".join(d for _, d in
                       [(l["tag"], l["description"]) for l in dust["legend"]])
check("Filter element (24 nos)" in dust_desc,
      "the dust collector draws its REAL filter-element count")
check("solenoid valve (4 nos)" in dust_desc.lower() and "pulse-jet" in dust_desc.lower(),
      "pulse-jet header and solenoid count come from the spec")
check("Differential pressure gauge" in dust_desc, "the collector carries its DP gauge")
check("Rotary airlock 0.5 HP" in dust_desc, "the rotary airlock states its rating")
check("ID fan centrifugal 25 HP" in dust_desc,
      "the ID fan names type and rating -- it printed a bare 'ID fan HP' when neither resolved")
check("DIRTY AIR IN" in dust["svg"], "dirty-air inlet direction is shown")
check(len(dust["legend"]) >= 10,
      f"the collector sheet is populated, not a bare casing ({len(dust['legend'])} legend rows)")

# A value that did NOT resolve must not be dressed up as equipment.
thin = build_drawing({**DUST, "technical_details": [
    {"label": "Blower type", "value": "To be determined", "origin": "tbd"}]})
thin_desc = " | ".join(l["description"] for l in thin["legend"])
check("ID fan HP" not in thin_desc and "ID fan" in thin_desc,
      "with no fan data the legend never prints a bare 'ID fan HP' with a missing value")

PLANT = {
    "category": "powder_coating_plant", "category_label": "Powder Coating Plant",
    "geometry": {"envelope_mm": {"length": 3000, "width": 2000, "height": 2500},
                 "ready": True},
    "technical_details": [
        {"label": "Powder coating booth",
         "value": "Booth type: downside draft; Inner size (m): 3L x 1.9W x 2.5H",
         "parts": {"booth_type": "downside draft", "inner_size_m": "3L x 1.9W x 2.5H"}},
        {"label": "Curing oven", "value": "Oven type: batch; Inner size (m): 3.0L x 1.8W x 2.5H",
         "parts": {"oven_type": "batch", "inner_size_m": "3.0L x 1.8W x 2.5H"}},
        {"label": "Material handling", "value": "Type: overhead manual push-pull; Track length (m): 35",
         "parts": {"type": "overhead manual push-pull", "track_length_m": 35}},
        {"label": "Pretreatment", "value": "To be determined", "origin": "tbd"},
    ],
}
plant = build_drawing(PLANT)
plant_desc = " | ".join(l["description"] for l in plant["legend"])
check("PROCESS SEQUENCE" in plant["svg"] and "POWDER BOOTH" in plant["svg"]
      and "CURING OVEN" in plant["svg"],
      "the plant draws its process line, not an empty component box")
check("PRETREATMENT" not in plant["svg"],
      "a TBD station is NOT drawn as though the plant has it")
check("35 m track" in plant_desc, "the conveyor track length reaches the sheet")
check("component exceeds reused booth opening" in plant_desc.lower(),
      "a component larger than the reused booth opening is FLAGGED, not silently drawn")
check("Inner size (m): 3L x 1.9W x 2.5H" in plant_desc,
      "a composite module reads as engineering text, never a Python dict repr")
check("{" not in plant_desc and "'" not in plant_desc,
      "no raw dict punctuation leaks into the legend")

# A module opening equal to the envelope must not be drawn on top of the outline.
same = build_drawing({**PLANT, "technical_details": [
    {"label": "Powder coating booth", "value": "Inner size (m): 3L x 2W x 2.5H",
     "parts": {"inner_size_m": "3L x 2W x 2.5H"}}]})
same_desc = " | ".join(l["description"] for l in same["legend"])
check("exceeds reused booth" not in same_desc.lower(),
      "a booth that DOES clear the component raises no false clash")

# --- Sheet text ------------------------------------------------------------
check(sheet._wrap("short line", 40) == ["short line"], "a short description is left alone")
long_wrap = sheet._wrap("Powder coating booth: Booth type: downside draft; "
                        "Inner size (m): 3L x 1.9W x 2.5H; MOC: mild steel panels", 60)
check(len(long_wrap) == 2 and all(len(l) <= 60 for l in long_wrap),
      "a long description wraps within the column instead of being sliced")
check(not any(l.endswith(("boo", "Inne", "mil")) for l in long_wrap),
      "wrapping breaks at spaces, never mid-word")
check(sheet._wrap("a " * 200, 40)[-1].endswith("..."),
      "text beyond the cap runs out with an ellipsis, so it reads as continuing")

print()
if FAILS:
    print(f"{len(FAILS)} DRAWING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL DRAWING TESTS PASS")
