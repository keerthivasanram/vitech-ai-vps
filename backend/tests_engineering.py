"""Guards for the client-supplied engineering data (received 2026-08-01).

Two client documents became executable engineering this session:
  * the Continental Thermal BLOWER SPECIFICATION CHART  -> blower_service
  * the paint-shop design-calculation document           -> paint_shop_service

The highest-value assertions here are the ones that pin our output to the
client's OWN real-world artefacts — above all the costed paint-booth BOM of
24.07.2026, whose blower line the selector must reproduce exactly. Run after any
change to `app/engineering/`.
"""
import sys

from app.engineering import paint_shop_service as ps
from app.engineering import booth_catalogue as bcat
from app.engineering import design_standards as ds_mod
from app.engineering import standards_service as std
from app.engineering.blower_service import (PAINT_BOOTH_SERIES, by_model, chart,
                                            select_blower, select_booth_blower,
                                            select_booth_blower_set, select_in_series,
                                            series_of)
from app.engineering import voc_service as voc
from app.engineering import scrubber_service as sc
from app.engineering import material_service as mat
from app.engineering import heat_load_service as hl
from app.engineering.formula_service import compute_spec

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# --- The vendor chart itself ----------------------------------------------
rows = chart()
check(len(rows) > 190, f"blower chart loaded ({len(rows)} models)")
check(all(b.cfm > 0 and b.motor_hp > 0 for b in rows), "every model has a positive CFM and motor HP")
check(all(b.static_pressure_mmwc <= b.total_pressure_mmwc for b in rows),
      "static pressure never exceeds total pressure")
check(len({b.model for b in rows}) == len(rows), "model codes are unique")

# --- THE ANCHOR: reproduce the client's own costed BOM ---------------------
# BOM line 24: 'Blower  CLP-4" WC-10 HP-9000Cfm-Direct Drive'
anchor = select_booth_blower(9000)
check(anchor is not None and anchor.model == "CLP-4-10-9000",
      "client BOM anchor: 9000 CFM booth duty selects CLP-4-10-9000")
check(anchor is not None and anchor.motor_hp == 10,
      "client BOM anchor: selected blower is the 10 HP machine")
check(anchor is not None and anchor.drive == "direct drive",
      "client BOM anchor: selected blower is direct drive")

# --- Selection semantics ---------------------------------------------------
check(by_model("CLP-4-10-9000") is not None and by_model("NOPE-1-1") is None,
      "exact catalogue lookup resolves a real model and rejects an unknown one")
check(series_of("CLP-4-10-9000") == "CLP-4" and series_of("CHPT-48-60-4900") == "CHPT-48",
      "series prefix parses for both 2- and 4-character series names")

b = select_booth_blower(9001)
check(b is not None and b.cfm >= 9001, "selection never under-sizes (9001 CFM -> a larger machine)")
check(all(series_of(select_booth_blower(c).model) == PAINT_BOOTH_SERIES
          for c in (900, 5000, 9000, 20000, 61000)),
      "booth selection stays inside the pressure class the client actually builds")

# Monotonic: a larger duty never selects a smaller motor.
hps = [select_booth_blower(c).motor_hp for c in (1000, 5000, 9000, 15000, 25000, 40000)]
check(hps == sorted(hps), f"motor HP rises monotonically with duty ({hps})")

check(select_booth_blower(10 ** 9) is None,
      "a duty beyond the catalogue returns None (caller emits TBD, never a guess)")
check(select_blower(-5) is None and select_blower(0) is None,
      "non-positive duty is rejected rather than silently selected")

big, qty = select_booth_blower_set(150000)
check(big is not None and qty > 1, f"an over-range duty splits across {qty} of the largest model")
one, qty1 = select_booth_blower_set(9000)
check(qty1 == 1 and one.model == "CLP-4-10-9000", "an in-range duty uses exactly one machine")

# Static-pressure filtering actually binds on the generic path.
hi = select_blower(2000, static_pressure_mmwc=1000)
check(hi is not None and hi.static_pressure_mmwc >= 1000,
      "generic selection honours a high static-pressure requirement")
