"""Authentication, authorization and audit.

`tests_api_contract.py` proves the engineering output did not move when auth was
added. THIS suite proves the routes are actually closed — the two together are
the Phase B contract.

    VT_TEST_ADMIN=... VT_TEST_ADMIN_PASSWORD=... \
    VT_TEST_ENGINEER=... VT_TEST_ENGINEER_PASSWORD=... \
    VT_TEST_SERVICE_KEY=... .venv/bin/python tests_auth.py

Needs the backend running on :8000 and the accounts created by
`python -m app.auth.bootstrap`.
"""
import json
import os
import sys
import urllib.error
import urllib.request

from app.auth import passwords, policy
from app.auth.store import ANONYMOUS, Principal, ROLE_ADMIN, ROLE_ENGINEER

BASE = "http://localhost:8000"
FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


def call(method: str, path: str, *, token: str = "", key: str = "",
         payload: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode(), e.code
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


# --- unit: hashing and the policy table, no server needed --------------------
salt = passwords.new_salt()
h = passwords.hash_password("correct horse battery staple", salt)
check(passwords.verify_password("correct horse battery staple", salt, h),
      "a correct password verifies")
check(not passwords.verify_password("wrong", salt, h), "a wrong password does not")
check(h != passwords.hash_password("correct horse battery staple", passwords.new_salt()),
      "the same password with a different salt hashes differently")
check(not passwords.verify_password("x", salt, "not-base64!!"),
      "a malformed stored hash is a failure, never an exception")

tok = passwords.new_token()
check(passwords.token_matches(tok, passwords.token_hash(tok)), "a token matches its hash")
check(not passwords.token_matches(tok, ""), "a token never matches an empty hash")

# The policy is the security matrix; these pin the decisions that were agreed.
check(policy.requirement("GET", "/api/health") == (policy.PUBLIC, True),
      "health is the one public route")
check(policy.requirement("POST", "/api/tools/spec") == (ROLE_ENGINEER, True),
      "agent tools are engineer-level AND service-reachable")
check(policy.requirement("GET", "/api/offers")[1] is False,
      "the service principal may NOT read the offer corpus")
check(policy.requirement("POST", "/api/admin/reload-index") == (ROLE_ADMIN, False),
      "admin routes are administrator-only")
check(policy.requirement("POST", "/api/query") == (ROLE_ADMIN, False),
      "the legacy chat engine is administrator-only")
check(policy.requirement("GET", "/api/some/route/invented/later") == (ROLE_ADMIN, False),
      "an UNCLASSIFIED route defaults to administrator — deny by default")

engineer = Principal(kind="user", name="e", role=ROLE_ENGINEER)
admin = Principal(kind="user", name="a", role=ROLE_ADMIN)
service = Principal(kind="service", name="agents", role="service")
check(admin.has_role(ROLE_ENGINEER), "an administrator inherits engineer rights")
check(not engineer.has_role(ROLE_ADMIN), "an engineer does NOT inherit admin rights")
check(not service.has_role(ROLE_ENGINEER),
      "a service principal never satisfies a HUMAN role")
check(policy.allows(service, "POST", "/api/tools/spec")[0],
      "the service principal reaches the agent tools")
check(not policy.allows(service, "GET", "/api/offers")[0],
      "a LEAKED AGENT KEY cannot read the corpus")
check(not policy.allows(service, "POST", "/api/ingest")[0],
      "a leaked agent key cannot ingest")
check(not policy.allows(ANONYMOUS, "GET", "/api/offers")[0],
      "anonymous is refused everywhere but the public route")

# --- live: the server actually enforces it -----------------------------------
ADMIN_U, ADMIN_P = os.getenv("VT_TEST_ADMIN", ""), os.getenv("VT_TEST_ADMIN_PASSWORD", "")
ENG_U, ENG_P = os.getenv("VT_TEST_ENGINEER", ""), os.getenv("VT_TEST_ENGINEER_PASSWORD", "")
SVC = os.getenv("VT_TEST_SERVICE_KEY", "")

status, body = call("GET", "/api/health")
check(status == 200 and body == {"status": "ok"},
      f"public health returns status ONLY (got {body})")
check("llm_model" not in str(body) and "ollama" not in str(body).lower(),
      "public health leaks no infrastructure detail")

if not (ADMIN_U and ENG_U and SVC):
    print("\n(live role tests skipped — set VT_TEST_* to run them)")
else:
    for path in ("/api/offers", "/api/records", "/api/tools/filters",
                 "/api/admin/audit", "/api/query"):
        st, _ = call("GET", path)
        check(st == 401, f"no credentials -> 401 on {path} (got {st})")

    st, body = call("POST", "/api/auth/login",
                    payload={"username": ADMIN_U, "password": "definitely-wrong"})
    check(st == 401, "a wrong password is refused")
    check("username" not in json.dumps(body).lower() or "invalid username or password" in
          json.dumps(body).lower(),
          "the failure does not reveal WHICH of user/password was wrong")

    st, body = call("POST", "/api/auth/login",
                    payload={"username": "no-such-user-here", "password": "x"})
    check(st == 401, "an unknown user is refused")

    st, body = call("POST", "/api/auth/login", payload={"username": ENG_U, "password": ENG_P})
    check(st == 200 and body.get("token"), "an engineer can log in")
    eng_token = body.get("token", "")
    check(body.get("user", {}).get("role") == ROLE_ENGINEER,
          "the role comes from the SERVER, not the client")

    st, body = call("POST", "/api/auth/login", payload={"username": ADMIN_U, "password": ADMIN_P})
    check(st == 200 and body.get("token"), "an administrator can log in")
    admin_token = body.get("token", "")

    st, _ = call("GET", "/api/offers", token=eng_token)
    check(st == 200, "an engineer reaches the engineering data")
    st, _ = call("POST", "/api/tools/spec", token=eng_token,
                 payload={"question": "paint booth 5m x 3m x 4m liquid"})
    check(st == 200, "an engineer reaches the engines")
    st, _ = call("GET", "/api/admin/audit", token=eng_token)
    check(st == 403, "an engineer is FORBIDDEN from admin routes (403, not 401)")
    st, _ = call("GET", "/api/admin/audit", token=admin_token)
    check(st == 200, "an administrator reaches admin routes")

    st, _ = call("GET", "/api/tools/filters", key=SVC)
    check(st == 200, "the service principal reaches the agent tools")
    st, _ = call("GET", "/api/offers", key=SVC)
    check(st == 403, "the service principal is refused the offer corpus")
    st, _ = call("POST", "/api/ingest", key=SVC)
    check(st == 403, "the service principal cannot ingest")
    st, _ = call("GET", "/api/admin/audit", key=SVC)
    check(st == 403, "the service principal cannot read the audit trail")

    st, _ = call("GET", "/api/tools/filters", key="not-a-real-key")
    check(st == 401, "a bogus service key is unauthenticated")
    st, _ = call("GET", "/api/offers", token="not-a-real-token")
    check(st == 401, "a bogus session token is unauthenticated")

    st, body = call("GET", "/api/auth/me", token=eng_token)
    check(st == 200 and body.get("username") == ENG_U, "/api/auth/me identifies the caller")

    # Revocation is why sessions are stored rather than self-contained.
    call("POST", "/api/auth/logout", token=eng_token)
    st, _ = call("GET", "/api/offers", token=eng_token)
    check(st == 401, "a logged-out session stops working IMMEDIATELY")

    st, body = call("GET", "/api/admin/audit", token=admin_token)
    entries = body.get("entries") or []
    check(any(e.get("action", "").endswith("/api/auth/login") for e in entries),
          "logins are audited")
    check(any(e.get("status") in (401, 403) for e in entries),
          "denials are audited")
    check(any(str(e.get("detail", "")).startswith("denied") for e in entries),
          "the audit records WHY a request was denied")
    check(not any("password" in json.dumps(e).lower() and ADMIN_P in json.dumps(e)
                  for e in entries),
          "no password ever reaches the audit trail")

    st, body = call("GET", "/api/admin/health/detail", token=admin_token)
    check(st == 200 and "services" in body,
          "the detailed diagnostics moved behind the admin role")

print()
if FAILS:
    print(f"{len(FAILS)} AUTH TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL AUTH TESTS PASS")
