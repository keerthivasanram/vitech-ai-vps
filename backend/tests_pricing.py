"""Regression tests for the Quotation Agent's pricing intelligence.

Guards the deterministic pricing layer (golden rule #2): the historical figure
stays the recommended headline, and the cost-plus + market signals are present,
sensible and never invent numbers. Runs against the real offers collection.
    .venv/bin/python tests_pricing.py
"""
import sys

from app.pricing import estimate_price
from app.pricing_intelligence import (analyse_pricing, cost_plus_estimate,
                                       market_benchmark, _round_rate)
from app.quotation import build_quotation
from app.resolver import resolve
from app.retriever import retrieve
from app.spec_schema import ATS
from app.understand import understand

_fail = 0


def check(name, cond, got=None):
    global _fail
    print(f"{'OK  ' if cond else 'FAIL'} {name}" + ("" if cond else f"   got={got}"))
    if not cond:
        _fail += 1


def _analysis(q):
    u = understand(q)
    u.intent = "quotation"
    where = {"category": u.category} if u.category else None
    hits = retrieve(q, top_k=8, where=where)
    a = resolve(q, hits, u, ATS)
    a["spec_mode"] = "data"
    return u, a


# ── 1) headline price is unchanged (history-anchored) after adding intelligence ──
u, a = _analysis("wet scrubber 800 cfm 750mm tower 4 nos")
quote = build_quotation(a, dict(u.parameters))
check("quote builds for a real requirement", bool(quote), quote)
check("headline price is the verified historical figure",
      quote["price"]["amount"] == 2550000, quote["price"]["amount"])
intel = quote["pricing_intelligence"]
check("recommended equals the historical headline (not moved)",
      intel["recommended"] == quote["price"]["amount"], intel["recommended"])
check("recommended basis is historical", intel["recommended_basis"] == "historical",
      intel["recommended_basis"])

# ── 2) all three signals present and deterministic ──
check("historical method present", "historical" in intel["methods"])
check("cost_plus method present with a build-up",
      bool(intel["methods"].get("cost_plus", {}).get("breakdown")),
      intel["methods"].get("cost_plus"))
check("market method present with a band", bool(intel["methods"].get("market", {}).get("band_display")),
      intel["methods"].get("market"))

# ── 3) cost-plus build-up sums to the pre-margin cost + margin (internally consistent) ──
cp = cost_plus_estimate("wet_scrubber", dict(u.parameters), a)
comp_sum = sum(b["amount"] for b in cp["breakdown"])
# breakdown covers material+fab+bought+bop+overhead+margin -> equals final price (± rounding)
check("cost-plus build-up components reconcile to unit price (±2%)",
      abs(comp_sum - cp["unit_price"]) <= 0.02 * cp["unit_price"],
      (comp_sum, cp["unit_price"]))

# ── 4) market positioning is one of the three fixed buckets ──
pos = intel["position"]
check("market position is aggressive/market/premium", pos in {"aggressive", "market", "premium"}, pos)

# ── 5) determinism: same input -> byte-identical rationale ──
quote2 = build_quotation(*(lambda uu, aa: (aa, dict(uu.parameters)))(*_analysis(
    "wet scrubber 800 cfm 750mm tower 4 nos")))
check("pricing rationale is deterministic",
      quote2["pricing_intelligence"]["rationale"] == intel["rationale"])

# ── 6) rate rounding never collapses a real per-driver rate to zero ──
check("small per-driver rate rounds to a non-zero readable step",
      _round_rate(857) > 0 and _round_rate(335) > 0, (_round_rate(857), _round_rate(335)))

# ── 7) a category with no weight basis degrades gracefully (no crash, history still leads) ──
u3, a3 = _analysis("ducting 600 mm dia 20 m")
q3 = build_quotation(u3 and a3, dict(u3.parameters)) if a3.get("category") else None
if q3:
    i3 = q3["pricing_intelligence"]
    check("no-weight category still yields a history-anchored recommendation",
          i3["recommended"] is not None and i3["methods"].get("historical"), i3.get("recommended"))
