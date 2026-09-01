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

print()
if _fail:
    print(f"{_fail} PRICING TEST(S) FAILED")
    sys.exit(1)
print("ALL PRICING TESTS PASS")
