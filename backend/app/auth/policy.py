"""The endpoint security matrix, as code.

`docs/endpoint-security-matrix.md` is the agreed policy; this is that policy
executable, so the two cannot drift. A test asserts every registered route is
classified here.

WHY A CENTRAL TABLE rather than a dependency on each route. Deny-by-default only
means something if it applies to routes nobody remembered to decorate. A new
endpoint added next year is covered by `_DEFAULT` — administrator — whether or
not its author thought about access control. Per-route decorators fail open on
exactly the route most likely to be forgotten.

CLASSES (V1.0 roles: engineer, admin, internal service — no viewer)
    PUBLIC   .. no credentials. One route only.
    ENGINEER .. any signed-in human. Every human account is at least an engineer.
    ADMIN .... administrators only.
    SERVICE .. reachable by the internal service principal (the Flowise agents).
               ADDITIVE to a class, never a substitute: a route marked
               ENGINEER|SERVICE is reachable by a signed-in engineer OR by the
               agents, and by nothing else.
"""
import re
from typing import Optional

from .store import ROLE_ADMIN, ROLE_ENGINEER, Principal

PUBLIC = "public"
ENGINEER = ROLE_ENGINEER
ADMIN = ROLE_ADMIN

# Anything not listed below requires an administrator. Deliberately the
# strictest class: an unclassified route is an oversight, and an oversight
# should fail closed.
_DEFAULT = (ADMIN, False)

# (method regex, path regex) -> (required class, service principal allowed)
# Ordered: the first match wins, so specific paths precede general ones.
_RULES: list[tuple[str, str, tuple[str, bool]]] = [
    # --- public ------------------------------------------------------------
    (r".*", r"^/api/health$", (PUBLIC, True)),

    # --- authentication itself ---------------------------------------------
    # Login must be reachable by someone with no session yet; the endpoint
    # rate-limits and locks out on its own.
    (r"POST", r"^/api/auth/login$", (PUBLIC, False)),
    (r".*", r"^/api/auth/(logout|me|password)$", (ENGINEER, False)),

    # --- the agent tool bridge: engineers AND the service principal ---------
    # This is the ONLY group a service key can reach. A leaked agent key
    # therefore cannot ingest, upload, read logs or browse the database.
    (r".*", r"^/api/tools/", (ENGINEER, True)),

    # --- administrator: system state and operational internals -------------
    (r".*", r"^/api/admin/", (ADMIN, False)),
    (r".*", r"^/api/ingest", (ADMIN, False)),
    (r"POST", r"^/api/uploads$", (ADMIN, False)),
    # LEGACY developer endpoints. The backend's own chat engine predates the
    # Flowise architecture and has no caller in the product; kept for now,
    # administrator-only, and hidden from the public API schema.
    (r".*", r"^/api/query", (ADMIN, False)),
    (r".*", r"^/api/session/", (ADMIN, False)),

    # Engineering job history and artifact downloads. Engineer-level because
    # producing these documents IS the engineer's job; the parallel
    # `/api/admin/jobs` view stays administrator-only.
    (r"GET", r"^/api/jobs", (ENGINEER, False)),

    # --- engineer: the engines, the documents, and the data views ----------
    (r".*", r"^/api/(bom|package|drawing|quotation|specification|datasheet)", (ENGINEER, False)),
    # Siting carries a CUSTOMER PHOTOGRAPH in its payload, so the service
    # principal is deliberately excluded: a leaked agent key must not be able
    # to post pictures of a customer's premises into the platform.
    (r".*", r"^/api/siting/", (ENGINEER, False)),
    (r".*", r"^/api/(offers|records|knowledge)", (ENGINEER, False)),
    (r"GET", r"^/api/uploads$", (ENGINEER, False)),
    (r"GET", r"^/records$", (ENGINEER, False)),
]

_COMPILED = [(re.compile(m), re.compile(p), req) for m, p, req in _RULES]

# Paths outside /api that are framework-owned, not application routes.
_UNGUARDED = re.compile(r"^/(docs|redoc|openapi\.json|favicon\.ico)")


def requirement(method: str, path: str) -> tuple[str, bool]:
    """(required class, service allowed) for a request."""
    for m_re, p_re, req in _COMPILED:
        if m_re.match(method) and p_re.search(path):
            return req
    return _DEFAULT


def is_unguarded(path: str) -> bool:
    """API docs and the schema. Not application data.

    NOTE these are open because they describe the API rather than expose it.
    Set `DOCS_ENABLED=0` to remove them entirely for an exposed deployment.
    """
    return bool(_UNGUARDED.match(path))


def allows(principal: Principal, method: str, path: str) -> tuple[bool, str]:
    """(allowed, reason). The reason is for the audit log, not the client."""
    required, service_ok = requirement(method, path)
    if required == PUBLIC:
        return True, "public"
    if not principal.is_authenticated:
        return False, "no credentials"
    if principal.is_service:
        # A service principal is never granted a human role: it is allowed only
        # where the route explicitly opts in.
        return (True, "service principal") if service_ok else (False, "service principal not permitted here")
    if principal.has_role(required):
        return True, f"role {principal.role} >= {required}"
    return False, f"role {principal.role} < {required}"


def describe() -> list[dict]:
    """The matrix, for the admin console and for the coverage test."""
    return [{"method": m, "path": p, "requires": req[0], "service_allowed": req[1]}
            for m, p, req in _RULES]
