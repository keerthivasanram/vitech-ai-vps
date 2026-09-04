"""Guards for the 2D GA drawing engine (`app/drawing/`).

The engine's contract is the same as the spec engine's: deterministic output,
and an unknown dimension surfaces as a TBD rather than a drawn line. These tests
pin both, plus the SVG structure the studio depends on (one <g> per layer).

Run after any change under `app/drawing/`.
"""
import re
import sys

from app.drawing import sheet, style, views
from app.api.support import _spec_for_drawing
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
# 1:40, not 1:50, since 2026-09-04: the scale ladder jumped 1:25 -> 1:50 and
# this booth fell all the way down, drawing at half the size the paper could
# carry. The value is asserted rather than merely "is a standard scale" because
# the scale is what every dimension on the sheet is true AT — a silent change
# here would rescale the whole drawing.
check(a["scale"] == "1:40" and a["scale_divisor"] == 40, f"a standard scale is chosen ({a['scale']})")
check([v["key"] for v in a["views"]] == ["plan", "front", "side"],
      "third-angle layout places plan, front and side")

# --- The honest-gap contract ----------------------------------------------
# THE CONTRACT CHANGED DELIBERATELY, and this is the harder version of it. A
# sheet with no engineered size used to draw nothing and print "NO DIMENSIONED
# VIEWS". It now draws a PRELIMINARY SCHEMATIC — which is more useful and more
# dangerous, so what is asserted here is no longer "nothing was drawn" but
# "nothing was CLAIMED": no scale, no number against any axis, and the sheet
# saying on its face that it is not for fabrication.
nd = build_drawing(NO_DIMS)
check(nd["scale"] == "NTS" and nd["scale_divisor"] is not None,
      "no scale is claimed when nothing is dimensioned")
check(nd["state"] == "schematic", f"the state is named ({nd['state']})")
check("PRELIMINARY SCHEMATIC - NOT FOR FABRICATION" in nd["svg"],
      "the schematic says it is not for fabrication, on the sheet")
check("DIMENSIONS PENDING ENGINEERING / CLIENT CONFIRMATION" in nd["svg"],
      "the schematic says the dimensions are pending")
# Abbreviated in the title block because the cell is ~13 mm; the unabbreviated
# claim lives on the sheet face and in the payload's `state`.
check(nd["title_block"]["status"] == "PRELIM",
      f"the title block states PRELIM (got {nd['title_block']['status']})")
check(nd["state_label"].lower().startswith("preliminary"),
      f"the payload carries the unabbreviated state ({nd['state_label']})")
# The load-bearing one: a schematic must not put a NUMBER against any overall
# extent, so no reader and no exporter can take a size off it. A real dimension
# is a `Dim` on the DIMENSION layer; a schematic draws none, and every extent
# is captioned TBD instead. Asserting the layer is absent is stronger than
# scanning text — it cannot be satisfied by a dimension that merely looks odd.
check('id="layer-dimension"' not in nd["svg"],
      "a schematic emits no dimension layer at all")
for _axis in ("LENGTH", "WIDTH", "HEIGHT"):
    check(f"OVERALL {_axis} - TBD" in nd["svg"],
          f"the schematic captions overall {_axis.lower()} as TBD")
check(nd["missing_axes"] == ["length", "width", "height"],
      "every unresolved axis is reported")
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

# --- Equipment TYPE is resolved by engineering, not sniffed by the renderer --
# A wet scrubber is two different machines in Vitech's archive. Which one it is
# decides the geometry model, so the type is an ENGINEERING output that travels
# with the envelope — the drawing must never re-decide it from row labels.
from app.engineering.geometry_service import (TYPE_HORIZONTAL_BAFFLE,
                                              TYPE_SPRAY_TOWER, resolve_geometry)

g = resolve_geometry("wet_scrubber", SCRUBBER_ROWS)
check(g.equipment_type == TYPE_SPRAY_TOWER and g.envelope == {"length": 750, "width": 750, "height": 4000},
      f"a stated tower diameter resolves a VERTICAL SPRAY TOWER ({g.equipment_type})")
check(g.basis.get("height", "").startswith("tower height"),
      "the envelope reports the basis of each axis, not just the number")

# THE DEFECT THIS FIXES. The archive holds one horizontal baffle unit, and when
# it is the nearest offer its wording reaches the spec as a REUSED row. A client
# who stated a tower diameter has specified a vertical tower, so the requirement
# wins and the contradiction is REPORTED rather than silently resolved.
g2 = resolve_geometry("wet_scrubber", SCRUBBER_ROWS + [
    {"label": "Scrubber type", "value": "horizontal baffle plate - blower mounted over scrubber",
     "origin": "reused"}])
