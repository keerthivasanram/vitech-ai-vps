import { BookOpen, Mail, MessageSquare, Phone } from "lucide-react";
import { Card } from "../common/Card";
import { Button } from "../common/Button";

/* Support routes. Swap these for the real desk details when they're confirmed. */
const CHANNELS = [
  {
    icon: Mail,
    title: "Email support",
    sub: "Best for a question with attachments — offers, drawings, specs.",
    action: "support@vitechenviro.com",
    href: "mailto:support@vitechenviro.com",
  },
  {
    icon: Phone,
    title: "Call the engineering desk",
    sub: "For an urgent quotation or a live client meeting.",
    action: "Contact your account manager",
    href: null,
  },
];

/** What the agent can and cannot be trusted with — the honest version. */
const FAQ = [
  {
    q: "Are the numbers the agent gives me reliable?",
    a: "Every dimension, capacity and price is computed by the deterministic engine from your historical offers and engineering rules — the model only writes the prose around them. Nothing numeric is invented.",
  },
  {
    q: "Why does the agent say it can't reach its tools?",
    a: "That means the backend is down, not that the model is confused. Check the status badge in the header: if it reads Offline, the API isn't reachable and the agent will improvise. Restart the stack before trusting any answer from that state.",
  },
  {
    q: "The agent is repeating strange JSON at me.",
    a: "Its conversation memory has been poisoned by an earlier reply. Start a New Chat — that rotates the session and gives it a clean context.",
  },
  {
    q: "Is every answer safe to send to a client?",
    a: "No. Every output is an engineer-reviewed draft, never an auto-send. Read it before it leaves the building.",
  },
];

/** Support channels, guidance and live system state. */
export function LiveHelpPage({ health, onOpenAgent }) {
  const online = health?.status === "ok";

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Live Help</h1>
        <p>Get help with the workspace, the agents, or a live client requirement.</p>
      </header>

      <Card className="help-hero">
        <div className="help-hero-t">
          <h2 className="help-hero-title">Ask the agent first</h2>
          <p className="help-hero-sub">
            Most engineering questions are answered instantly, grounded in Vitech's own
            project history.
          </p>
          <Button icon={MessageSquare} onClick={onOpenAgent}>Open the AI Agent</Button>
        </div>
      </Card>

      <h2 className="section-label">Contact a human</h2>
      <div className="help-channels">
        {CHANNELS.map((c) => (
          <Card key={c.title} className="help-channel">
            <span className="help-ic">
              <c.icon size={20} strokeWidth={1.8} aria-hidden="true" />
            </span>
            <h3 className="help-channel-title">{c.title}</h3>
            <p className="help-channel-sub">{c.sub}</p>
            {c.href ? (
              <a className="help-link" href={c.href}>{c.action}</a>
            ) : (
              <span className="help-muted">{c.action}</span>
            )}
          </Card>
        ))}

        <Card className="help-channel">
          <span className="help-ic">
            <BookOpen size={20} strokeWidth={1.8} aria-hidden="true" />
          </span>
          <h3 className="help-channel-title">System status</h3>
          <p className="help-channel-sub">
            Whether the agents can reach the deterministic engine right now.
          </p>
          <span className={`badge ${online ? "ok" : "warn"}`}>
            {online ? "All services online" : "Backend not reachable"}
          </span>
        </Card>
      </div>

      <h2 className="section-label">Common questions</h2>
      <div className="faq">
        {FAQ.map((f) => (
          <details className="faq-item" key={f.q}>
            <summary>{f.q}</summary>
            <p>{f.a}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
