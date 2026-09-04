"""The runaway guards on the expensive routes (`app/ratelimit.py`).

    .venv/bin/python tests_limits.py

OFFLINE and deterministic: it exercises the limiter directly rather than by
hammering the running server, because a suite that deliberately exhausts a
live rate limit would leave every other HTTP suite 429'd for the rest of the
minute.

WHAT IT IS REALLY GUARDING. The limiter exists for readiness findings S5 (an
unthrottled LLM route is an unbounded cost and DoS surface) and P2 (concurrent
slow requests exhaust the thread pool and take `/api/health` down with them).
The second one is the trap: the FIRST implementation of the concurrency slot
took no path argument, so it counted EVERY request — which would have put
`/api/health` behind the same ceiling as a package build and 429'd the monitor
under load, reintroducing the exact failure it was written to prevent. It was
caught by reading `in_flight` in the live metrics, not by reading the code.
The `cheap routes never consume a slot` checks below are that bug, pinned.
"""
import sys

from app import config, ratelimit

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


class P:
    """A stand-in principal — the limiter only reads kind and name."""

    def __init__(self, name, kind="user"):
        self.name, self.kind = name, kind


# --- which routes are expensive ----------------------------------------------
for path in ("/api/query", "/api/tools/spec", "/api/tools/quote", "/api/package",
             "/api/bom", "/api/siting/place", "/api/drawing/render",
             "/api/specification/pdf"):
    check(ratelimit.is_expensive(path), f"expensive: {path}")

# `/api/health` is the one that matters most: P2 is precisely that the probe
# stops answering when everything else is saturated.
for path in ("/api/health", "/api/auth/me", "/api/auth/login", "/api/offers",
             "/api/records", "/api/admin/metrics", "/api/jobs", "/api/knowledge/overview",
             "/api/drawing/catalog", "/api/uploads"):
    check(not ratelimit.is_expensive(path), f"NOT rate-limited: {path}")

# --- the rate limit fires, and only for the principal that tripped it --------
ratelimit.reset()
limit = config.RATE_LIMIT_PER_MINUTE
alice, bob = P("alice"), P("bob")

allowed = sum(1 for _ in range(limit) if ratelimit.check(alice, "/api/tools/spec")[0])
check(allowed == limit, f"a principal gets its full budget ({allowed}/{limit})")

ok, why, retry = ratelimit.check(alice, "/api/tools/spec")
check(not ok, "the request after the limit is refused")
check(retry > 0, f"a refusal carries a positive Retry-After ({retry}s)")
check(str(limit) in why, f"the audit reason names the limit ({why})")

check(ratelimit.check(bob, "/api/tools/spec")[0],
      "one principal's loop does NOT throttle another")

# A cheap route is never refused, even for a principal already over its budget.
check(ratelimit.check(alice, "/api/health")[0],
      "an over-budget principal can still reach /api/health")
check(ratelimit.check(alice, "/api/auth/me")[0],
      "an over-budget principal can still reach a cheap route")

# --- the concurrency ceiling -------------------------------------------------
ratelimit.reset()
held = []
for _ in range(config.MAX_CONCURRENT_EXPENSIVE):
    s = ratelimit.slot("/api/package")
    s.__enter__()
    held.append(s)
check(all(s.acquired for s in held),
      f"all {config.MAX_CONCURRENT_EXPENSIVE} expensive slots can be held at once")

overflow = ratelimit.slot("/api/package")
overflow.__enter__()
check(not overflow.acquired, "the request past the ceiling is refused a slot")
overflow.__exit__()

# THE REGRESSION THIS SUITE EXISTS FOR: at a saturated ceiling, a cheap route
# must still sail through. A monitor has to be able to tell "busy" from "dead".
cheap = ratelimit.slot("/api/health")
cheap.__enter__()
check(cheap.acquired, "a CHEAP route is served while the expensive ceiling is full")
cheap.__exit__()
check(ratelimit.stats()["in_flight"] == config.MAX_CONCURRENT_EXPENSIVE,
      "a cheap route did not consume a slot on the way through")

for s in held:
    s.__exit__()
check(ratelimit.stats()["in_flight"] == 0, "slots are released on exit")

# An exception inside the block must not leak a slot, or the ceiling ratchets
# down to zero over time and the platform refuses everything.
ratelimit.reset()
try:
    with ratelimit.slot("/api/package"):
        raise RuntimeError("boom")
except RuntimeError:
    pass
check(ratelimit.stats()["in_flight"] == 0, "a slot is released when the request raises")

# --- the switch, and the reporting ------------------------------------------
ratelimit.reset()
config.RATE_LIMIT_ENABLED = False
try:
    check(all(ratelimit.check(alice, "/api/tools/spec")[0] for _ in range(limit + 10)),
          "RATE_LIMIT_ENABLED=0 disables the limit entirely")
    with ratelimit.slot("/api/package") as s:
        check(s.acquired, "RATE_LIMIT_ENABLED=0 disables the concurrency ceiling")
finally:
    config.RATE_LIMIT_ENABLED = True

stats = ratelimit.stats()
for key in ("enabled", "per_minute_per_principal", "max_concurrent_expensive",
            "in_flight", "rejected_rate", "rejected_concurrency", "note"):
    check(key in stats, f"metrics report {key}")

# The limiter must never be the thing that breaks engineering: a malformed
# principal is allowed through rather than raising into the request path.
check(ratelimit.check(None, "/api/tools/spec")[0] in (True, False),
      "a malformed principal never raises")

print()
if FAILS:
    print(f"{len(FAILS)} LIMIT TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL LIMIT TESTS PASS")