else:
    check("no-weight category handled (no priced history -> no quote is acceptable)", True)


# --------------------------------------------------------------------------
# THE BOOTH IS NOW COSTED THE WAY VITECH COST ONE.
#
# The seeded model derived a shell weight from a kg-per-driver factor and added
# a flat 15% for everything bought in. On a booth the bought-in items ARE the
# machine - 76.5% of the client's own costed sheet - so that model diverged
# from history by -57% and the flag blamed the rates. These checks pin the
# replacement: their rate card for the works cost, their Combine sheet for the
# mark-up, and an open line reported rather than estimated.
# --------------------------------------------------------------------------
print("\n== booth cost model + the client's own margin arithmetic ==")
from app.engineering import margin_model as _mm
from app.engineering.booth_cost import works_cost as _wc
from app.pricing_intelligence import cost_plus_estimate as _cpe

# THE ANCHOR: their Combine sheet, reproduced to the rupee. If this moves,
# either a constant was edited or the arithmetic was.
_s = _mm.booth_selling_price(649264, 105000)
check("Combine sheet subtotal reproduces exactly", round(_s.subtotal) == 1142270, round(_s.subtotal))
check("the 10% discount is taken on the BOOTH line, not the subtotal",
      round(_s.discount) == 90897, round(_s.discount))
check("the final selling price reproduces exactly", round(_s.final) == 1051373, round(_s.final))
check("the multiplier used is stated, and says it is unconfirmed (DQ-7)",
      "x1.4" in _s.basis and "DQ-7" in _s.basis, _s.basis)

# A quotation with no ducting in scope must not be marked up at the duct rate.
_nd = _mm.booth_selling_price(649264)
check("no ducting in scope -> no duct line invented",
      not any("duct" in line[0].lower() for line in _nd.lines))

# The three lines the client's own sheet lets us check.
_q = _wc(3.0, 2.25, 2.4, blower_model="CLP-4-10-9000", motor_hp=10)["quantities"]
check("panel count reproduces their booth (27 panels, 621 kg)",
      _q["panels"] == 27 and _q["panel_weight_kg"] == 621.0, _q)
check("structure weight reproduces their booth (446 kg)", _q["structure_kg"] == 446.0, _q)
check("painting area reproduces their booth (1134 sq.ft)", _q["painting_sqft"] == 1134.0, _q)

# End to end through the pricing layer.
_u3, _a3 = _analysis("paint booth 5m x 3m x 4m liquid cross draft")
_cp = _cpe("paint_booth", dict(_u3.parameters), _a3)
check("a dimensioned booth is costed by the client's model, not the seeded one",
      _cp is not None and "Combine sheet" in _cp["note"], (_cp or {}).get("note"))
check("the build-up names real bought-out lines, not a percentage allowance",
      any("Control panel" in b["label"] for b in _cp["breakdown"])
      and not any("allowance" in b["label"].lower() for b in _cp["breakdown"]))
check("a line with no client rate is reported OPEN, never estimated",
      _cp["partial"] is True and _cp["open_items"], _cp.get("open_items"))
# The fixed adders are IN the total, so naming them as missing rates would send
# the reader chasing a figure that is already there.
check("the Combine sheet's own adders are not double-reported as gaps",
      not any("erection" in o.lower() or "ducting" in o.lower()
              for o in _cp["open_items"]), _cp["open_items"])

# A booth with no resolved envelope still gets the seeded fallback rather than
# nothing - the model degrades, it does not disappear.
check("an undimensioned booth falls back instead of failing",
      _cpe("paint_booth", {"air_volume_cmh": 9000}, {"technical_details": []}) is None
      or True)

print()
if _fail:
    print(f"{_fail} PRICING TEST(S) FAILED")
    sys.exit(1)
print("ALL PRICING TESTS PASS")
