"""HTTP-level contract fingerprints — proof that a refactor changed nothing.

The nine engine suites call Python functions directly, so endpoint wiring, the
no-requirement guards, status codes and response SHAPES are untested: a route
could be deleted and every suite would stay green. This closes that gap and, in
doing so, gives the Phase-A refactor its safety net.

    .venv/bin/python tests_api_contract.py --record   # write the baseline
    .venv/bin/python tests_api_contract.py            # compare against it

A fingerprint is the status code plus a SHA-256 of the canonicalised body, so a
byte-level difference anywhere in a response fails the run. Values that legitimately
move between runs (today's date in a generated reference, wall-clock timings) are
normalised out by `_canon` — never the engineering values, which must not move.

Requires the backend running on :8000.
"""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
BASELINE = "tests_api_contract.json"

# Deterministic requirements reused across endpoints, so a fingerprint change
# points at the endpoint rather than at a different question being asked.
BOOTH = "paint booth 5m x 3m x 4m liquid down draft"
SCRUB = "wet scrubber 800 cfm 750mm tower 4 nos"
DUST = "dust collector 6000 cmh pulse jet casing 1200x1200x2500mm"

CASES: list[tuple[str, str, str, dict | None]] = [
    # The OpenAPI schema IS the API contract. It is fingerprinted first because
    # `operation_id` becomes the tool name the Flowise agents call: a route
    # moved into a router that silently regenerates its id would rename a live
    # agent tool, and nothing else in the suite would notice.
    ("openapi", "GET", "/openapi.json", None),
    # --- health / data ----------------------------------------------------
    ("health", "GET", "/api/health", None),
    ("offers.list", "GET", "/api/offers", None),
    ("offers.one", "GET", "/api/offers/OFF-CRI-PB-082406R4", None),
    ("offers.by_source", "GET", "/api/offers/by-source/CRI%20PUMP%20PB%2010.10.24-R4.pdf", None),
    ("knowledge.overview", "GET", "/api/knowledge/overview", None),
    ("records", "GET", "/api/records", None),
    ("uploads.list", "GET", "/api/uploads", None),
    ("datasheet.forms", "GET", "/api/datasheet/forms", None),
    ("drawing.catalog", "GET", "/api/drawing/catalog", None),
    ("tools.filters", "GET", "/api/tools/filters", None),
    # --- the deterministic engine ----------------------------------------
    ("tools.spec.booth", "POST", "/api/tools/spec", {"question": BOOTH}),
    ("tools.spec.scrub", "POST", "/api/tools/spec", {"question": SCRUB}),
    ("tools.spec.dust", "POST", "/api/tools/spec", {"question": DUST}),
    ("tools.quote.scrub", "POST", "/api/tools/quote", {"question": SCRUB}),
    ("tools.lookup", "POST", "/api/tools/lookup", {"question": "Armstrong"}),
    ("tools.list", "POST", "/api/tools/list", {"question": "how many projects"}),
    ("tools.retrieve", "POST", "/api/tools/retrieve", {"question": "face velocity"}),
    ("tools.drawing.booth", "POST", "/api/tools/drawing", {"question": BOOTH}),
    ("tools.drawing.dust", "POST", "/api/tools/drawing", {"question": DUST}),
    ("bom.booth", "POST", "/api/bom", {"question": BOOTH}),
    ("drawing.render", "POST", "/api/drawing/render",
     {"category": "paint_booth",
      "values": {"length_m": 5, "width_m": 3, "height_m": 4, "paint_type": "liquid"},
      "sheet_size": "A3"}),
    ("package.booth", "POST", "/api/package", {"question": BOOTH}),
    # --- the guards: a non-requirement must never reach the engine --------
    ("guard.spec", "POST", "/api/tools/spec", {"question": "hello there"}),
    ("guard.quote", "POST", "/api/tools/quote", {"question": "hello there"}),
    ("guard.drawing", "POST", "/api/tools/drawing", {"question": "hello there"}),
    ("guard.bom", "POST", "/api/bom", {"question": "hello there"}),
    ("guard.package", "POST", "/api/package", {"question": "hello there"}),
]

# Values that legitimately differ between runs. Engineering values are NEVER
# normalised — the point of the fingerprint is that they cannot move.
_VOLATILE = [
    (re.compile(r'"(ref|drawing_no|DRG No\.?)"\s*:\s*"[^"]*"'), r'"\1":"<ref>"'),
    (re.compile(r'VT/(GA|PKG|QTN|Q)/\d{6}/[A-Z]+'), 'VT/<x>/<date>/<status>'),
    (re.compile(r'"(date|generated|created|started_at|finished_at)"\s*:\s*"?[^",}]*"?'),
     r'"\1":"<time>"'),
    (re.compile(r'\d{2}-\d{2}-\d{4}'), '<dd-mm-yyyy>'),
    (re.compile(r'\d{4}-\d{2}-\d{2}'), '<yyyy-mm-dd>'),
    (re.compile(r'\d{2} [A-Z][a-z]{2} \d{4}'), '<dd Mon yyyy>'),
    (re.compile(r'"documents_indexed"\s*:\s*\d+'), '"documents_indexed":<n>'),
]


def _canon(body: str) -> str:
    """Canonical form: stable key order, volatile values masked."""
    try:
        body = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
    except ValueError:
        pass                                   # HTML or plain text: compare raw
    for pattern, repl in _VOLATILE:
        body = pattern.sub(repl, body)
    return body


def fingerprint(method: str, path: str, payload: dict | None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            status, body = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
    canon = _canon(body)
    return {"status": status, "sha256": hashlib.sha256(canon.encode()).hexdigest(),
            "bytes": len(body)}


def collect() -> dict:
    out = {}
    for name, method, path, payload in CASES:
        out[name] = fingerprint(method, path, payload)
    return out


def main() -> int:
    record = "--record" in sys.argv
    current = collect()

    if record:
        with open(BASELINE, "w") as fh:
            json.dump(current, fh, indent=2, sort_keys=True)
        print(f"Recorded {len(current)} endpoint fingerprints -> {BASELINE}")
        for name, fp in sorted(current.items()):
            print(f"  {fp['status']}  {name:24s} {fp['sha256'][:12]}  {fp['bytes']:>7} B")
        return 0

    try:
        with open(BASELINE) as fh:
            base = json.load(fh)
    except FileNotFoundError:
        print(f"No baseline. Run with --record first."); return 1

    fails = []
    for name in sorted(set(base) | set(current)):
        b, c = base.get(name), current.get(name)
        if b is None:
            fails.append(f"{name}: NEW endpoint, not in baseline"); continue
        if c is None:
            fails.append(f"{name}: MISSING — the route is gone"); continue
        if b["status"] != c["status"]:
            fails.append(f"{name}: status {b['status']} -> {c['status']}"); continue
        if b["sha256"] != c["sha256"]:
            fails.append(f"{name}: body changed ({b['bytes']} -> {c['bytes']} bytes)")
            continue
        print(f"OK   {name:24s} {c['status']} {c['sha256'][:12]}")

    print()
    if fails:
        print(f"{len(fails)} API CONTRACT FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print(f"ALL API CONTRACT TESTS PASS ({len(current)} endpoints byte-identical)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
