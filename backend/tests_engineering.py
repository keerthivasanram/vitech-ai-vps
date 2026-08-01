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
from app.engineering import standards_service as std
from app.engineering.blower_service import (PAINT_BOOTH_SERIES, by_model, chart,
                                            select_blower, select_booth_blower,
                                            select_booth_blower_set, select_in_series,
                                            series_of)
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
check(abs(cross.exhaust_cmh - (12 * 0.45 * 3600)) < 1e-6, "exhaust = area x velocity x 3600")

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

print()
if FAILS:
    print(f"{len(FAILS)} ENGINEERING TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL ENGINEERING TESTS PASS")
