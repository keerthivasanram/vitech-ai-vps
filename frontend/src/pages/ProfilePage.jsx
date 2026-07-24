import { LogOut, Moon, Shield, Sun } from "lucide-react";
import { Avatar } from "../common/Avatar";
import { Card } from "../common/Card";
import { Button } from "../common/Button";

/**
 * Signed-in user's profile.
 *
 * There is no auth backend yet, so this reports what the app genuinely knows —
 * the configured user, the live session id, the model actually answering, and
 * the local theme choice — rather than inventing account fields. It grows into
 * a real account page when the multi-user phase lands.
 */
export function ProfilePage({ user, health, sessionId, conversationCount, isDark, onToggleTheme, onLogout }) {
  const rows = [
    { k: "Name", v: user.name },
    { k: "Role", v: user.role },
    { k: "Organisation", v: "Vitech Enviro Systems" },
    { k: "Workspace", v: "Engineering AI" },
  ];

  const session = [
    { k: "Session id", v: sessionId, mono: true },
    { k: "Language model", v: health?.llm_model || "unknown" },
    { k: "Conversation memory", v: health?.memory || "unknown" },
    { k: "Saved conversations", v: String(conversationCount) },
  ];

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Profile</h1>
        <p>Your account and the current workspace session.</p>
      </header>

      <Card className="profile-head">
        <Avatar name={user.name} size={72} />
        <div className="profile-head-t">
          <h2 className="profile-name">{user.name}</h2>
          <p className="profile-role">{user.role} · Vitech Enviro Systems</p>
          <span className="badge ok profile-badge">
            <Shield size={12} strokeWidth={2} aria-hidden="true" />
            Signed in
          </span>
        </div>
      </Card>

      <div className="dash-grid profile-grid">
        <Card>
          <h2 className="card-h2">Account</h2>
          <dl className="kv">
            {rows.map((r) => (
              <div className="kv-row" key={r.k}>
                <dt>{r.k}</dt>
                <dd>{r.v}</dd>
              </div>
            ))}
          </dl>
          <p className="kv-note">
            Account details are configured by your administrator. Editing arrives with
            the multi-user phase.
          </p>
        </Card>

        <Card>
          <h2 className="card-h2">Session</h2>
          <dl className="kv">
            {session.map((r) => (
              <div className="kv-row" key={r.k}>
                <dt>{r.k}</dt>
                <dd className={r.mono ? "mono" : undefined}>{r.v}</dd>
              </div>
            ))}
          </dl>

          <h2 className="card-h2 kv-sep">Appearance</h2>
          <div className="btn-row">
            <Button
              variant="ghost"
              size="sm"
              icon={isDark ? Sun : Moon}
              onClick={onToggleTheme}
            >
              {isDark ? "Switch to light mode" : "Switch to dark mode"}
            </Button>
            {onLogout && (
              <Button variant="ghost" size="sm" icon={LogOut} onClick={onLogout} className="set-danger">
                Sign out
              </Button>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
