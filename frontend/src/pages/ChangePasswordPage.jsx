import { useState } from "react";
import { KeyRound, Loader2, Moon, ShieldAlert, Sun } from "lucide-react";
import { Logo } from "../components/Logo";
import { Button } from "../common/Button";

/**
 * Mandatory password change.
 *
 * Rendered INSTEAD of the application, not alongside it, whenever the server
 * says `must_change_password`. That is the point: an account still on its
 * issued password is a credential someone else may have seen — in a terminal,
 * a handover note, a screenshot — so it must not reach the engineering data.
 * A dismissible banner would make the protection optional, which is the same as
 * not having it.
 *
 * Reuses the sign-in screen's markup and classes exactly, so it reads as the
 * same product rather than a bolted-on form.
 */
export function ChangePasswordPage({ onSubmit, onLogout, isDark, onToggleTheme,
                                     username }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Mirrors the server's own minimum. Checking here saves a round trip; the
  // server still enforces it, because a browser-side rule protects nobody.
  const tooShort = next.length > 0 && next.length < 12;
  const mismatch = confirm.length > 0 && next !== confirm;
  const canSubmit = current && next.length >= 12 && next === confirm && !busy;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    const res = await onSubmit(current, next);
    setBusy(false);
    if (!res?.ok) setError(res?.error || "Could not change the password.");
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

        <div className="login-notice" role="status">
          <ShieldAlert size={15} strokeWidth={2} />
          <span>This account is still using its issued password.</span>
        </div>

        <h1 className="login-title">Set a new password</h1>
        <p className="login-sub">
          {username ? <>Signed in as <b>{username}</b>. </> : null}
          Changing it signs out every other session.
        </p>

        <form className="login-form" onSubmit={submit} noValidate>
          <label className="login-field">
            <span className="login-label">Current password</span>
            <input
              className="login-input"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </label>

          <label className="login-field">
            <span className="login-label">New password</span>
            <input
              className="login-input"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              placeholder="At least 12 characters"
            />
            {tooShort && (
              <span className="login-hint">Needs at least 12 characters.</span>
            )}
          </label>

          <label className="login-field">
            <span className="login-label">Confirm new password</span>
            <input
              className="login-input"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {mismatch && (
              <span className="login-hint">The two entries do not match.</span>
            )}
          </label>

          {error && <div className="login-error" role="alert">{error}</div>}

          <Button type="submit" className="login-submit" disabled={!canSubmit}>
            {busy
              ? <><Loader2 size={16} strokeWidth={2} className="spin" /> Saving…</>
              : <><KeyRound size={16} strokeWidth={2} /> Set password and continue</>}
          </Button>
        </form>

        <p className="login-foot">
          Not you?{" "}
          <button type="button" className="login-linkbtn" onClick={onLogout}>
            Sign out
          </button>
        </p>
      </div>
    </div>
  );
}
