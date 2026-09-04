"""Requirement STATE: what the customer confirmed, and what is genuinely open.

THE DEFECT THIS SUITE EXISTS FOR. A hot air oven was specified with its overall
size, panel thickness, door opening, operating and maximum temperature and
electric heating all stated in the requirement, and the specification came back
listing the overall dimensions and most of the rest under TO BE DETERMINED —
while the SAME three axes were printed as client-given data two tables above.
The reused values that did resolve were worse than the gaps: 200 mm of
insulation on an oven specified at 100, and a diesel burner on an oven specified
as electric, both correctly attributed to a 230 deg C conveyorised oven that is
not this machine.

Three independent causes, each guarded below:

  1. THE PARSER never read four of the six stated values. `maximum temperature`
     was aliased onto `operating_temp`, so the two collapsed into one number.
  2. THE TEMPLATE matched fields by LABEL alone, so "Overall dimensions (mm)" —
     which is composed of three requirement keys and named by none of them —
     could never resolve, whatever the customer stated.
  3. THE LADDER consulted the requirement only when NOTHING else resolved, so a
     value reused from the nearest design silently outranked the customer's own
     words.

Every parameter now lands in exactly one of four states: CONFIRMED, DERIVED,
TBD or INDICATIVE. That partition is asserted here, not assumed.
"""
import sys

from app.api.support import _spec_for_drawing
from app.catalog import ORIGIN_LABELS, ORIGIN_STATES, get_profile, state_for
from app.drawing.drawing_service import compose
from app.drawing.style import DASH_AIRFLOW
from app.spec_template import apply_template, state_summary
from app.understand import _labelled_inputs, understand
from app.validate import _agrees_mm, demote_contradicted

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# The requirement from the report, verbatim in substance.
REQ = ("hot air oven 4000 x 2500 x 2500 mm overall, insulated panel thickness 100 mm, "
       "double leaf door opening 2000 x 2200 mm, operating temperature 180 deg C, "
       "maximum temperature 200 deg C, electric heating")

# What the customer stated, and therefore what may NEVER be reported as missing.
MUST_BE_CONFIRMED = [
    "Overall dimensions (mm)",
    "Insulated panel thickness (mm)",
    "Door type",
    "Door opening (mm)",
    "Operating temperature",
    "Maximum temperature (deg C)",
    "Heating source",
]
# What no rule and no source data can answer yet, so it stays open.
MAY_BE_TBD = {
    "Airflow (m3/h)", "Circulation blower (HP)", "Circulation blower (nos)",
    "Heating capacity (kcal/hr)", "Control panel", "Utilities",
    "Safety features", "Chamber", "Insulation",
}

print("== 1. the parser reads every LABELLED value ==")
got = _labelled_inputs(REQ.lower())
for key, want in (("operating_temp", 180), ("max_temp_c", 200),
                  ("panel_thickness_mm", 100), ("door_opening_mm", "2000 x 2200"),
                  ("door_type", "double leaf"), ("heating_mode", "electric")):
    check(got.get(key) == want, f"reads {key} = {want!r} (got {got.get(key)!r})")
# The two temperatures are DIFFERENT engineering values. Folding one onto the
# other is what lost whichever the customer wrote second.
check(got["operating_temp"] != got["max_temp_c"],
      "operating and maximum temperature stay distinct")

print("\n== 2. it reads nothing it was not given ==")
# Anchored on the WORD, never on a bare number: re-reading an unqualified
# "200C" here would change what every existing oven requirement resolves to.
for quiet in ("paint booth 5 x 3 x 4 liquid",
              "wet scrubber for 800 cfm 750mm tower 4 nos",
              "hot air oven 200C 500kg batch",
              "dust collector 6000 cmh pulse jet"):
    check(_labelled_inputs(quiet) == {},
          f"no labelled input invented from {quiet!r}")

print("\n== 3. the deterministic read survives the model ==")
u = understand(REQ)
for key, want in (("operating_temp", 180), ("max_temp_c", 200),
                  ("panel_thickness_mm", 100), ("heating_mode", "electric")):
    check(u.parameters.get(key) == want,
          f"understand() keeps {key} = {want!r} (got {u.parameters.get(key)!r})")

print("\n== 4. the four states are a TOTAL partition ==")
# A state map that silently omitted an origin would put values in no bucket at
# all, which defeats the whole point of the partition.
missing = sorted(set(ORIGIN_LABELS) - set(ORIGIN_STATES))
check(not missing, f"every origin has a state (unmapped: {missing})")
check(set(ORIGIN_STATES.values()) <= {"confirmed", "derived", "tbd", "indicative"},
      "no state outside the declared four")