check(g2.equipment_type == TYPE_SPRAY_TOWER and g2.envelope == g.envelope,
      "a client-stated tower outranks a REUSED baffle description")
check(any("confirm the scrubber type" in c for c in g2.conflicts),
      f"the type contradiction is reported to the engineer ({g2.conflicts})")

# A horizontal baffle unit with no engineered height must NOT be drawn. Vitech
# has supplied no height rule for this type and the archived casing belongs to a
# different machine, so the honest answer is no envelope plus a stated reason.
g3 = resolve_geometry("wet_scrubber", [
    {"label": "Scrubber type", "value": "horizontal baffle plate", "origin": "reused"},
    {"label": "Scrubber dimension", "value": "700mm W x 1700mm L", "origin": "reused"}])
check(g3.equipment_type == TYPE_HORIZONTAL_BAFFLE and g3.envelope is None,
      "a horizontal baffle unit with no height rule yields NO envelope")
check(any("no height rule" in c for c in g3.conflicts),
      f"and says why, so the gap is a request rather than a silence ({g3.conflicts})")

# --- A client-stated value must survive a nearest offer that lacks the field --
# THE ROOT CAUSE of the blank scrubber sheet: the planner walked the nearest
# offer's field set, so a value the CLIENT STATED or a RULE COMPUTED vanished
# whenever that offer did not carry the field. The profile declares the field
# set; history only fills it.
from app.resolver import ATS, resolve
from app.retriever import retrieve
from app.schema import QueryUnderstanding

_u = QueryUnderstanding(intent="specification", category="wet_scrubber",
                        parameters={"air_volume_cfm": 800, "tower_diameter_mm": 750, "qty": 4},
                        source="regex")
_a = resolve("wet scrubber for 800 cfm 750mm tower 4 nos",
             retrieve("wet scrubber for 800 cfm 750mm tower 4 nos", top_k=10,
                      where={"category": "wet_scrubber"}), _u, ATS)
_rows = {r["label"]: r for r in _a.get("technical_details") or []}
check(_rows.get("Tower diameter (mm)", {}).get("origin") == "given",
      "the client's stated tower diameter reaches the spec even when the nearest "
      "offer has no such field")
check(_rows.get("Tower height (m)", {}).get("origin") == "rule",
      "and the rule-computed tower height with it")

_geom = _a.get("geometry") or {}
_env = build_drawing({"category": "wet_scrubber", "category_label": "Wet Scrubber",
                      "geometry": {"envelope_mm": resolve_geometry(
                          "wet_scrubber", _a.get("technical_details") or []).envelope,
                                   "ready": True},
                      "technical_details": _a.get("technical_details") or []})
check(len(_env["views"]) == 3 and _env["scale"] != "NTS",
      "so the flagship wet scrubber draws a real GA instead of a blank sheet")
check(len(_env["legend"]) > 5,
      f"and its component glyph actually runs ({len(_env['legend'])} legend rows)")

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
# --- DESIGN DATA table + KEY DIMENSIONS (composed, never computed) ----------
from app.drawing.drawing_service import _design_data, _key_dimensions
from app.drawing import sheet as _sheet, title_block as _tb
from app.drawing.primitives import Text as _Text, L_TEXT as _L_TEXT

_SCRUB = _spec_for_drawing("wet scrubber 800 cfm 750mm tower 4 nos")
_d = build_drawing(_SCRUB)

check(len(_d["design_data"]) > 0, "the sheet carries a DESIGN DATA block")
check("DESIGN DATA" in _d["svg"], "and it is actually drawn on the sheet")

# PARTITION, not a sample: every resolved row is in exactly one of the two
# tables, so no resolved value is silently dropped from the drawing.
_bom_labels = {r["item"] for r in _d["bom"]}
_data_labels = {r["label"] for r in _d["design_data"]}
check(not (_bom_labels & _data_labels),
      "design data and the item list never contain the same row twice")
_resolved = {str(r["label"]) for r in _SCRUB["technical_details"]
             if str(r.get("value", "")).strip().lower() not in ("", "to be determined")
             and r.get("origin") != "tbd"}
check(_resolved <= (_bom_labels | _data_labels),
      f"every resolved row lands in one of the two tables "
      f"(missing: {sorted(_resolved - (_bom_labels | _data_labels))})")
