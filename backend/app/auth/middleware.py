"""Resolve the principal, enforce the policy, write the audit record.

One place, so every route is covered — including any added later without a
thought for access control (`policy._DEFAULT` makes those administrator-only).

CREDENTIALS ACCEPTED
    Authorization: Bearer <session token>   a signed-in human
    X-Session-Token: <session token>        same, for callers that cannot set
                                            Authorization
    X-API-Key: <service key>                the internal service principal

`X-Role` is NOT read. It used to decide the retrieval permission filter and was
client-supplied, so anyone could claim any role; the role now comes from the
credential and nowhere else.
"""
import time

from fastapi.responses import JSONResponse

from . import policy
from .. import ratelimit
from .store import ANONYMOUS, Principal, resolve_service, resolve_session, write_audit

# Audit noise control: successful reads of these are high-volume and low value.
# Failures are always recorded regardless.
_QUIET_PATHS = ("/api/health",)


def _client_ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    return (fwd.split(",")[0].strip() or
            (request.client.host if request.client else ""))


def resolve_principal(request) -> Principal:
    """Credential -> Principal. Never raises; an unusable credential is anonymous."""
    try:
        api_key = request.headers.get("x-api-key") or ""
        if api_key:
            found = resolve_service(api_key)
            if found:
                return found
        token = request.headers.get("x-session-token") or ""
        if not token:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if token:
            found = resolve_session(token)
            if found:
                return found
    except Exception:
        # A failure to READ a credential must not become a 500 that reveals the
        # auth layer's internals; it is simply not authenticated.
        return ANONYMOUS
    return ANONYMOUS


async def auth_middleware(request, call_next):
    path = request.url.path
    method = request.method

    if method == "OPTIONS" or policy.is_unguarded(path):
        return await call_next(request)

    principal = resolve_principal(request)
    request.state.principal = principal
    # Hand the identity to the trace context. The trace middleware wraps this
    # one, so it began the request before any principal existed.
    try:
        from ..observability import context as _obs_ctx
        _obs_ctx.identify(principal.name, principal.kind, principal.role)
    except Exception:
        pass

    allowed, reason = policy.allows(principal, method, path)
    if not allowed:
        status = 401 if not principal.is_authenticated else 403
        write_audit(actor_kind=principal.kind, actor=principal.name or "-",
                    role=principal.role, action=f"{method} {path}",
                    target=path, status=status, ip=_client_ip(request),
                    detail=f"denied: {reason}")
        body = {"error": "unauthorized" if status == 401 else "forbidden",
                "detail": ("Authentication required."
                           if status == 401 else
                           "This account does not have access to that resource.")}
        return JSONResponse(body, status_code=status)

    # --- runaway guards, AFTER authorization ---------------------------------
    # Order matters: an unauthorized caller is refused before it can consume a
    # rate-limit slot, so a bad credential in a loop cannot exhaust the budget
    # of the principal it is impersonating.
    limited, why, retry_after = ratelimit.check(principal, path)
    if not limited:
        write_audit(actor_kind=principal.kind, actor=principal.name or "-",
                    role=principal.role, action=f"{method} {path}",
                    target=path, status=429, ip=_client_ip(request),
                    detail=f"rate limited: {why}")
        return JSONResponse(
            {"error": "rate_limited",
             "detail": "Too many requests. This limit exists to keep the "
                       "engineering engines responsive; it is set far above "
                       "normal use, so this usually means a client is looping."},
            status_code=429, headers={"Retry-After": str(retry_after)})

    with ratelimit.slot(path) as expensive_slot:
        if not expensive_slot.acquired:
            write_audit(actor_kind=principal.kind, actor=principal.name or "-",
                        role=principal.role, action=f"{method} {path}",
                        target=path, status=429, ip=_client_ip(request),
                        detail="rejected: expensive-route concurrency ceiling")
            return JSONResponse(
                {"error": "busy",
                 "detail": "The engineering engines are at capacity. Retry "
                           "shortly — this ceiling keeps the API answerable "
                           "instead of letting every request stall together."},
                status_code=429, headers={"Retry-After": "5"})

        started = time.perf_counter()
        response = await call_next(request)
        elapsed = int((time.perf_counter() - started) * 1000)

        # Audit every non-public request. Reads included: the point of an audit
        # trail is answering "who looked at that", not only "who changed it".
        if not (path in _QUIET_PATHS and response.status_code < 400):
            write_audit(actor_kind=principal.kind, actor=principal.name or "-",
                        role=principal.role, action=f"{method} {path}",
                        target=path, status=response.status_code,
                        ip=_client_ip(request), detail=f"{elapsed}ms")
        return response