check(state_for("given") == "confirmed", "a client-stated value is CONFIRMED")
check(state_for("rule") == "derived", "a rule-computed value is DERIVED")
check(state_for("tbd") == "tbd" and state_for("customer_decision") == "tbd",
      "a gap and a customer decision are both open")
check(state_for("nonsense-origin") == "tbd",
      "an unknown provenance is reported open, never derived")

print("\n== 5. the oven resolves as specified ==")
spec = _spec_for_drawing(REQ)
rows = {r["label"]: r for r in spec["technical_details"]}
for label in MUST_BE_CONFIRMED:
    r = rows.get(label) or {}
    check(r.get("state") == "confirmed",
          f"{label} is CONFIRMED (state={r.get('state')!r}, value={r.get('value')!r})")
check(rows.get("Overall dimensions (mm)", {}).get("value") == "4000 x 2500 x 2500",
      "the composed envelope states the customer's own millimetres")
check(rows.get("Heating source", {}).get("value") == "electric",
      "the stated heating medium supersedes the reused one")

print("\n== 6. nothing confirmed leaks into the TBD schedule ==")
open_rows = {lbl for lbl, r in rows.items() if r.get("state") == "tbd"}
stray = sorted(open_rows - MAY_BE_TBD)
check(not stray, f"only genuinely open fields are TBD (stray: {stray})")

print("\n== 7. every row is in exactly one bucket ==")
summary = state_summary(spec["technical_details"])
total = sum(len(summary[k]) for k in ("confirmed", "derived", "tbd", "indicative"))
check(total == summary["total"] == len(spec["technical_details"]),
      f"the four buckets sum to the row count ({total} == {summary['total']})")
check(all(len(set(summary[k])) == len(summary[k])
          for k in ("confirmed", "derived", "tbd", "indicative")),
      "no label appears twice inside a bucket")

print("\n== 8. a stated value is never displaced by a reused one ==")
profile = get_profile("hot_air_oven")
reused = [{"label": "Heating source", "value": "diesel fired hot air generator",
           "origin": "reused", "origin_label": "Reused from nearest design",
           "source": "OFF-X", "reason": ""}]
out = {r["label"]: r for r in
       apply_template(profile, reused, [], {"heating_mode": "electric"})}
hs = out["Heating source"]
check(hs["origin"] == "given" and hs["value"] == "electric",
      "the requirement outranks the nearest design")
check(hs.get("superseded", {}).get("value") == "diesel fired hot air generator",
      "and the displaced value is recorded, not discarded")
# A calculation is NOT displaced: it follows FROM the requirement rather than
# standing in for it.
ruled = [{"label": "Heating source", "value": "computed", "origin": "rule",
          "origin_label": "Calculated", "source": "std", "reason": ""}]
out = {r["label"]: r for r in
       apply_template(profile, ruled, [], {"heating_mode": "electric"})}
check(out["Heating source"]["origin"] == "rule",
      "a rule-computed value is left alone")

print("\n== 9. a reused value the requirement CONTRADICTS is demoted ==")
ins = [{"label": "Insulation", "value": "175mm blanket 96 kg/m3 + 25mm ceramic wool",
        "origin": "reused", "origin_label": "Reused", "source": "OFF-X", "reason": ""}]
got = demote_contradicted(ins, {"panel_thickness_mm": 100}, profile)[0]
check(got["origin"] == "tbd", "200 mm of insulation on a 100 mm panel is refused")
check(got["contradicted"]["stated"] == 100 and "175mm" in got["contradicted"]["reused"],
      "and both figures are recorded so an engineer can reconcile them")
agree = [dict(ins[0], value="100mm rockwool panel")]
check(demote_contradicted(agree, {"panel_thickness_mm": 100}, profile)[0]["origin"] == "reused",
      "a reused value that AGREES is kept")
check(_agrees_mm(100, "50mm + 50mm sandwich"), "a build-up summing to the stated figure agrees")
check(_agrees_mm(100, "glass wool, density 96 kg/m3"),
      "text stating no thickness is not a contradiction")
check(not _agrees_mm(100, "175mm blanket"), "a different single figure is one")

print("\n== 10. the drawing draws ONE machine across three views ==")
canvas, pkg = compose(spec, sheet_size="A3")
per_mm = 1.0 / float(pkg["scale"].split(":")[1])
rects = [s for s in canvas.shapes if type(s).__name__ == "Rect"]


def near(a, b, tol=0.02):
    return abs(a - b) <= tol


def one(w, h):
    return [r for r in rects if near(r.w, w) and near(r.h, h)]


