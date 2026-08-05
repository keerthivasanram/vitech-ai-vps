import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getToken, installAuthFetch, SESSION_EXPIRED, setToken } from "../lib/api";

/**
 * Front-end session, backed by REAL server-side authentication.
 *
 * This used to match credentials in the browser against a hard-coded list —
 * which meant the password shipped in the JS bundle to every visitor, and the
 * `role` field was decorative because nothing server-side read it. Both are
 * gone: `login()` now calls `POST /api/auth/login`, the server issues an opaque
 * session token, and the ROLE COMES BACK FROM THE SERVER. The browser cannot
 * grant itself anything — every route is checked again on each request.
 *
 * The token is the credential, so it is the only thing that must be kept. The
 * cached user object is a convenience for rendering; `/api/auth/me` is the
 * authority and is re-checked on load.
 */

const SESSION_KEY = "vitech_session";

installAuthFetch();

function readCachedUser() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    return s && s.user ? s.user : null;
  } catch {
    return null;
  }
}

function cacheUser(user) {
  try {
    if (user) localStorage.setItem(SESSION_KEY, JSON.stringify({ user }));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage unavailable — the session just won't survive a reload */
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // `ready` avoids a login-screen flash before the stored session is checked.
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  /* Re-validate on load. A cached user proves nothing — the token may have
     expired, been revoked, or the server may have been rebuilt — so the server
     is asked who we are before anything is rendered as signed in. */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!getToken()) {
        cacheUser(null);
        if (!cancelled) setReady(true);
        return;
      }
      try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
          const me = await res.json();
          const current = {
            username: me.username, name: me.username, role: me.role,
            // Re-read from the SERVER on every load, so a refresh cannot walk
            // past the mandatory password change.
            mustChangePassword: !!me.must_change_password,
          };
          cacheUser(current);
          if (!cancelled) setUser(current);
        } else {
          setToken("");
          cacheUser(null);
        }
      } catch {
        // Backend unreachable: fall back to the cached identity so the app
        // still renders. Every API call will still be authorised server-side,
        // so this cannot grant access — it only avoids a login screen during a
        // transient outage.
        if (!cancelled) setUser(readCachedUser());
      }
      if (!cancelled) setReady(true);
    })();
    return () => { cancelled = true; };
  }, []);

  /* A session that expires or is revoked mid-use drops the user back to the
     login screen instead of leaving a page of failed requests. */
  useEffect(() => {
    const onExpired = () => { cacheUser(null); setUser(null); };
    window.addEventListener(SESSION_EXPIRED, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED, onExpired);
  }, []);

  const login = useCallback(async ({ username, password }) => {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.token) {
        // The server deliberately does not say WHICH of the two was wrong.
        return { ok: false, error: data.error || "Incorrect username or password." };
      }
      setToken(data.token);
      const current = {
        username: data.user?.username || username,
        name: data.user?.name || username,
        role: data.user?.role || "engineer",
        mustChangePassword: !!data.user?.must_change_password,
      };
      cacheUser(current);
      setUser(current);
      return { ok: true, mustChangePassword: current.mustChangePassword };
    } catch {
      return { ok: false, error: "Could not reach the server. Is the backend running?" };
    }
  }, []);

  const logout = useCallback(async () => {
    // Tell the server first so the session is revoked rather than merely
    // forgotten by this browser — a token dropped locally but still valid is
    // exactly what an attacker who copied it would want.
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* offline: the token is cleared locally and expires server-side */
    }
    setToken("");
    cacheUser(null);
    setUser(null);
  }, []);

  /** Clears the must-change flag locally once the server has accepted the new
   *  password, so the gate lifts without a reload. */
  const changePassword = useCallback(async (currentPassword, newPassword) => {
    try {
      const res = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return { ok: false, error: data.error || "Could not change the password." };
      if (data.token) setToken(data.token);      // other sessions were revoked
      setUser((u) => {
        const next = { ...(u || {}), mustChangePassword: false };
        cacheUser(next);
        return next;
      });
      return { ok: true };
    } catch {
      return { ok: false, error: "Could not reach the server." };
    }
  }, []);

  const value = useMemo(
    () => ({ user, ready, login, logout, changePassword }),
    [user, ready, login, logout, changePassword]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
