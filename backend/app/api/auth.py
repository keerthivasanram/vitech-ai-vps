"""Authentication endpoints: login, logout, identity, password change."""
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from ..auth import store
from ..auth.middleware import _client_ip
from ..auth.store import SESSION_DAYS

router = APIRouter()


@router.post("/api/auth/login")
def login(request: Request, payload: dict = Body(...)):
    """Exchange credentials for a session token.

    The failure response is deliberately identical for an unknown user, a wrong
    password and a disabled account: distinguishing them tells an attacker which
    usernames exist. The real reason goes to the audit log.
    """
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    ip = _client_ip(request)

    user, reason = store.authenticate(username, password)
    if user is None:
        store.write_audit(actor_kind="anonymous", actor=username or "-",
                          action="POST /api/auth/login", target="login",
                          status=401, ip=ip, detail=f"failed: {reason}")
        return JSONResponse(
            {"ok": False, "error": "Invalid username or password."}, status_code=401)

    token = store.create_session(
        user["id"], ip=ip, user_agent=request.headers.get("user-agent") or "")
    store.write_audit(actor_kind="user", actor=user["username"], role=user["role"],
                      action="POST /api/auth/login", target="login", status=200, ip=ip,
                      detail="ok")
    return {
        "ok": True,
        "token": token,
        "expires_in_days": SESSION_DAYS,
        "user": {"username": user["username"], "name": user["name"],
                 "role": user["role"],
                 "must_change_password": bool(user["must_change_password"])},
    }


@router.post("/api/auth/logout")
def logout(request: Request):
    """Revoke the presented session server-side.

    Revocation is why sessions are stored rather than self-contained tokens: a
    signed-out or compromised session must stop working immediately, which a
    stateless JWT cannot do before it expires.
    """
    auth = request.headers.get("authorization") or ""
    token = (request.headers.get("x-session-token") or
             (auth[7:].strip() if auth.lower().startswith("bearer ") else ""))
    if token:
        store.revoke_session(token)
    return {"ok": True}


@router.get("/api/auth/me")
def me(request: Request):
    """Who the caller is, as the SERVER sees them."""
    p = getattr(request.state, "principal", None)
    if p is None or not p.is_authenticated:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    out = {"ok": True, "kind": p.kind, "username": p.name, "role": p.role}
    # The must-change flag is re-read on every identity check, not just at
    # sign-in. Without it a page refresh would drop the flag and walk straight
    # past the mandatory password change — the gate has to be re-asserted by the
    # SERVER, or it is only a suggestion the browser is free to forget.
    if p.kind == "user":
        row = store.get_user(p.name)
        out["must_change_password"] = bool(row["must_change_password"]) if row else False
    return out


@router.post("/api/auth/password")
def change_password(request: Request, payload: dict = Body(...)):
    """Change your own password. Requires the current one.

    Every other session for the account is revoked: if the password was changed
    because it may have leaked, leaving the other sessions alive defeats the
    purpose.
    """
    p = getattr(request.state, "principal", None)
    if p is None or p.kind != "user":
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    current = str(payload.get("current_password") or "")
    new = str(payload.get("new_password") or "")
    if len(new) < 12:
        return JSONResponse(
            {"ok": False, "error": "The new password must be at least 12 characters."},
            status_code=400)

    user, _ = store.authenticate(p.name, current)
    if user is None:
        store.write_audit(actor_kind="user", actor=p.name, role=p.role,
                          action="POST /api/auth/password", status=401,
                          ip=_client_ip(request), detail="wrong current password")
        return JSONResponse({"ok": False, "error": "The current password is incorrect."},
                            status_code=401)

    store.set_password(user["id"], new)
    revoked = store.revoke_user_sessions(user["id"])
    fresh = store.create_session(user["id"], ip=_client_ip(request),
                                 user_agent=request.headers.get("user-agent") or "")
    store.write_audit(actor_kind="user", actor=p.name, role=p.role,
                      action="POST /api/auth/password", status=200,
                      ip=_client_ip(request),
                      detail=f"changed; {revoked} session(s) revoked")
    return {"ok": True, "token": fresh, "revoked_sessions": revoked}