check(not any(str(r["value"]).lower() == "to be determined" for r in _d["design_data"]),
      "a TBD is never printed as design data - it is scheduled separately")

# The engineering engine owns every printed value; the table composes only.
for _r in _d["design_data"]:
    _src = [t for t in _SCRUB["technical_details"] if t["label"] == _r["label"]]
    check(bool(_src) and str(_src[0]["value"]).strip() == _r["value"],
          f"design data value for {_r['label']!r} is reproduced verbatim from the spec")
    break

# --- Diameter annotation comes from the resolved TYPE, not a label guess ----
check(any(r["value"].startswith("\u00d8") for r in _d["key_dimensions"]),
      f"a stated bore is scheduled with the diameter symbol ({_d['key_dimensions']})")
check("\u00d8750" in _d["svg"],
      "a circular footprint is DIMENSIONED as a diameter, not as a square casing")

_booth = build_drawing(_spec_for_drawing("paint booth 5m x 3m x 4m"))
check(not any("\u00d8" in str(v) for v in
              [_l for _l in re.findall(r'>([^<]*)</text>', _booth["svg"])
               if _l.strip().isdigit()]),
      "a rectangular booth's overall dimensions are NOT marked as diameters")
_duct = [r for r in _booth["key_dimensions"] if "duct" in r["label"].lower()]
check(_duct and "dia" not in _duct[0]["value"].lower(),
      f"the symbol replaces the word - never '\u00d8 600 mm dia' ({_duct})")

# A historical-only dimension must never be scheduled: it is a different
# machine's casing, which is exactly what the trust rule exists to refuse.
check(_key_dimensions({"technical_details": [
        {"label": "Collector size (m)", "value": "2.15L x 1.15W x 4.95H",
         "origin": "reused"}]}) == [],
      "a REUSED size is never presented as a dimension of this machine")
check(len(_key_dimensions({"technical_details": [
        {"label": "Collector size (m)", "value": "2.15L x 1.15W x 4.95H",
         "origin": "given"}]})) == 1,
      "the same size stated by the CLIENT is scheduled")
check(_key_dimensions({"technical_details": [
        {"label": "Spray nozzles (nos)", "value": "19", "origin": "rule"}]}) == [],
      "a COUNT is not mistaken for a dimension")

# --- The side column is bounded by the title block --------------------------
# Verified defect: on A4 the notes printed straight over the title block.
for _size in ("A4", "A3"):
    _c, _pkg = compose(_spec_for_drawing("dust collector 9000 m3/h casing 3m x 2m x 5m"),
                       sheet_size=_size)
    _sw, _sh = _sheet.SHEET_SIZES[_size]
    _top = _sh - _sheet.MARGIN - _tb.TB_H
    _left = _sw - _sheet.MARGIN - _tb.TB_W
    _bad = [s for s in _c.shapes if isinstance(s, _Text) and s.layer == _L_TEXT
            and s.y > _top and s.x > _left - 2]
    check(not _bad, f"{_size}: the notes column never prints over the title block "
                    f"({len(_bad)} intruding)")

# The standing notes are NOT optional: they state that positions are indicative
# and that the sheet is a draft not released for construction (golden rule #3).
# A full column dropped them, because they were drawn last. Their space is now
# reserved, so a busier sheet truncates a schedule instead of a safety statement.
from app.drawing.drawing_service import STANDING_NOTES as _NOTES
for _q in ("paint booth 5m x 3m x 4m",
           "dust collector 9000 m3/h casing 3m x 2m x 5m",
           "wet scrubber 800 cfm 750mm tower 4 nos"):
    for _size in ("A4", "A3"):
        _pkg = build_drawing(_spec_for_drawing(_q), sheet_size=_size)
        check(all(_n[:40] in _pkg["svg"] for _n in _NOTES),
              f"{_size}: every standing note survives a full column ({_q[:26]})")


# --- the optional isometric ------------------------------------------------
from app.drawing import isometric as _iso

_plain = build_drawing(BOOTH)
_withiso = build_drawing(BOOTH, drawing_type="ga_iso")
check("ISOMETRIC" not in _plain["svg"], "a plain GA carries no pictorial")
check("ISOMETRIC" in _withiso["svg"], "ga_iso adds the pictorial")
check("NOT TO SCALE" in _withiso["svg"],
      "the pictorial says it cannot be measured off")