check(select_in_series(10 ** 9, PAINT_BOOTH_SERIES) is None,
      "in-series selection returns None rather than overflowing the series")

# --- The client's paint-shop calculation document --------------------------
# "Exhaust Air Volume : Area x Velocity"; area depends on the draft direction.
cross = ps.compute_paint_shop_unit("paint_booth", 5, 3, 4, draft=ps.Draft.CROSS)
side = ps.compute_paint_shop_unit("paint_booth", 5, 3, 4, draft=ps.Draft.SIDE)
down = ps.compute_paint_shop_unit("paint_booth", 5, 3, 4, draft=ps.Draft.DOWN)
check(cross.face_area_m2 == 3 * 4, "cross draft uses the end face (width x height)")
check(side.face_area_m2 == 5 * 4, "side draft uses the side face (length x height)")
check(down.face_area_m2 == 5 * 3, "down draft uses the plan area (length x width)")
check(abs(cross.exhaust_cmh - (12 * ps.DEFAULT_FACE_VELOCITY * 3600)) < 1e-6,
      "exhaust = area x velocity x 3600")

# DQ-2, adopted 2026-09-01: the face velocity is the CLIENT's 0.5 m/s, from
# `Standard Booth.xlsx`, not the NFPA 33 default we used while they were silent.
check(ps.DEFAULT_FACE_VELOCITY == 0.50, "face velocity is the client's stated 0.5 m/s")
std_booth = ps.compute_paint_shop_unit("paint_booth", 3.0, 2.25, 2.4, draft=ps.Draft.SIDE)
check(round(std_booth.exhaust_cmh) == 12960,
      f"standard-booth anchor: 3000 x 2400 face -> 12,960 CMH (got {std_booth.exhaust_cmh})")
for _t in ("cross_draft", "side_draft", "semi_down_draft"):
    check(ds_mod.BOOTH_TYPES[_t].velocity == 0.50, f"{_t} designs to 0.5 m/s")
check(ds_mod.BOOTH_TYPES["full_down_draft"].velocity == 0.35
      and ds_mod.BOOTH_TYPES["powder"].velocity == 0.55,
      "DQ-2 did not touch the types the client's face-based table does not describe")

# The override is what makes 0.5 a default rather than a hard-coded law.
_ovr = compute_spec(5, 3, 4, "liquid", "cross draft", face_velocity=0.45)
_ovr_row = next(r for r in _ovr.rules if r.name == "Exhaust airflow")
check("19440" in _ovr_row.value, f"a stated face velocity overrides the table (got {_ovr_row.value})")
check("stated for this design" in _ovr_row.formula,
      "the rule trail says the velocity was stated, not taken from the table")

# "Inlet Air volume": +10% rooms/zones, -10% booths, nil for a side-draft booth.
check(side.inlet_cmh is None, "side-draft paint booth has NIL forced inlet air")
check(abs(cross.inlet_cmh - cross.exhaust_cmh * 0.90) < 1e-6,
      "cross-draft paint booth inlet is 10% LESS than exhaust (negative pressure)")
check(abs(down.inlet_cmh - down.exhaust_cmh * 0.90) < 1e-6,
      "down-draft paint booth inlet is 10% less than exhaust")
for unit in ("cleaning_room", "buffing_booth", "flash_off_zone"):
    c = ps.compute_paint_shop_unit(unit, 5, 3, 4, draft=ps.Draft.DOWN)
    check(abs(c.inlet_cmh - c.exhaust_cmh * 1.10) < 1e-6,
          f"{unit} inlet is 10% MORE than exhaust (positive pressure)")

# "Material weight : Total Surface area (5 Sides - bottom side neglected)"
area = ps.enclosure_surface_area(5, 3, 4)
check(abs(area - (2 * 5 * 4 + 2 * 3 * 4 + 5 * 3)) < 1e-9,
      "surface area is 4 walls + roof, floor excluded")
check(abs(ps.sheet_weight_kg(10) - 10 * 0.002 * 7850) < 1e-9,
      "sheet weight uses the client's 2 mm MS basis at 7850 kg/m3")