# The stated panel, converted through each view's own scale, is the same real
# thickness everywhere. Before this, the section drew it true-scale and the plan
# and side drew a symbolic 5% band — one sheet, one wall, three thicknesses.
t = 100 * per_mm
liners = 0
for o in rects:
    inner = [r for r in rects if r is not o and near(r.x - o.x, t) and near(r.y - o.y, t)
             and near(o.w - r.w, 2 * t) and near(o.h - r.h, 2 * t)]
    liners += len(inner)
check(liners >= 3, f"the 100 mm panel is drawn true-scale in all three views ({liners})")

check(len(one(2000 * per_mm, 2200 * per_mm)) >= 1,
      "SECTION A-A draws the door at its stated 2000 x 2200")
check(len(one(2000 * per_mm, t)) >= 1,
      "PLAN draws the same opening, 2000 wide through the panel")
check(len(one(t, 2200 * per_mm)) >= 1,
      "SIDE ELEVATION draws the same opening, 2200 high, edge-on")
# Third-angle correspondence: the plan sits above the section and the side beside
# it, so the one door must project to the same x in two views and the same y in
# the other two. This is the check that would catch a door drawn twice.
sec = one(2000 * per_mm, 2200 * per_mm)[0]
pln = one(2000 * per_mm, t)[0]
sde = one(t, 2200 * per_mm)[0]
check(near(sec.x, pln.x, 0.05), "the door projects to the same x in plan and section")
check(near(sec.y, sde.y, 0.05), "and to the same y in section and side elevation")

print("\n== 11. forced-air circulation reads on every view ==")
arrows = [s for s in canvas.shapes
          if type(s).__name__ == "Line" and getattr(s, "dash", None) == DASH_AIRFLOW]
bands = {"plan": 0, "section": 0, "side": 0}
for s in arrows:
    y, x = min(s.y1, s.y2), min(s.x1, s.x2)
    bands["plan" if y < 140 else ("side" if x >= 150 else "section")] += 1
for view, n in bands.items():
    check(n > 0, f"the recirculation circuit is shown on the {view} ({n} arrows)")

print("\n== 12. an oven stating none of this is unchanged ==")
# The fallback matters as much as the fix: a requirement that gives no thickness
# and no door must still draw, and must not gain a callout for a value nobody
# supplied.
plain = _spec_for_drawing("hot air oven 3m x 2m x 2m 200C")
prows = {r["label"]: r for r in plain["technical_details"]}
for label in ("Insulated panel thickness (mm)", "Door opening (mm)", "Door type"):
    check(prows.get(label, {}).get("state") == "tbd",
          f"{label} is honestly open when unstated")
pc, ppkg = compose(plain, sheet_size="A3")
texts = [getattr(s, "text", "") for s in pc.shapes if type(s).__name__ == "Text"]
check(not any("CLEAR OPENING" in t for t in texts),
      "no door callout is invented for an oven that stated none")
check(ppkg["state"] == "fully_dimensioned", "and the sheet still draws")

print("\n== 13. the STUDIO form carries the same values ==")
# The studio feeds structured inputs straight into the resolver rather than
# composing a sentence and re-parsing it, so it is a SECOND route to the same
# engine and it has to be checked separately. A door opening is two numbers in
# one field: typed from its `_mm` suffix alone it became a single-number input,
# and `coerce` then dropped "2000 x 2200" as unparseable — the studio silently
# losing a value the engineer had typed in.
from app.drawing.fields import coerce, describe, is_number  # noqa: E402
check(not is_number("door_opening_mm"), "a door opening is a PAIR, not a number field")
check(is_number("panel_thickness_mm") and is_number("max_temp_c"),
      "a thickness and a temperature still are numbers")
form = coerce({"length_m": "4", "width_m": "2.5", "height_m": "2.5",
               "operating_temp": "180", "max_temp_c": "200",
               "panel_thickness_mm": "100", "door_opening_mm": "2000 x 2200",
               "door_type": "double leaf", "heating_mode": "electric"})
check(form.get("door_opening_mm") == "2000 x 2200",
      "the form keeps the door opening intact")
check(form.get("panel_thickness_mm") == 100.0 and form.get("max_temp_c") == 200.0,
      "and coerces the single-number fields to numbers")
offered = {f["key"] for f in describe(get_profile("hot_air_oven"), "optional_inputs")}
check({"max_temp_c", "panel_thickness_mm", "door_opening_mm", "door_type",
       "heating_mode"} <= offered,
      "the studio form offers every input the parser can read")

if FAILS:
    print(f"\n{len(FAILS)} REQUIREMENT-STATE FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("\nALL REQUIREMENT-STATE TESTS PASS")
