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
from app.spec_template import TBD_VALUE, apply_template
from app.validate import (cross_validate, demote_unscalable, fits_size,
                          is_size_dependent)

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


# --- Field-level retrieval: TBD is the LAST resort -------------------------
# The nearest offer decides most of a spec, but it is one document. A field it
# happens to leave blank may be answered by the next-closest design, and before
# this the template stopped at the first miss and printed TBD (review defect #6).
PROFILE = {
    "spec_template": [{"label": "Dry scrubber", "kind": "standard"},
                      {"label": "Blower MOC", "kind": "standard"},
                      {"label": "Material handling", "kind": "customer_decision"}],
    "field_labels": {"dry_scrubber": "Dry scrubber", "blower_moc": "Blower MOC"},
    "scale_driver": None,
}
NEAR = {"id": "OFF-NEAR", "record": {"given_data": {"length_m": 3, "width_m": 3},
                                     "technical_details": {"dry_scrubber": None}}}
FAR_MATCH = {"id": "OFF-FAR", "record": {"given_data": {"length_m": 3, "width_m": 3},
                                         "technical_details": {"dry_scrubber": "activated carbon 3 nos",
                                                               "blower_moc": "MS"}}}

rows = apply_template(PROFILE, [], [NEAR, FAR_MATCH], {"length_m": 3, "width_m": 3})
by = {r["label"]: r for r in rows}
check(by["Dry scrubber"]["origin"] == "reused"
      and by["Dry scrubber"]["source"] == "OFF-FAR",
      f"a field the nearest design left blank is found in a comparable one "
      f"({by['Dry scrubber']['origin']})")
check("Field-level match" in by["Dry scrubber"]["reason"],
      "the borrowed field says it came from a field-level match, not the main design")
check(by["Material handling"]["origin"] == "customer_decision",
      "a customer decision is never looked up - it is theirs to make, not ours to find")

# Retrieval must not reintroduce the mismatch demote_unscalable exists to remove.
rows = apply_template(PROFILE, [], [NEAR, FAR_MATCH], {"length_m": 10, "width_m": 10})
by = {r["label"]: r for r in rows}
check(by["Dry scrubber"]["origin"] == "tbd",
      "a size-dependent field is NOT borrowed across a large size gap")
check(by["Blower MOC"]["origin"] == "reused",
      "a material is still borrowed across a size gap - it does not scale")

check(all(r["origin"] in ("tbd", "customer_decision")
          for r in apply_template(PROFILE, [], [], {})),
      "with no offers to search, every unresolved field is still an honest TBD")

check(fits_size({}, {}, PROFILE) is True,
      "an unmeasurable offer is not rejected outright - that would disable retrieval")


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

# --- VOC/LEL safety reaches the release verdict ----------------------------
# `voc_service` could answer this since the workbooks landed and nothing asked
# it, so an over-limit extraction could reach Customer Ready with nothing on the
# document to show it had never been checked.
_SOLVENT_ROWS = [{"label": "Paint process", "value": "liquid", "origin": "rule"},
                 {"label": "Exhaust airflow", "value": "10000 m3/h", "origin": "rule"}]
_SAFE = {"paint_consumption_l_hr": 10, "voc_percent": 60, "density_kg_l": 1.2}
_UNSAFE = dict(_SAFE, paint_consumption_l_hr=100)


def _gate(rows, params):
    return assess({"technical_details": rows, "validation": [], "parameters": params})


# The client's own worked example: 10 l/hr x 1.2 kg/l x 60% into 10,000 m3/h.
_pass = _gate(_SOLVENT_ROWS, _SAFE)
check(_pass["safety"]["verdict"] == "pass",
      "the client's worked VOC example passes its own limit")
check(_pass["safety"]["concentration_mg_m3"] == 720,
      f"and reproduces their 720 mg/m3 exactly (got {_pass['safety'].get('concentration_mg_m3')})")
check(_pass["status"] == STATUS_CUSTOMER_READY,
      "a passing safety check does not hold the document back")

_fail = _gate(_SOLVENT_ROWS, _UNSAFE)
check(_fail["status"] == STATUS_ENGINEERING_DRAFT,
      "an OVER-LIMIT solvent load blocks release, whatever the confidence")
check(any("VOC safety" in b for b in _fail["blockers"]),
      "and it is a BLOCKER, not a gap — customer sign-off cannot make it safe")
check("72000" in _fail["safety"]["blocker"],
      "the blocker says what airflow would fix it, not only that it failed")

# An unanswered safety question is reported as unanswered, never as a pass.
_unknown = _gate(_SOLVENT_ROWS, {})
check(_unknown["safety"]["verdict"] is None,
      "missing inputs yield NO verdict rather than a pass")
check(any("VOC safety not verified" in q for q in _unknown["questions"]),
      "an unverified solvent booth says so on the document")

# A powder booth has no solvent to evaporate. A safety warning an engineer knows
# is inapplicable is worse than no warning at all.
_powder = _gate([{"label": "Paint process", "value": "powder", "origin": "rule"},
                 _SOLVENT_ROWS[1]], {})
check("safety" not in _powder and not _powder["questions"],
      "a powder booth is not given a solvent safety check")

print()
if FAILS:
    print(f"{len(FAILS)} REVIEW TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL REVIEW TESTS PASS")