# Oven: "Heat load : volume (ft3) / 100, 100 ft3 = 12 kW; kW x 860 = kCal"
kw, kcal = ps.oven_heat_load(5, 3, 4)
check(abs(kw - (60 * 35.3147 / 100 * 12)) < 1e-3, "oven heat load follows 100 ft3 = 12 kW")
check(abs(kcal - kw * 860) < 1e-6, "oven kCal is kW x 860")

# ACH has no invented default: without it there is simply no exhaust figure.
check(ps.compute_paint_shop_unit("paint_drying_oven", 5, 3, 4, ach=None).exhaust_cmh is None,
      "no ACH supplied -> no exhaust volume invented (honest gap -> TBD)")
check(ps.compute_paint_shop_unit("paint_drying_oven", 5, 3, 4, ach=20).exhaust_cmh == 60 * 20,
      "ACH supplied -> exhaust = volume x ACH")

check(ps.normalise_draft("wet cross draft") == ps.Draft.CROSS
      and ps.normalise_draft("Down-Draft") == ps.Draft.DOWN
      and ps.normalise_draft("dry type booth") is None,
      "draft text normalises, and unrecognised text stays None (no direction assumed)")

# Missing dimensions must not fabricate a design.
empty = ps.compute_paint_shop_unit("paint_booth", None, 3, 4)
check(empty.exhaust_cmh is None and empty.material_weight_kg is None,
      "incomplete dimensions produce no numbers at all")

# --- Integration: the booth spec engine emits catalogue-backed rows --------
spec = compute_spec(5, 3, 4, "liquid")
labels = {v.label: v.value for v in spec.values}
check(labels.get("Exhaust blower") == "CLP-4-15-14500", "booth spec names a real catalogue blower")
check(labels.get("Exhaust blower motor (HP)") == "15", "booth spec carries the catalogue motor HP")
check("Inlet air volume" in labels, "booth spec carries the client's inlet-air rule")
check("Enclosure sheet weight" in labels, "booth spec carries the 5-side material weight")

# Every emitted value must be matched by a rule carrying a formula + standard,
# so nothing can be mis-attributed to the customer as "given".
rule_names = {r.name for r in spec.rules}
unmatched = [v.label for v in spec.values
             if not any(n.lower() in v.label.lower() or v.label.lower() in n.lower()
                        for n in rule_names)]
check(unmatched == ["Dimensions", "Paint process"],
      f"only requirement echoes lack a rule; got {unmatched}")
check(all(r.standard and r.formula for r in spec.rules),
      "every rule cites both a formula and a governing standard")
check(any(r.standard == std.BLOWER_CHART_SELECTION for r in spec.rules),
      "blower rows cite the vendor chart as their standard")
check(any(r.standard == std.CLIENT_PAINT_SHOP_CALC for r in spec.rules),
      "inlet-air row cites the client's own calculation document")

# A booth whose duty exceeds the catalogue must degrade to no blower rows.
huge = compute_spec(400, 400, 400, "liquid")
huge_labels = {v.label for v in huge.values}
check("Exhaust airflow" in huge_labels, "an over-range booth still computes its airflow")


# ==========================================================================
# The 2026-09-01 calculation workbooks (docs/client-calculation-sheets.md).
# Each block pins our output to the sheet's OWN worked example wherever that
# example is reproducible from the inputs the sheet records. Where it is not,
# the missing input is asserted as a reported GAP rather than papered over.
# ==========================================================================

# --- VOC / LEL gate (workbook: Paint shop VOC calculation) ----------------
v = voc.assess_voc(paint_consumption_l_hr=10, voc_percent=60,
                   density_kg_l=1.2, airflow_cmh=10000)
check(round(v.voc_kg_hr, 3) == 7.2, f"VOC anchor: 10 l/hr x 1.2 kg/l x 60% = 7.2 kg/hr (got {v.voc_kg_hr})")
check(round(v.concentration_mg_m3) == 720,
      f"VOC anchor: 7.2 kg/hr into 10000 m3/h = 720 mg/m3 (got {v.concentration_mg_m3})")
