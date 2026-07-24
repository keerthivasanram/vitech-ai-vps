import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Front-end session/auth.
 *
 * There is no auth backend yet (see CLAUDE.md "E1. permission_filter — needs a
 * user/role/ACL model, none today"), so this validates credentials against a
 * configured local account list and keeps a signed session in localStorage.
 * It is a gate + session layer for the single-tenant deployment, NOT real
 * security — `login()` is written as the one seam to swap for a real
 * `POST /api/auth/login` when the multi-user phase lands. Everything else
 * (the gate, the session, logout, the UI) stays the same.
 */

const SESSION_KEY = "vitech_session";
const SESSION_DAYS = 7;

/* Accounts. Override in .env with VITE_AUTH_USERS as a JSON array of
   {username, password, name, role}. Falls back to a single admin account. */
function configuredUsers() {
  const raw = import.meta.env.VITE_AUTH_USERS;
  if (raw) {
    try {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr) && arr.length) return arr;
    } catch {
      /* fall through to default */
    }
  }
  return [
    { username: "admin", password: "vitech@123", name: "Loganathan R", role: "Admin" },
    { username: "sales", password: "vitech@123", name: "Sales Desk", role: "Sales Engineer" },
  ];
}

function readSession() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    if (s && s.exp && s.exp > Date.now() && s.user) return s;
  } catch {
    /* ignore */
  }
  return null;
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // `ready` avoids a login-screen flash before the stored session is read.
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const s = readSession();
    if (s) setUser(s.user);
    setReady(true);
  }, []);

  /* The single seam for a real backend: replace the local match with a fetch,
     keep the session write + setUser identical. Returns {ok, error}. */
  const login = useCallback(async ({ username, password, remember = true }) => {
    const u = (username || "").trim().toLowerCase();
    const match = configuredUsers().find(
      (a) => a.username.toLowerCase() === u && a.password === password
    );
    if (!match) return { ok: false, error: "Incorrect username or password." };

    const publicUser = { username: match.username, name: match.name, role: match.role };
    const session = { user: publicUser, exp: Date.now() + SESSION_DAYS * 864e5 };
    if (remember) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setUser(publicUser);
    return { ok: true };
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
