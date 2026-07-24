import { useState } from "react";
import {
  Bot, Check, Database, LogOut, Moon, Palette, ReceiptText,
  ShieldCheck, Sun, Trash2, Wifi, WifiOff,
} from "lucide-react";
import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { ENGINEERING_AGENT_ID, QUOTATION_AGENT_ID } from "../lib/constants";

const APP_VERSION = "0.9.0";

/**
 * Workspace settings: appearance, the live assistants, connection/system
 * status, local data, and account. Reports what the app genuinely knows
 * (health, configured agent ids, theme) — it invents no account fields.
 */
export function SettingsPage({ user, health, sessionId, isDark, onToggleTheme, onLogout }) {
  const [cleared, setCleared] = useState(false);

  const online = health ? health.status === "ok" : false;

  const clearLocalData = () => {
    // Wipe cached conversations + session id; keep theme + auth session.
    localStorage.removeItem("vitech_convos");
    localStorage.removeItem("ats_session");
    setCleared(true);
    setTimeout(() => window.location.reload(), 700);
  };

  const agents = [
    { icon: Bot, name: "Engineering Agent", id: ENGINEERING_AGENT_ID, status: "Live" },
    { icon: ReceiptText, name: "Quotation Agent", id: QUOTATION_AGENT_ID, status: "Live" },
  ];

  const system = [
    { k: "Status", v: online ? "All services online" : "Backend unreachable" },
    { k: "Language model", v: health?.llm_model || "unknown" },
    { k: "Conversation memory", v: health?.memory || "unknown" },
    { k: "Documents indexed", v: health?.documents_indexed != null ? String(health.documents_indexed) : "—" },
  ];

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Settings</h1>
        <p>Appearance, assistants, connection and your account.</p>
      </header>

      <div className="dash-grid settings-grid">
        {/* Appearance */}
        <Card>
          <h2 className="card-h2"><Palette size={16} strokeWidth={1.9} /> Appearance</h2>
          <div className="set-row">
            <div className="set-row-t">
              <span className="set-row-title">Theme</span>
              <span className="set-row-sub">{isDark ? "Dark" : "Light"} mode is active.</span>
            </div>
            <Button variant="ghost" size="sm" icon={isDark ? Sun : Moon} onClick={onToggleTheme}>
              {isDark ? "Light mode" : "Dark mode"}
            </Button>
          </div>
        </Card>

        {/* Account */}
        <Card>
          <h2 className="card-h2"><ShieldCheck size={16} strokeWidth={1.9} /> Account</h2>
          <dl className="kv">
            <div className="kv-row"><dt>Signed in as</dt><dd>{user.name}</dd></div>
            <div className="kv-row"><dt>Role</dt><dd>{user.role}</dd></div>
            <div className="kv-row"><dt>Organisation</dt><dd>Vitech Enviro Systems</dd></div>
          </dl>
          <div className="btn-row">
            <Button variant="ghost" size="sm" icon={LogOut} onClick={onLogout} className="set-danger">
              Sign out
            </Button>
          </div>
        </Card>

        {/* Assistants */}
        <Card className="set-span">
          <h2 className="card-h2"><Bot size={16} strokeWidth={1.9} /> Assistants</h2>
          <ul className="set-agents" role="list">
            {agents.map((a) => (
              <li key={a.id} className="set-agent">
                <span className="set-agent-ic"><a.icon size={18} strokeWidth={1.8} /></span>
                <span className="set-agent-t">
                  <span className="set-agent-name">{a.name}</span>
                  <span className="set-agent-id mono">{a.id}</span>
                </span>
                <span className="badge ok">{a.status}</span>
              </li>
            ))}
          </ul>
          <p className="kv-note">
            Assistant ids are configured by your administrator (overridable via the
            <span className="mono"> VITE_*_AGENT_ID</span> environment variables).
          </p>
        </Card>

        {/* Connection / system */}
        <Card>
          <h2 className="card-h2">
            {online ? <Wifi size={16} strokeWidth={1.9} /> : <WifiOff size={16} strokeWidth={1.9} />}
            Connection
          </h2>
          <dl className="kv">
            {system.map((r) => (
              <div className="kv-row" key={r.k}>
                <dt>{r.k}</dt>
                <dd>{r.v}</dd>
              </div>
            ))}
            <div className="kv-row"><dt>Session id</dt><dd className="mono">{sessionId}</dd></div>
          </dl>
        </Card>

        {/* Data */}
        <Card>
          <h2 className="card-h2"><Database size={16} strokeWidth={1.9} /> Local data</h2>
          <p className="set-row-sub set-data-note">
            Saved conversations and the chat session are stored in this browser only.
            Clearing them cannot be undone.
          </p>
          <div className="btn-row">
            <Button
              variant="ghost"
              size="sm"
              icon={cleared ? Check : Trash2}
              onClick={clearLocalData}
              disabled={cleared}
              className="set-danger"
            >
              {cleared ? "Cleared — reloading…" : "Clear saved conversations"}
            </Button>
          </div>
        </Card>
      </div>

      <p className="set-version">Vitech AI Engineering Platform · v{APP_VERSION}</p>
    </div>
  );
}