check(v.verdict == voc.PASS, "VOC anchor: 720 mg/m3 passes the client's 1000 mg/m3 limit")
over = voc.assess_voc(20, 60, 1.2, 10000)
check(over.verdict == voc.FAIL, "double the paint consumption fails the same limit")
check(over.required_airflow_cmh and round(over.required_airflow_cmh) == 14400,
      f"a failing design states the airflow that would pass (got {over.required_airflow_cmh})")
unknown = voc.assess_voc(10, None, 1.2, 10000)
check(unknown.verdict is None and "VOC content" in unknown.reason,
      "an unanswered safety question is reported unanswered, never as a pass")
check(voc.assess_voc(10, 60, 1.2, 10000, solvent_lel_mg_m3=None).percent_lel is None,
      "no %LEL is reported without the solvent's own LEL (the sheet gives no molecular weight)")

# --- Heat load (workbook: Heat Load) --------------------------------------
tank = hl.tank_heat_load(2250, 1500, 1500, 25, 75, 750)
check(tank.kcal == 264125.0, f"tank anchor: 2250x1500x1500, 25->75 C, 750 kg steel = 264,125 Kcal (got {tank.kcal})")
check(tank.kw == 308, f"tank anchor: 264,125 Kcal = 308 kW (got {tank.kw})")
check(hl.kw_from_kcal(860.0) == 1 and hl.kw_from_kcal(861.0) == 2,
      "kW rounds UP from Kcal, as every sheet does")
# DQ-8, resolved by reading the actual cell (2026-09-01): the whole 188,786 vs
# 191,399 gap is a BRACKET in the client's D18, which adds two wall AREAS in m2
# to a mass in kg. We reproduce their cell exactly, and use the sound reading.
check(hl.sheet_oven_steel_mass_kg(4.3, 2.75, 3.0, 1.2) == 377,
      "the client's own D18 cell is reproduced exactly (377 kg), bracket bug included")
_their = hl.dry_off_oven_heat_load(4.3, 2.75, 3.0, 30, 120, 1.2, job_mass_kg=1500,
                                   jobs_per_hour=6, air_density_kg_m3=101.325)
check(_their.kcal - 188786 == 3877,
      f"our total differs from the sheet's 188,786 by exactly the steel-mass bracket "
      f"({_their.kcal - 188786} Kcal = (733-377) kg x 0.11 x 90 +10%)")
check(hl.oven_shell_steel_mass_kg(4.3, 2.75, 3.0, 1.2) == 733,
      "oven shell mass follows the sheets' own ((LH)2 + (WH)2 + (LW)3) x 7.85 x thk expression")

dry = hl.dry_off_oven_heat_load(4.3, 2.75, 3.0, 30, 120, 1.2,
                                job_mass_kg=1500, jobs_per_hour=6)
check("air" not in dry.components,
      "dry-off oven omits the air term while its air density is under query (DQ-1)")
check(any("DQ-1" in g for g in dry.gaps),
      "the dry-off oven result names the open question instead of guessing the density")
dry_air = hl.dry_off_oven_heat_load(4.3, 2.75, 3.0, 30, 120, 1.2,
                                    job_mass_kg=1500, jobs_per_hour=6,
                                    air_density_kg_m3=hl.AIR_DENSITY_KG_M3)
check(dry_air.kcal > dry.kcal and "air" in dry_air.components,
      "an explicitly supplied air density is honoured, and only then")
partial = hl.dry_off_oven_heat_load(4.3, 2.75, 3.0, 30, 120, 1.2)
check(any("job mass" in g for g in partial.gaps),
      "a dry-off oven with no stated job load says so rather than heating an empty oven silently")

cure = hl.curing_oven_heat_load(25, 2.1, 3.0, 30, 220, 1.2,
                                conveyor_mass_kg=2500, job_mass_kg=4000,
                                insulation_thickness_mm=100)  # the sheet's own inputs
