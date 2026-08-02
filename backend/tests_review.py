"""Guards for the engineering review layer: cross-validation and the release gate.

Confidence says how well-founded the numbers are. THIS layer says whether the
document may leave the building. The two are different judgements and the tests
below pin that difference, plus the two failure modes that made the check
untrustworthy while it was being built:

  * comparing a requirement in CFM against an offer in m3/h as if they were the
    same unit (reported a 103% size gap where the true gap was 20%);
  * calling a MATERIAL size-dependent because its label happened to name a
    component ("Blower MOC = MS").

Run after any change to `validate.py`, `release_gate.py` or `analysis.py`.
"""
import sys

from app.engineering.design_standards import (HISTORICAL_TOLERANCE,
                                              STATUS_CUSTOMER_READY,
                                              STATUS_CUSTOMER_REVIEW,
                                              STATUS_ENGINEERING_DRAFT,
                                              check_historical)
from app.release_gate import assess
from app.spec_template import TBD_VALUE
from app.validate import (cross_validate, demote_unscalable, is_size_dependent)

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# --- Is a reused value size-dependent? -------------------------------------
# Naming a component is not enough: a material or a grade travels between
# machine sizes perfectly well, and a warning an engineer knows is wrong is
# worse than no warning at all.
SIZED = [
    ("Illumination", "20w x 10 nos LED"),
    ("Blower motor hp", "15"),
    ("Scrubber chamber", "1000 mm dia x 3000 H"),
    ("Paint arresting filter", "16 nos 600 x 600 x 50 mm"),
    ("Exhaust airflow", "19440 m3/h"),
]
NOT_SIZED = [
    ("Blower MOC", "MS"),
    ("Spray nozzle material", "SS316"),
    ("Air intake filter", "10 micron velcro type"),
    ("Blower drive", "belt"),
    ("Finish", "primer + final coats"),
    ("Construction", "base frame ISMC / panels MS 1.2mm"),
]
for label, value in SIZED:
    check(is_size_dependent(label, value), f"'{label}' is size-dependent")
for label, value in NOT_SIZED:
    check(not is_size_dependent(label, value),
          f"'{label}' = '{value[:22]}' is a descriptor, not a size")

# --- The client's +/-20% tolerance -----------------------------------------
check(check_historical(125, 100) is not None and check_historical(75, 100) is not None,
      "a reused value beyond +/-20% of the computed one is flagged, either way")
check(check_historical(115, 100) is None and check_historical(120, 100) is None,
      "the tolerance band is inclusive - exactly 20% is still acceptable")
check(HISTORICAL_TOLERANCE == 0.20, "the tolerance is the client's 20%")

# --- Cross-validation runs for EVERY category, and compares like with like --
PROFILE_CFM = {"scale_driver": "air_volume_cfm"}
ROWS = [{"label": "Illumination", "value": "20w x 10 nos", "origin": "reused"},
        {"label": "Blower MOC", "value": "MS", "origin": "reused"}]

# The regression: the requirement carries CFM, the offer records only m3/h.
# Treating those as the same unit made 6100 vs 3000 look like a 103% gap.
offer_cmh_only = {"id": "OFF-X", "record": {"given_data": {"air_volume_cmh": 6100},
                                            "technical_details": {}}}
checks = cross_validate("wet_scrubber", {"air_volume_cfm": 3000, "air_volume_cmh": 5097},
                        offer_cmh_only, ROWS, PROFILE_CFM)
msgs = " ".join(c["message"] for c in checks)
check("103%" not in msgs, f"mismatched units are never compared as if equal ({msgs[:70]})")
check(all(c["level"] != "warn" for c in checks),
      "a 6100 vs 5097 m3/h gap is inside tolerance, so it informs rather than warns")

# A genuine, like-for-like size gap DOES warn, and names only the sized values.
offer_small = {"id": "OFF-SMALL", "record": {"given_data": {"air_volume_cfm": 800},
                                             "technical_details": {}}}
checks = cross_validate("wet_scrubber", {"air_volume_cfm": 3000}, offer_small,
                        ROWS, PROFILE_CFM)
warns = [c for c in checks if c["level"] == "warn"]
check(len(warns) == 1, f"a real size gap warns ({len(warns)} warning(s))")
check("Illumination" in warns[0]["message"] and "Blower MOC" not in warns[0]["message"],
      "the warning names the size-dependent value and not the material")

# Booths are compared on floor area, and the check is no longer scrubber-only.
booth = {"id": "OFF-BOOTH", "record": {"given_data": {"length_m": 7.5, "width_m": 4.0},
                                       "technical_details": {}}}
checks = cross_validate("paint_booth", {"length_m": 10, "width_m": 10}, booth,
                        ROWS, {"scale_driver": None})