# It must add NO dimension: a pictorial is not to scale, so a number on it
# would be measurable from a view that is explicitly not measurable.
_iso_dims_plain = _plain["svg"].count('stroke-dasharray')
check(len(_withiso["views"]) == len(_plain["views"]),
      "the pictorial is not counted as a projected view")
# An unresolved axis means no pictorial at all, rather than an approximate box.
_partial_iso = build_drawing(
    {**BOOTH, "geometry": {"envelope_mm": {"length": 6000, "width": None,
                                           "height": 4000}, "ready": False}},
    drawing_type="ga_iso")
check("ISOMETRIC" not in _partial_iso["svg"],
      "a partly unknown envelope gets NO pictorial, not an approximate one")
# The projection itself: equal foreshortening, and the origin behind the solid.
_p0 = _iso.project(0, 0, 0)
_px = _iso.project(1000, 0, 0)
_py = _iso.project(0, 1000, 0)
_pz = _iso.project(0, 0, 1000)
import math as _m
_lx = _m.hypot(_px[0] - _p0[0], _px[1] - _p0[1])
_ly = _m.hypot(_py[0] - _p0[0], _py[1] - _p0[1])
_lz = _m.hypot(_pz[0] - _p0[0], _pz[1] - _p0[1])
check(abs(_lx - _ly) < 1e-9 and abs(_lx - _lz) < 1e-9,
      f"all three axes foreshorten equally ({_lx:.3f}/{_ly:.3f}/{_lz:.3f})")


# --- drafting detailing: sections, datums, real-thickness material --------
from app.drawing.symbols import SECTION_VIEWS, _mm_on_sheet, view_caption

_sec = build_drawing(BOOTH)
check("SECTION A-A" in _sec["svg"],
      "a view that shows internals is captioned as a section")
check("FRONT ELEVATION" not in _sec["svg"],
      "and is NOT also called an elevation")
# The mark and the view must agree: a cutting plane pointing at a view that
# shows nothing inside would tell the reader a drawing is missing.
for _cat in SECTION_VIEWS:
    check(_cat in SYMBOLS, f"{_cat} declares a section and has a glyph")
check(view_caption("conveyor", "front", "FRONT ELEVATION") == "FRONT ELEVATION",
      "a category with no declared section keeps its elevation caption")

# THE CAPTION AND THE MARK ARE ONE DECISION. On a plan too small to carry a
# legible cutting plane, the view must also stop calling itself a section —
# a section caption with no locating mark is a reference to a cut nobody can
# find, which is worse than an unlabelled elevation.
class _P:
    def __init__(s, w, h): s.w, s.h, s.x, s.y, s.key = w, h, 0.0, 0.0, "plan"
check(view_caption("paint_booth", "front", "FRONT ELEVATION",
                   {"plan": _P(120.0, 60.0)}) == "SECTION A-A",
      "a plan with room keeps the section caption")
check(view_caption("paint_booth", "front", "FRONT ELEVATION",
                   {"plan": _P(30.0, 35.0)}) == "FRONT ELEVATION",
      "a plan too narrow for the mark drops the caption with it")
check(view_caption("paint_booth", "front", "FRONT ELEVATION", {}) == "FRONT ELEVATION",
      "no plan at all means no section reference")
_narrow = build_drawing(_spec_for_drawing("wet scrubber 800 cfm 750mm tower 4 nos"))
check("SECTION A-A" not in _narrow["svg"],
      "the real narrow-tower case drops the section reference end to end")

# Levels are a reading convention over values already on the sheet, so they may
# only appear where a real height was resolved.
check("FFL 0.000" in _sec["svg"] and "+4.000" in _sec["svg"],
      "floor and height datums are marked on a dimensioned elevation")
check("FFL 0.000" not in nd["svg"],
      "a SCHEMATIC carries no level marker -- it would be the one number on it")

# Real-thickness material is drawn only when the spec states a thickness.
class _V:
    def __init__(s, w, h, mw, mh): s.w, s.h, s.model_w, s.model_h = w, h, mw, mh
_v = _V(120.0, 80.0, 6000, 4000)          # 1:50
check(abs((_mm_on_sheet("100 mm rockwool", _v) or 0) - 2.0) < 0.01,
      "a stated 100 mm reads as 2 mm of sheet at 1:50")
check(_mm_on_sheet("rockwool", _v) is None,
      "a value stating no thickness gets no drawn thickness")
check(_mm_on_sheet("50", _v) is None,
      "a bare number is not read as a thickness")