check(cure.components["air"] == 8675.0,
      f"curing oven air anchor: 158 m3 (rounded up) x 1.204 -> 8,675 Kcal (got {cure.components['air']})")
check(cure.components.get("insulation_loss_kw") == 9,
      f"curing oven insulation loss at 100 mm / U=0.35 (got {cure.components.get('insulation_loss_kw')})")
check(hl.sheet_oven_steel_mass_kg(25, 2.1, 3.0, 1.2) == 1647,
      "the curing sheet's D17 carries the SAME bracket bug, reproduced exactly (1,647 kg)")
check(hl.insulation_loss_kw(25, 2.1, 3.0, 190, 75) is None,
      "no U-value is interpolated for a thickness the client has not given")
bare = hl.curing_oven_heat_load(25, 2.1, 3.0, 30, 220, 1.2)
check(len(bare.gaps) == 3 and bare.kcal < cure.kcal,
      "a curing oven with no conveyor, job mass or insulation reports all three as gaps")

# --- Scrubber / duct diameter (workbook: Vertical Scrubber - Diameter) ----
tower = sc.tower_diameter(6750)
check(round(tower.diameter_mm) == 1545,
      f"scrubber anchor: 6750 m3/h at 1.0 m/s = 1545 mm (got {tower.diameter_mm})")
duct = sc.duct_diameter(6750)
check(round(duct.diameter_mm) == 399,
      f"duct anchor: 6750 m3/h at 15 m/s = 399 mm (got {duct.diameter_mm})")
check(tower.standard_diameter_mm is None and "DQ-3" in tower.note,
      "the standard-size ladder is not invented; the result says the rounding rule is outstanding")
check(sc.tower_diameter(None).diameter_mm is None,
      "no airflow, no diameter")

# --- Stock section weights (workbook: Cyclone recovery & Cartridge filter) -
check(mat.stock_weight_kg("ms_channel_75x40_6000") == 44.0,
      "stock table: MS channel 75x40 is 44 kg per 6 m")
check(mat.stock_weight_kg("ms_plate_1250x2500x6") == 150.0,
      "stock table: MS 6 mm plate is 150 kg per sheet")
check(mat.section_weight_kg("ms_channel_75x40_6000", 40) == 308.0,
      "structure anchor: 40 m of channel = 7 standard lengths = 308 kg")
check(mat.stock_lengths_required(36) == 6 and mat.stock_lengths_required(37) == 7,
      "lengths are bought whole, rounded up")
check(mat.stock_weight_kg("ms_square_tube_40x40x2_6000") == 18.0
      and mat.stock_weight_kg("ms_square_tube_40x40x3_6000") == 21.0,
      "DQ-4: the square-tube 'conflict' was two thicknesses, and both are now on the table")
check(mat.stock_weight_kg("ms_flat_40x6_6000") is None,
      "the one section the client's workbooks really disagree about returns None, never a picked side")
check(set(mat.STOCK_WEIGHT_DISPUTED) == {"ms_flat_40x6_6000"},
      "the remaining disputed section stays visible in code as an open question")

# --- Vitech's standard product range (the AI database PDF) -----------------
# Every figure here is QUOTED from their catalogue, never computed, which is
# what lets the platform answer a standard enquiry without first settling DQ-10.
check(len(bcat.CATALOGUE) == 31, f"the published range loads ({len(bcat.CATALOGUE)} models)")
_m = bcat.select(3000, bcat.DRY_2ROW, bcat.FRONT_OPEN)
check(_m is not None and _m.model == "VT/3.0/DTPB/OP" and _m.airflow_cmh == 8100
      and _m.motor_hp == 5,
      "a 3.0 m dry front-open booth resolves to VT/3.0/DTPB/OP, 8100 CMH, 5 HP")
check(bcat.select(3200, bcat.DRY_2ROW, bcat.FRONT_OPEN) is None,
      "a width 200 mm off the range is a SPECIAL, not the nearest catalogue machine")
check(bcat.select(3000, bcat.DRY_3ROW, bcat.FRONT_OPEN).airflow_cmh == 11340,
      "the 3-row variant of the same width carries its own published airflow")
