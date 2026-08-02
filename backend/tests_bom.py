"""Guards for the bill of materials (`app/bom.py`).

The BOM's whole value is that it is honest about money. Quantities and weights
are engineering and are computed wherever the spec supports them; a line is
priced ONLY where the client's own rate card reaches it, and the total says so.

The client's supplied cost sheet has its first row cut off (visible lines sum to
Rs 5,68,534 against a stated Rs 6,49,264), so no total built here can be
validated against theirs. These tests pin the restraint that follows from that:
nothing is extrapolated, nothing is dropped, and the gaps are named.

Run after any change to `bom.py` or `engineering/rate_card.py`.
"""
import sys

from app.bom import build_bom
from app.engineering import rate_card

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


BOOTH = {
    "category": "paint_booth", "category_label": "Paint Booth",
    "geometry": {"envelope_mm": {"length": 5000, "width": 3000, "height": 4000}},
    "technical_details": [
        {"label": "Construction", "value": "panels MS 1.6mm / supports MS tubes"},
        {"label": "Enclosure sheet weight", "value": "1240 kg"},
        {"label": "Exhaust blower", "value": "CLP-4-15-14500"},
        {"label": "Exhaust blower (nos)", "value": "1"},
        {"label": "Exhaust blower motor (HP)", "value": "15"},
        {"label": "Paint arresting filter", "value": "16 nos 600 x 600 x 50 mm"},
        {"label": "Air intake filter", "value": "10 micron velcro type"},
        {"label": "Exhaust ducts", "value": "700 mm dia, GI, 14.0 m/s"},
        {"label": "Illumination", "value": "3 nos 40 W weatherproof LED (750 lux)"},
        {"label": "Control panel", "value": "Star Delta MCC, 13.0 kW"},
        {"label": "Dry scrubber", "value": "To be determined", "origin": "tbd"},
    ],
}

b = build_bom(BOOTH)
by = {l["item"]: l for l in b["lines"]}

# --- Quantities and weights come from the engineering ----------------------
check(b["ok"] and len(b["lines"]) >= 8, f"a booth yields a real BOM ({len(b['lines'])} lines)")
check(by["MS sheet panels"]["qty"] == 1240 and by["MS sheet panels"]["weight_kg"] == 1240,
      "the fabricated weight is the engine's own sheet weight, not an estimate")
check(by["Blower motor"]["qty"] == 15, "the motor line carries the selected HP")
check(by["Paint arresting filter"]["qty"] == 16,
      "the filter count is the engineered count, not a guess")
check(by["Light fitting"]["qty"] == 3, "the luminaire count is the engineered count")

# --- Costing: only where the client's own rate card reaches -----------------
mat, lab = rate_card.steel_cost(1240, "sheet")
check(by["MS sheet panels"]["amount"] == round(mat + lab),
      "sheet steel is priced at the client's material + fabrication rates")
check(by["Blower motor"]["amount"] == round(rate_card.motor_cost(15)),
      f"the motor is priced at Rs {rate_card.MOTOR_RATE_PER_HP:g}/HP")
check(by["Light fitting"]["amount"] == round(rate_card.bought_out_cost("led_light", 3)),
      "luminaires are priced from the named bought-out list")
check(by["Painting"]["amount"] and by["Painting"]["unit"] == "sq.ft",
      "painting is priced per sq.ft on the five-side area, floor excluded")

# The client priced ONE blower model. Extrapolating a price for a different
# frame would be inventing money, which is the one thing a BOM must not do.
check(rate_card.blower_cost("CLP-4-15-14500") is None
      and by["Exhaust blower"]["amount"] is None,
      "an unpriced blower model is listed WITHOUT a price, never extrapolated")
check("not on the client's priced list" in by["Exhaust blower"]["basis"],
      "the blower line says why it has no price")

# Scope must never be hidden just because it cannot be priced.
check(by["MS structure / supports"]["amount"] is None
      and by["MS structure / supports"] in b["lines"],
      "structure is LISTED even though no rule computes its weight")
check(by["Exhaust duct"]["amount"] is None and "RUN LENGTH" in by["Exhaust duct"]["basis"],
      "duct is listed with the reason its area cannot be taken off")
check(by["Control panel"]["amount"] is None,
      "a 13 kW panel is not priced from the rate card's 10 HP booth panel")

# --- The total is explicitly partial ---------------------------------------
t = b["totals"]
check(t["partial"] and t["uncosted_lines"] >= 4,
      f"the total declares itself partial ({t['uncosted_lines']} unpriced lines)")
check(t["costed_amount"] == sum(l["amount"] for l in b["lines"] if l["amount"] is not None),
      "the total is exactly the sum of the priced lines - nothing implied")
check(len(b["uncosted"]) == t["uncosted_lines"]
      and all(u["reason"] for u in b["uncosted"]),
      "every unpriced line explains what is missing")
check("not a quotation" in b["bom_markdown"].lower(),
      "the printed BOM never presents itself as a quotation")
check("Partial costing" in b["bom_markdown"],
      "the partial-costing caveat is stated at the top, not buried at the bottom")

# --- A TBD field contributes nothing ---------------------------------------
check(not any("dry scrubber" in l["item"].lower() for l in b["lines"]),
      "an undetermined field produces no BOM line")

# --- Determinism and empties -----------------------------------------------
check(build_bom(BOOTH)["bom_markdown"] == b["bom_markdown"], "the BOM is deterministic")
empty = build_bom({"category": "x", "technical_details": []})
check(empty["totals"]["costed_amount"] == 0 and empty["lines"] and
      all(l["amount"] is None for l in empty["lines"]),
      "a spec with no engineering yields no priced lines")

print()
if FAILS:
    print(f"{len(FAILS)} BOM TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL BOM TESTS PASS")
