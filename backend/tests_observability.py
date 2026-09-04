"""Phase C: tracing, jobs, artifacts, metrics and logging.

The companion proof is `tests_api_contract.py`: all 28 engineering endpoints
must stay byte-identical after Phase C *without re-recording*. This suite covers
what that one cannot — that the telemetry itself is correct, and that it holds
to its two rules: never block engineering, never log a customer requirement.

    VT_TEST_ADMIN=... VT_TEST_ADMIN_PASSWORD=... .venv/bin/python tests_observability.py
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

# THIS SUITE MUST NOT WRITE INTO THE LIVE DATA STORE, and until 2026-09-04 it
# did. `ops.db`, `data/jobs/` and the audit trail are declared PERMANENT and are
# never purged, so every run left behind a fake job row, a fake job folder, and
# — because one check deliberately tampers an artifact to prove corruption is
# caught — a permanently CORRUPT file in the artifact store.
#
# Two consequences, both real: the job history an engineer reads in Package
# Center filled up with test rows, and an integrity check over the artifact
# store reported dozens of corrupt documents that were all test residue. A
# monitor that always reports corruption is one nobody believes on the day the
# corruption is real.
#
# The overrides must be set BEFORE the app modules are imported: `ARTIFACT_ROOT`
# and `LOG_DIR` are read at module import, not per call.
_ISOLATED = tempfile.mkdtemp(prefix="vitech-obs-test-")
os.environ["OPS_DB"] = os.path.join(_ISOLATED, "ops.db")
os.environ["ARTIFACT_DIR"] = os.path.join(_ISOLATED, "jobs")
os.environ["LOG_DIR"] = os.path.join(_ISOLATED, "logs")

from app.observability import artifacts, context, jobs, logs, metrics, store, trace, writer  # noqa: E402

BASE = "http://localhost:8000"
FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# The isolation above is load-bearing, so assert it rather than trust it: if an
# app module is ever imported before the overrides are set, these silently
# revert to the live store and this suite starts corrupting real records again.
check(str(artifacts.ARTIFACT_ROOT).startswith(_ISOLATED),
      f"artifacts are isolated from the live store ({artifacts.ARTIFACT_ROOT})")
check(str(store.db_path()).startswith(_ISOLATED),
      f"the job database is isolated from the live store ({store.db_path()})")
check(str(logs.LOG_DIR).startswith(_ISOLATED),
      f"logs are isolated from the live store ({logs.LOG_DIR})")


# --- request ids -------------------------------------------------------------
a, b = context.new_request_id(), context.new_request_id()
check(a != b, "request ids are unique")
check(len(a) >= 20 and a.isalnum(), f"request id is compact and safe ({a})")
time.sleep(0.002)
check(context.new_request_id() > a, "request ids sort chronologically")

# --- spans -------------------------------------------------------------------
# Outside a request a span must be a no-op that STILL RUNS ITS BODY: that is what
# lets the golden tests exercise the engine without tracing changing anything.
context.begin("")
ran = []
with trace.span("nowhere", "test"):
    ran.append(1)
check(ran == [1], "a span outside a request still runs its body")

context.begin("test-req-1", actor="tester", actor_kind="user")
with trace.span("unit.work", "test") as s:
    s.detail(count=3)
check(context.facts()["spans"] == 1, "a span inside a request is recorded")

# An exception must propagate, and be marked on the span rather than swallowed.
raised = False
try:
    with trace.span("unit.boom", "test"):
        raise ValueError("boom")
except ValueError:
    raised = True
check(raised, "a span never swallows the exception it wraps")

# Counters the request summary reports.
context.begin("test-req-2")
trace.count("retrieval_count", 5)
trace.count("rule_count", 2)
trace.note(equipment="paint_booth", tool="generate_specification")
f = context.facts()
check(f["retrieval_count"] == 5 and f["rule_count"] == 2, "counters accumulate")
check(f["equipment"] == "paint_booth", "facts record the equipment")

# `identify` must reach the FACT BAG, not only the ContextVars: Starlette runs
# the downstream app in another task, so a rebind never reaches the middleware
# that wrapped it. This is the bug that left every trace's actor empty.
context.identify("alice", "user", "admin")
check(context.facts().get("actor") == "alice",
      "identify writes to the fact bag so it crosses the task boundary")

# --- log redaction -----------------------------------------------------------
# The rule: a customer requirement never enters a log file.
redacted = logs._redact({
    "question": "paint booth 5m x 3m x 4m",
    "requirement": "wet scrubber 800 cfm",
    "password": "hunter2",
    "x-api-key": "secret-key",
    "equipment": "paint_booth",
    "nested": {"token": "abc", "count": 3},
})
check(redacted["question"] == "<redacted>", "a customer requirement never reaches the log")
check(redacted["requirement"] == "<redacted>", "requirement text is redacted")
check(redacted["password"] == "<redacted>" and redacted["x-api-key"] == "<redacted>",
      "credentials are redacted")
check(redacted["nested"]["token"] == "<redacted>", "redaction recurses")
check(redacted["equipment"] == "paint_booth", "non-sensitive fields survive")
check(len(logs._redact({"s": "x" * 900})["s"]) <= 501, "long strings are truncated")

# --- artifacts ---------------------------------------------------------------
job_id = jobs.create("specification", requirement="paint booth 5m x 3m x 4m",
                     equipment="paint_booth")
check(store.get_job(job_id) is not None, "a job is persisted immediately")

row = jobs.attach(job_id, "Test.pdf", b"%PDF-1.4 test bytes")
check(row["sha256"] == __import__("hashlib").sha256(b"%PDF-1.4 test bytes").hexdigest(),
      "an artifact records its SHA-256")
got = artifacts.read(job_id, "Test.pdf")
check(got is not None and got[0] == b"%PDF-1.4 test bytes", "an artifact reads back intact")
check(all(x["state"] == "ok" for x in artifacts.verify(job_id)), "integrity verifies")

# A corrupted artifact must be reported missing, not served as though genuine.
from pathlib import Path                                            # noqa: E402
Path(row["path"]).write_bytes(b"tampered")
check(artifacts.read(job_id, "Test.pdf") is None,
      "a file that no longer matches its digest is NOT served")
check(any(x["state"] == "corrupt" for x in artifacts.verify(job_id)),
      "tampering is reported as corrupt")

# Path traversal: a job id or artifact name from a request must not escape.
safe = artifacts._safe_name("../../etc/passwd")
check("/" not in safe and ".." not in safe, f"artifact names cannot traverse ({safe})")
check(str(artifacts.job_dir("../../evil")).startswith(str(artifacts.ARTIFACT_ROOT)),
      "a job directory stays inside the artifact root")

jobs.finish(job_id, equipment="paint_booth", confidence_pct=93,
            release_status="Customer Review Draft", warning_count=1)
done = jobs.get(job_id)
check(done["status"] == "succeeded" and done["confidence_pct"] == 93,
      "a job records its engineering outcome")
check(done["requirement"] == "paint booth 5m x 3m x 4m",
      "the customer requirement is persisted on the job, verbatim")
check(done["duration_ms"] is not None, "a job records its duration")

# --- the writer never blocks -------------------------------------------------
before = writer.stats()
for i in range(50):
    writer.submit("span", {"request_id": "bulk", "seq": i, "name": "x",
                           "kind": "test", "started_at": time.time(),
                           "duration_ms": 1, "ok": 1, "detail": {}})
check(writer.stats()["queued"] >= 0, "submitting telemetry never raises")
writer.flush(10)
check(writer.stats()["written"] > before["written"], "the background writer drains")
writer.submit("nonsense-kind", {})
writer.flush(5)
check(writer.stats()["errors"] == before["errors"],
      "an unknown record type is ignored, not an error")

# --- metrics -----------------------------------------------------------------
m = metrics.summary(24)
for key in ("requests", "failure_rate", "response_time", "llm", "retrieval",
            "package_generation", "active_users", "active_service_principals",
            "cache", "telemetry_writer", "store", "logs"):
    check(key in m, f"metrics report {key}")
check("note" in m["cache"], "cache stats say the counters are per-process")

# --- retention ---------------------------------------------------------------
n_jobs_before = len(jobs.listing(limit=1000))
result = store.purge(days=36500)          # nothing is old enough
check(result["requests_removed"] == 0, "purge respects the retention horizon")
check(len(jobs.listing(limit=1000)) == n_jobs_before,
      "purging request traces NEVER removes jobs — they are permanent")

# --- live: the admin surface --------------------------------------------------
ADMIN, PASSWORD = os.getenv("VT_TEST_ADMIN", ""), os.getenv("VT_TEST_ADMIN_PASSWORD", "")


def call(path, token="", method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, {}, dict(e.headers)


if not (ADMIN and PASSWORD):
    print("\n(live tests skipped — set VT_TEST_ADMIN / VT_TEST_ADMIN_PASSWORD)")
else:
    st, body, _ = call("/api/auth/login", method="POST",
                       payload={"username": ADMIN, "password": PASSWORD})
    token = body.get("token", "")
    check(st == 200 and token, "admin login for the live checks")

    st, _, headers = call("/api/health")
    check("X-Request-ID" in headers or "x-request-id" in {k.lower() for k in headers},
          "every response carries X-Request-ID")

    st, _, headers = call("/api/tools/spec", token, "POST",
                          {"question": "wet scrubber 800 cfm 750mm tower 4 nos"})
    rid = headers.get("X-Request-ID") or headers.get("x-request-id")
    check(st == 200 and rid, "an engineering request returns its trace id in a header")
    writer.flush(10)
    time.sleep(0.5)

    st, tr, _ = call(f"/api/admin/trace/{rid}", token)
    check(st == 200 and tr.get("found"), "the trace viewer finds the request")
    req = tr.get("request") or {}
    check(req.get("tool") == "generate_specification", "the trace records the tool")
    check(req.get("equipment") == "wet_scrubber", "the trace records the equipment")
    check(req.get("actor") == ADMIN, "the trace attributes the request to its actor")
    check(req.get("retrieval_count", 0) > 0, "the trace counts historical retrieval")
    kinds = {s["kind"] for s in tr.get("spans") or []}
    check("retrieval" in kinds and "resolve" in kinds,
          f"the execution path is reconstructed ({sorted(kinds)})")
    check(any(j["kind"] == "specification" for j in tr.get("jobs") or []),
          "the trace links to the job it produced")

    st, body, _ = call("/api/admin/jobs?kind=specification", token)
    check(st == 200 and body.get("jobs"), "job history is queryable")
    check(all("requirement" in j for j in body["jobs"]),
          "job history carries the customer requirement (role-gated)")

    st, body, _ = call("/api/admin/metrics", token)
    check(st == 200 and body.get("requests", 0) > 0, "metrics are live")

    st, body, _ = call("/api/admin/logs?limit=5", token)
    check(st == 200 and isinstance(body.get("entries"), list), "structured logs are readable")
    blob = json.dumps(body.get("entries") or [])
    check("wet scrubber 800" not in blob and "paint booth 5m" not in blob,
          "NO customer requirement appears in the structured logs")

    st, _, _ = call("/api/admin/metrics")
    check(st == 401, "the DevOps surface is not public")

    # --- single resolution per package -------------------------------------
    # The trace found /api/package resolving the same requirement twice, and
    # parsing it a third time for the quotation. This pins the fix: reuse of the
    # one analysis is what makes the package's "documents cannot disagree"
    # guarantee true by construction, not merely faster.
    st, _, headers = call("/api/package", token, "POST",
                          {"question": "paint booth 5m x 3m x 4m liquid down draft"})
    pkg_rid = headers.get("X-Request-ID") or headers.get("x-request-id")
    check(st == 200 and pkg_rid, "package generation traced")
    writer.flush(10)
    time.sleep(0.5)
    st, tr, _ = call(f"/api/admin/trace/{pkg_rid}", token)
    names = [s["name"] for s in tr.get("spans") or []]
    for stage in ("retrieve.offers", "resolve.spec", "rules.apply"):
        check(names.count(stage) == 1,
              f"{stage} runs EXACTLY ONCE per package (got {names.count(stage)})")
    check(any(n.startswith("package.") for n in names),
          "the package stages are still traced")

print()
if FAILS:
    print(f"{len(FAILS)} OBSERVABILITY TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL OBSERVABILITY TESTS PASS")