check(checks and "floor area" in checks[0]["message"],
      "a paint booth is size-compared on floor area, not skipped")

check(cross_validate("paint_booth", {}, None, ROWS, {}) == [],
      "with no comparable offer there is nothing to cross-validate")

# --- Scale-or-refuse: a big size gap DEMOTES rather than asserts -----------
# Warning was not enough. The spec still printed "20 W x 10 LED" as the lighting
# for a booth seven times the size of the one it came from, and a reader takes a
# stated value as engineered.
DEMOTE_ROWS = [
    {"label": "Illumination", "value": "20w x 10 nos", "origin": "reused", "origin_label": "Reused"},
    {"label": "Blower MOC", "value": "MS", "origin": "reused", "origin_label": "Reused"},
    {"label": "Exhaust airflow", "value": "19440 m3/h", "origin": "rule"},
]
small_booth = {"id": "OFF-SMALL", "record": {"given_data": {"length_m": 7.5, "width_m": 4.0}}}

out = demote_unscalable(DEMOTE_ROWS, {"length_m": 10, "width_m": 10}, small_booth,
                        {"scale_driver": None})
by = {r["label"]: r for r in out}
check(by["Illumination"]["origin"] == "tbd" and by["Illumination"]["value"] == TBD_VALUE,
      "a size-dependent value from a far-off design is demoted, not asserted")
check("engineered for" in by["Illumination"].get("reason", "")
      and "OFF-SMALL" in by["Illumination"]["reason"],
      "the demoted row explains what to re-size and which design it came from")
check(by["Blower MOC"]["origin"] == "reused" and by["Blower MOC"]["value"] == "MS",
      "a material is left alone - it travels between sizes")
check(by["Exhaust airflow"]["origin"] == "rule",
      "a CALCULATED value is never demoted; it was computed for this duty")

check(demote_unscalable(DEMOTE_ROWS, {"length_m": 8, "width_m": 4}, small_booth,
                        {"scale_driver": None}) == DEMOTE_ROWS,
      "inside the tolerance band nothing is demoted")
check(demote_unscalable(DEMOTE_ROWS, {"length_m": 10, "width_m": 10}, None, {}) == DEMOTE_ROWS,
      "with no source offer there is nothing to demote against")


# --- The release gate ------------------------------------------------------
OK_ROWS = [{"label": "Exhaust airflow", "value": "19440 m3/h", "origin": "rule"},
           {"label": "Construction", "value": "MS", "origin": "reused"}]

r = assess({"technical_details": OK_ROWS, "validation": []})
check(r["status"] == STATUS_CUSTOMER_READY,
      f"a consistent, complete spec reaches Customer Ready ({r['status']})")

r = assess({"technical_details": OK_ROWS + [{"label": "Dry scrubber",
                                             "value": "To be determined", "origin": "tbd"}],
            "validation": []})
check(r["status"] == STATUS_CUSTOMER_REVIEW and r["gaps"] == ["Dry scrubber"],
      f"an open engineering TBD holds it at Customer Review ({r['status']})")

r = assess({"technical_details": OK_ROWS,
            "validation": [{"level": "warn", "message": "velocity out of range"}]})
check(r["status"] == STATUS_ENGINEERING_DRAFT and r["blockers"],
      f"a warning keeps it an internal Engineering Draft ({r['status']})")

# A customer's decision is a QUESTION, not our engineering gap -- it must not
# hold the document back the way an unresolved calculation does.
r = assess({"technical_details": OK_ROWS + [{"label": "Material handling",
                                             "value": "To be confirmed",
                                             "origin": "customer_decision"}],
            "validation": []})
check(r["status"] == STATUS_CUSTOMER_READY and r["questions"] == ["Material handling"],
      f"a customer decision is a question, not a gap ({r['status']})")

r = assess({"technical_details": [{"label": "Mystery", "value": "42", "origin": None}],
            "validation": []})
check(r["status"] == STATUS_ENGINEERING_DRAFT and "no source" in " ".join(r["blockers"]),
      "a value with no provenance blocks release")

check(assess({"technical_details": [], "validation": []})["status"] == STATUS_ENGINEERING_DRAFT,
      "an empty spec is never 'customer ready' just because nothing failed")

# Released Design is a signature, not a computation.
statuses = {assess({"technical_details": rows, "validation": v})["status"]
            for rows, v in ((OK_ROWS, []), (OK_ROWS, [{"level": "warn", "message": "x"}]),
                            ([], []))}
check("Released Design" not in statuses,
      "the engine can never award itself Released Design")

print()
if FAILS:
    print(f"{len(FAILS)} REVIEW TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL REVIEW TESTS PASS")