check(bcat.by_model("VT/7.5/DTPB/CL").motor_hp is None,
      "a model the catalogue leaves unrated reports no motor rather than a scaled guess")
check(all(m.height_mm == 2425 for m in bcat.CATALOGUE),
      "every published model is 2425 high, as the range specifies")
check(all(m.airflow_cfm > 0 and m.airflow_cmh > m.airflow_cfm for m in bcat.CATALOGUE),
      "every model carries both airflow units, and CMH exceeds CFM")
_d = bcat.describe(_m)
check(len(_d["rows"]) == 5 and all(len(r) == 3 for r in _d["rows"]),
      "a model describes itself as attributed spec rows")
check(_d["standard"] == std.CLIENT_BOOTH_CATALOGUE,
      "catalogue rows cite the catalogue, never a calculation")

# --- A booth IS a standard model only on EVERY stated dimension ------------
# Matching on width alone is not a near-miss, it is a different machine: a
# 5.0 x 3.0 x 4.0 m booth shares its 3.0 m width with VT/3.0/DTPB/OP, which is
# published 1.5 m deep and 2.425 m high. Calling that standard would ship a
# booth 1.6 m too short.
check(bcat.match_requirement(3000, 1500, 2425, bcat.DRY_2ROW).model == "VT/3.0/DTPB/OP",
      "a booth matching every published dimension resolves to its standard model")
check(bcat.match_requirement(3000, 2250, 2425, bcat.DRY_2ROW).config == bcat.ENCLOSED,
      "the configuration follows from the depth, it is never guessed")
check(bcat.match_requirement(3000, 5000, 4000, bcat.DRY_2ROW) is None,
      "a booth sharing only its WIDTH with a published model is not that model")
check(bcat.match_requirement(3200, 1500, 2425, bcat.DRY_2ROW) is None,
      "a width 200 mm off the range stays a special under full-envelope matching")
check(bcat.family_for("powder") is None,
      "a powder booth has no standard model — the published range is liquid booths")

# The spec REPORTS the published machine; it never substitutes it. Vitech's
# published airflow and their own calculation sheet disagree (DQ-10), so both
# figures reach the engineer with the gap named.
_std_spec = compute_spec(1.5, 3.0, 2.425, "liquid")
_std_labels = {v.label: v.value for v in _std_spec.values}
check(_std_labels.get("Standard model") == "VT/3.0/DTPB/OP",
      "a standard booth names its published model")
check("Exhaust airflow" in _std_labels and _std_labels["Exhaust airflow"] != "8100 m3/h",
      "the engineered airflow is still computed, not replaced by the catalogue")
_pub_rule = next((r for r in _std_spec.rules if r.name == "Standard model"), None)
check(_pub_rule is not None and "8100 m3/h (4765 cfm)" in _pub_rule.formula,
      "the published duty is QUOTED from the catalogue in the basis trail")
check(_pub_rule is not None and "CONFIRM WHICH BASIS GOVERNS" in _pub_rule.formula,
      "where published and engineered airflow disagree, the gap is REPORTED not resolved")
check(_pub_rule is not None and _pub_rule.standard == std.CLIENT_BOOTH_CATALOGUE,
      "the catalogue row cites the catalogue, never a calculation")

# The published figures stay OUT of the value list on purpose. Emitted as
# values they were picked up as bill-of-materials lines, and a BOM listing both
# a 10 HP engineered motor and a 5 HP published one contradicts itself.
check(sum(1 for v in _std_spec.values if v.origin == "standard"
          and v.label == "Standard model") == 1,
      "a standard booth adds exactly ONE row, an identification not a component")
check(not any(v.label.startswith("Published") for v in _std_spec.values),
      "the published duty and motor never become component rows")

_special = compute_spec(5, 3, 4, "liquid")
check(not any(v.label.startswith(("Standard model", "Published"))
              for v in _special.values),
      "a special booth carries no catalogue rows at all")

print()
if FAILS:
    print(f"{len(FAILS)} ENGINEERING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL ENGINEERING TESTS PASS")
