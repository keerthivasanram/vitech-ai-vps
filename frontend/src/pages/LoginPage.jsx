import { useState } from "react";
import { Eye, EyeOff, Loader2, LogIn, Moon, Sun } from "lucide-react";
import { Logo } from "../components/Logo";
import { Button } from "../common/Button";

/**
 * Sign-in gate. Branded, theme-aware, keyboard-friendly.
 * Delegates credential checking to `onLogin` (see AuthProvider) and shows the
 * returned error inline. No account fields are invented.
 */
export function LoginPage({ onLogin, isDark, onToggleTheme }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    const res = await onLogin({ username, password, remember });
    setBusy(false);
    if (!res.ok) setError(res.error || "Sign-in failed.");
  };

  return (
    <div className="login-screen">
      <div className="login-bg" aria-hidden="true" />

      <button
        type="button"
        className="login-theme"
        onClick={onToggleTheme}
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      >
        {isDark ? <Sun size={18} strokeWidth={1.8} /> : <Moon size={18} strokeWidth={1.8} />}
      </button>

      <div className="login-card">
        <div className="login-brand">
          <Logo height={52} isDark={isDark} />
        </div>
        <h1 className="login-title">Sign in</h1>
        <p className="login-sub">Vitech AI Engineering Platform</p>

        <form className="login-form" onSubmit={submit} noValidate>
          <label className="login-field">
            <span className="login-label">Username</span>
            <input
              className="login-input"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
            />
          </label>

          <label className="login-field">
            <span className="login-label">Password</span>
            <span className="login-inputwrap">
              <input
                className="login-input"
                type={show ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
              <button
                type="button"
                className="login-eye"
                onClick={() => setShow((v) => !v)}
                aria-label={show ? "Hide password" : "Show password"}
                tabIndex={-1}
              >
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
          </label>

          <label className="login-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            <span>Keep me signed in</span>
          </label>

          {error && (
            <p className="login-error" role="alert">{error}</p>
          )}

          <Button
            type="submit"
            variant="primary"
            className="login-submit"
            icon={busy ? Loader2 : LogIn}
            disabled={busy || !username || !password}
          >
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="login-foot">
          Engineer-reviewed drafts only. Access is limited to authorised Vitech staff.
        </p>
      </div>
    </div>
  );
}
