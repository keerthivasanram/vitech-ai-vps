import { memo, useEffect, useMemo, useState } from "react";
import { FileText, Grid2x2, Users, Wallet } from "lucide-react";
import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { catLabel, inrMaybe } from "../lib/format";

const Kpi = memo(function Kpi({ n, label, icon: Icon, tone = "" }) {
  return (
    <div className="kpi">
      <span className={`kpi-ic ${tone}`.trim()}>
        <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
      </span>
      <b>{n}</b>
      <span>{label}</span>
    </div>
  );
});

/** Live overview of the workspace. Every number is computed from the store. */
export function Dashboard({ setView }) {
  const [health, setHealth] = useState(null);
  const [offers, setOffers] = useState(null);
  const [agentUp, setAgentUp] = useState(null);

  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth({ status: "down" }));
    fetch("/api/offers").then((r) => r.json()).then(setOffers).catch(() => setOffers({ count: 0, offers: [] }));
    fetch("/flowise/api/v1/ping").then((r) => setAgentUp(r.ok)).catch(() => setAgentUp(false));
  }, []);

  const derived = useMemo(() => {
    const list = offers?.offers || [];
    const counts = {};
    list.forEach((o) => {
      const c = o.category || "other";
      counts[c] = (counts[c] || 0) + 1;
    });
    const cats = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return {
      list,
      cats,
      max: Math.max(...cats.map((c) => c[1]), 1),
      clients: new Set(list.map((o) => o.client).filter(Boolean)).size,
      priced: list.filter((o) => o.price_total != null).length,
      recent: list
        .filter((o) => o.date)
        .sort((a, b) => String(b.date).localeCompare(String(a.date)))
        .slice(0, 6),
    };
  }, [offers]);

  if (!offers) {
    return <div className="placeholder"><p>Loading workspace…</p></div>;
  }

  const backendOk = health?.status === "ok";
  const svc = [
    { name: "Backend API", ok: backendOk,
      detail: backendOk ? "Deterministic engine online" : "Not reachable — run start-all.sh" },
    { name: "AI Agents", ok: agentUp === true,
      detail: agentUp === null ? "Checking…" : agentUp ? "Engineering + Quotation live on Flowise" : "Flowise not reachable on :3000" },
    { name: "Language model", ok: !!health?.llm_model, detail: health?.llm_model || "unknown" },
    { name: "Knowledge index", ok: (health?.documents_indexed || 0) > 0,
      detail: `${health?.documents_indexed ?? 0} records in ChromaDB` },
  ];

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Dashboard</h1>
        <p>Live overview of the Vitech engineering workspace.</p>
      </header>

      <div className="kpis">
        <Kpi n={offers.count ?? derived.list.length} label="Offers indexed" icon={FileText} />
        <Kpi n={derived.clients} label="Clients" icon={Users} tone="blue" />
        <Kpi n={derived.cats.length} label="Equipment categories" icon={Grid2x2} tone="violet" />
        <Kpi n={derived.priced} label="Offers with pricing" icon={Wallet} tone="amber" />
      </div>

      <div className="dash-grid">
        {/* One measure across categories -> single-hue ranked bars */}
        <Card>
          <h2 className="card-h2">Offers by equipment category</h2>
          <div className="bars">
            {derived.cats.map(([c, n]) => (
              <div className="bar-row" key={c} title={`${catLabel(c)}: ${n} offer${n === 1 ? "" : "s"}`}>
                <span className="bar-label">{catLabel(c)}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(n / derived.max) * 100}%` }} />
                </div>
                <span className="bar-val">{n}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="card-h2">System health</h2>
          <ul className="svc">
            {svc.map((s) => (
              <li key={s.name}>
                <span className={`svc-dot ${s.ok ? "ok" : "bad"}`} aria-hidden="true" />
                <span className="svc-name">{s.name}</span>
                <span className="svc-state">{s.ok ? "OK" : "Down"}</span>
                <span className="svc-detail">{s.detail}</span>
              </li>
            ))}
          </ul>
          <div className="btn-row">
            <Button size="sm" onClick={() => setView("engineering")}>Open AI Agent</Button>
            <Button size="sm" variant="ghost" onClick={() => setView("quotation")}>
              Generate a quotation
            </Button>
          </div>
        </Card>

        <Card className="dash-wide">
          <h2 className="card-h2">Recent offers</h2>
          <table className="dtable">
            <thead>
              <tr>
                <th>Client</th><th>Category</th><th>Reference</th><th>Date</th>
                <th className="ta-r">Value</th>
              </tr>
            </thead>
            <tbody>
              {derived.recent.map((o) => (
                <tr key={o.id}>
                  <td>{o.client || "—"}</td>
                  <td><span className="badge soft">{catLabel(o.category)}</span></td>
                  <td className="mono">{o.ref || "—"}</td>
                  <td>{o.date || "—"}</td>
                  <td className="ta-r mono">{inrMaybe(o.price_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