check(_mm_on_sheet("10 mm", _v) is None,
      "a thickness too thin to print legibly is refused, not smudged")
check(_mm_on_sheet("3000 mm", _v) is None,
      "an implausible thickness cannot swallow the view")
check(_mm_on_sheet("100 mm", _V(120.0, 80.0, None, None)) is None,
      "no model dimension means no real-thickness conversion")


# --- a component must clear BOTH apertures, not just the booth ------------
# `oven_m` was parsed and never used: the curing oven's inner opening is
# resolved from the same composite field the booth's is, and a component has to
# pass through both. Checking only the booth cleared a component the oven
# cannot take — the more expensive of the two to discover late.
_pp = [{"label": "Powder coating booth", "value": "inner size 3.0L x 2.0W x 2.5H",
        "parts": {"inner_size_m": "3.0L x 2.0W x 2.5H"}},
       {"label": "Curing oven", "value": "inner size 3.0L x 2.0W x 1.8H",
        "parts": {"inner_size_m": "3.0L x 2.0W x 1.8H"}}]
_pd = build_drawing({"category": "powder_coating_plant", "category_label": "P",
                     "geometry": {"envelope_mm": {"length": 2500, "width": 1500,
                                                  "height": 2200}, "ready": True},
                     "technical_details": _pp})
_checks = [r["description"] for r in _pd["legend"] if "CHECK" in r["description"]]
check(any("curing oven" in c and "height" in c for c in _checks),
      f"a component too tall for the curing oven is reported ({_checks})")
check(not any("booth" in c for c in _checks),
      "and the booth, which the component DOES clear, is not reported")
check("CURING OVEN INNER OPENING" in _pd["svg"],
      "the oven opening is drawn, not just parsed")


# --- the three drawing states ---------------------------------------------
# One classifier decides all fourteen categories, so these are asserted on the
# state machine itself as well as through a rendered sheet.
from app.drawing import states as _states

check(_states.classify({"length": 6000, "width": 3000, "height": 4000}).state
      == _states.FULL, "all three axes -> fully dimensioned")
check(_states.classify({"length": 6000, "width": None, "height": 4000}).state
      == _states.PARTIAL, "a missing axis -> partially dimensioned")
check(_states.classify({}).state == _states.SCHEMATIC, "no axis -> schematic")
# A zero is not a dimension. Treating it as one is how a machine 0 mm wide gets
# drawn to scale, and it is the commonest way a bad parse reaches a sheet.
check(_states.classify({"length": 0, "width": 0, "height": 0}).state
      == _states.SCHEMATIC, "a zero is not a dimension")
check(_states.classify({"length": "6000", "width": 3000, "height": 4000}).state
      == _states.PARTIAL, "a string is not a dimension")

_PART = {"category": "hot_air_oven", "category_label": "Hot Air Oven",
         "geometry": {"envelope_mm": {"length": 6000, "width": None,
                                      "height": 4000}, "ready": False},
         "technical_details": [{"label": "Chamber", "value": "To be determined",
                                "origin": "tbd"}]}
_p = build_drawing(_PART)
check(_p["state"] == "partially_dimensioned", f"partial state named ({_p['state']})")
check(_p["scale"].startswith("1:"), "a partial sheet still carries a REAL scale")
check([v["key"] for v in _p["views"]] == ["front"],
      f"only the view the dimensions support is drawn ({[v['key'] for v in _p['views']]})")
check("PARTIALLY DIMENSIONED" in _p["svg"], "a partial sheet says it is partial")
check("width" in _p["missing_axes"] and len(_p["missing_axes"]) == 1,
      f"the unresolved axis is named ({_p['missing_axes']})")
# The one that prevents the worst misreading: a view that could not be drawn is
# declared absent, so nobody assumes the machine simply has no side to show.
check("omitted for want of a dimension" in _p["svg"],
      "an undrawable view is declared, not silently missing")
check(_p["title_block"]["status"] == "DRAFT",
      "a partial sheet is a DRAFT, not PRELIMINARY -- it carries real dimensions")

# Every unresolved row carries the action that clears it, and the axes come
# first because they are what blocks a dimensioned GA.
_u = build_drawing(NO_DIMS)["unresolved"]
check(_u and all(r.get("action") for r in _u),
      "every unresolved row names the action that clears it")
check([r["parameter"] for r in _u][:3]
      == ["Overall length", "Overall width", "Overall height"],
      "the blocking geometry rows are scheduled first")
check(all(r["kind"] == "geometry" for r in _u[:3]),
      "the axes are classified as geometry")
# An engineering output must never be sent to the customer to answer.
check(_states.action_for("Heating capacity (kcal/hr)").startswith("Engineering"),
      "a computed output is an engineering action, not a customer question")
check("customer" in _states.action_for("Material handling").lower(),
      "a process input is a customer question")


# --- a dashed line belongs to the layer its dash claims -------------------
# The studio renders one <g> per layer and toggles it, so a centre line drawn
# on the COMPONENT layer is one the "Centre lines" switch cannot turn off. Ten
# glyphs drew their own centre and hidden lines by hand on the component layer
# while the library drew the identical thing on the right one, so the same
# toggle worked for a duct axis and not for a conveyor axis on the same sheet.
_D_CENTRE, _D_HIDDEN = "6,1.5,1.5,1.5", "2,1.5"
for _cat in SYMBOLS:
    _svg = build_drawing({"category": _cat, "category_label": _cat,
                          "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                       "height": 4000}, "ready": True},
                          "technical_details": [
                              {"label": "Conveyor", "value": "overhead"},
                              {"label": "Zones", "value": "3"},
                              {"label": "Tower diameter", "value": "750 mm"},
                              {"label": "Illumination", "value": "LED 6 nos"}]})["svg"]
    _m = re.search(r'<g[^>]*id="layer-component"[^>]*>(.*?)</g>', _svg, re.S)
    _body = _m.group(1) if _m else ""
    # An OPENING legitimately keeps the hidden dash on the component layer, so
    # the test discriminates by WEIGHT rather than exempting whole glyphs:
    # stranded hidden detail is LIGHT, an opening is MEDIUM.
    _dashed = re.findall(r'stroke-dasharray="([^"]*)"[^>]*stroke-width="([^"]*)"'
                         r'|stroke-width="([^"]*)"[^>]*stroke-dasharray="([^"]*)"', _body)
    _pairs = [(d or d2, w or w2) for d, w, w2, d2 in _dashed]
    _light = f"{style.W_LIGHT:g}"
    _stray_c = sum(1 for d, _w in _pairs if d == _D_CENTRE)
    _stray_h = sum(1 for d, w in _pairs if d == _D_HIDDEN and w == _light)
    check(_stray_c == 0,
          f"{_cat}: no centre line stranded on the component layer ({_stray_c})")
    check(_stray_h == 0,
          f"{_cat}: no hidden detail stranded on the component layer ({_stray_h})")

# An OPENING is the deliberate exception: a void in the enclosure is a real
# feature in front of the viewer, so it keeps the hidden DASH to read as an
# absence of panel while staying a component. It is a MEDIUM weight, which is
# what distinguishes it from hidden detail at a glance.
from app.drawing.style import HIDDEN_LINE, OPENING, CENTRE_LINE, L_COMPONENT as _LC
check(OPENING.layer == _LC and OPENING.width > HIDDEN_LINE.width,
      "an OPENING stays a component and outweighs hidden detail")
check(CENTRE_LINE.layer != _LC and HIDDEN_LINE.layer != _LC,
      "centre and hidden roles live off the component layer")


# --- a Pen may only be splatted into a shape whose tail arg is `dash` ------
# `Line` and `Rect` end (layer, width, dash), so `*PEN` reads cleanly. `Circle`
# and `poly` end (layer, width, FILL) — splatting a Pen there silently passes
# the Pen's dash (None) as the fill, emitting fill="None". Under cairosvg that
# still renders hollow, so it is invisible on screen; but `export.py` treats any
# fill outside ("none", "", None) as SOLID, so the shape prints as a black blob
# in the PDF. A digest caught it once; this keeps it caught.
_FILL_OK = {"none", "", "currentColor"}
for _cat in SYMBOLS:
    _svg = build_drawing({"category": _cat, "category_label": _cat,
                          "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                                       "height": 4000}, "ready": True},
                          "technical_details": [
                              {"label": "Illumination", "value": "LED 6 nos"},
                              {"label": "Spray nozzle", "value": "8 nos"},
                              {"label": "Blower motor hp", "value": "15"}]})["svg"]
    _fills = set(re.findall(r'fill="([^"]*)"', _svg))
    _bad = sorted(f for f in _fills if f not in _FILL_OK)
    check(not _bad, f"{_cat}: every fill value is valid SVG (bad: {_bad})")


if FAILS:
    print(f"{len(FAILS)} DRAWING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL DRAWING TESTS PASS")
