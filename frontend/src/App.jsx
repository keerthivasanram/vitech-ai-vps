import { useEffect, useRef, useState } from "react";

const SUGGESTED = [
  "Generate a wet scrubber spec for 800 CFM, 750 mm tower, 4 nos.",
  "Generate a specification for a 10 x 6 powder paint booth.",
  "What did C2C Engineering order?",
  "Which clients are in the database?",
  "How does a wet scrubber remove particulates from air?",
  "Convert 800 CFM to CMH.",
];

const THINK_LABELS = [
  "Thinking",
  "Understanding your request",
  "Searching the knowledge base",
  "Reasoning over past projects",
  "Composing the answer",
];

const fmtTime = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const newId  = () => Math.random().toString(36).slice(2, 14);

// The Engineering Agent chatflow in Flowise. Override with VITE_ENGINEERING_AGENT_ID
// in an .env if the chatflow id changes.
const ENGINEERING_AGENT_ID =
  import.meta.env.VITE_ENGINEERING_AGENT_ID || "c4bfba16-aeb0-4c1b-840e-21b474639a8d";
const AGENT_URL = `/flowise/api/v1/prediction/${ENGINEERING_AGENT_ID}`;

function HexIcon({ size = 20, className = "" }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M12 2L21.66 7.5V16.5L12 22L2.34 16.5V7.5L12 2Z" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  );
}

export default function App() {
  const [health, setHealth]     = useState(null);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("ats_session") || newId());
  const [messages, setMessages] = useState([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [agent, setAgent]       = useState("Auto (Hybrid Routing)");
  const [view, setView]         = useState("engineering");
  const endRef = useRef(null);
  useEffect(() => { localStorage.setItem("ats_session", sessionId); }, [sessionId]);
  useEffect(() => {
    fetch("/api/health").then(r => r.json()).then(setHealth).catch(() => {});
  }, []);
  // Conversation memory now lives in Flowise (keyed by chatId=sessionId); the UI
  // starts fresh on reload. "New chat" rotates the sessionId for a clean context.
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  async function send(q) {
    const text = (q ?? input).trim();
    if (!text || loading) return;
    setInput("");
    setMessages(m => [...m, { role: "user", text, time: fmtTime() }]);
    setLoading(true);

    // add an empty assistant placeholder we fill as tokens stream in
    let idx = 0;
    setMessages(m => { idx = m.length; return [...m, { role: "assistant", text: "", streaming: true }]; });
    const patch = (p) => setMessages(m => m.map((x, i) => (i === idx ? { ...x, ...p } : x)));
    // Flowise keys conversation memory by chatId — reuse the session so the
    // Engineering Agent remembers context across turns.
    const body = JSON.stringify({ question: text, streaming: true, chatId: sessionId });

    try {
      const resp = await fetch(AGENT_URL, {
        method: "POST", headers: { "Content-Type": "application/json" }, body,
      });
      if (!resp.ok || !resp.body) throw new Error("no stream");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "", acc = "", tools = [];
      // coalesce tokens: render at most once per animation frame, not per token
      let raf = 0;
      const flush = () => { raf = 0; patch({ text: acc }); };
      const schedule = () => { if (!raf) raf = requestAnimationFrame(flush); };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        // Flowise SSE record: "message:\ndata:{"event":..,"data":..}", split on blank line
        while ((nl = buf.indexOf("\n\n")) >= 0) {
          const raw = buf.slice(0, nl); buf = buf.slice(nl + 2);
          const dataLine = raw.split("\n").find(l => l.startsWith("data:"));
          if (!dataLine) continue;
          const json = dataLine.replace(/^data:\s?/, "").trim();
          if (!json || json === "[DONE]") continue;
          let evt; try { evt = JSON.parse(json); } catch { continue; }
          if (evt.event === "token" && evt.data) {
            acc += evt.data;
            schedule();
          } else if (evt.event === "usedTools" && Array.isArray(evt.data)) {
            tools = evt.data.map(t => t.tool).filter(Boolean);
          } else if (evt.event === "end") {
            if (raf) { cancelAnimationFrame(raf); raf = 0; }
            patch({ text: acc, data: { usedTools: tools }, streaming: false, time: fmtTime() });
          }
        }
      }
      if (raf) cancelAnimationFrame(raf);
      if (!acc) throw new Error("empty stream");
      patch({ text: acc, data: { usedTools: tools }, streaming: false, time: fmtTime() });
    } catch {
      // fall back to a non-streaming prediction call
      try {
        const resp = await fetch(AGENT_URL, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: text, chatId: sessionId }),
        });
        if (!resp.ok) throw new Error("bad status");
        const data = await resp.json();
        const answer = data.text ?? data.answer ?? "(no response)";
        patch({ text: answer, data: { usedTools: (data.usedTools || []).map(t => t.tool) }, streaming: false, time: fmtTime() });
      } catch {
        patch({ text: "Engineering Agent not reachable — is Flowise running on :3000?", streaming: false });
      }
    } finally {
      setLoading(false);
    }
  }

  function newChat() {
    // A fresh sessionId gives the Flowise agent a clean memory context.
    setSessionId(newId());
    setMessages([]);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <HexIcon size={22} className="logo-icon" />
          <span className="brand-name">ATS Engineering Assistant</span>
        </div>
        <div className="status">
          {health && (
            <>
              <span className="pill pill-ic"><UsersIcon />{health.documents_indexed} offers</span>
              <span className="pill">{health.llm_model}</span>
              <span className={`pill${health.memory === "redis" ? " ok" : ""}`}>memory: {health.memory}</span>
            </>
          )}
          <button className="newchat" onClick={newChat}>+ New chat</button>
        </div>
      </header>

      <div className="body">
        <Sidebar view={view} setView={setView} />
        <div className="viewport">
          {view === "dashboard" ? <Dashboard setView={setView} />
            : view === "knowledge" ? <KnowledgeBase />
            : view === "upload" ? <UploadPage />
            : view === "quotation" ? <QuotationPage />
            : view === "drawing" ? <AgentPlaceholder id={view} />
            : (
      <main className="chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="empty">
              <div className="hero-icon"><HexIcon size={52} className="hero-hex" /></div>
              <h1>How can I help?</h1>
              <p>Generate a technical specification, look up a stored client offer,<br />or ask a general engineering question.</p>
              <div className="chips">
                {SUGGESTED.map(s => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="row user">
                <div className="user-side">
                  <div className="bubble user"><Answer text={m.text} /></div>
                  {m.time && <div className="msg-time">{m.time} <span className="tick">&#10003;</span></div>}
                </div>
                <div className="user-circle">U</div>
              </div>
            ) : (
              <div key={i} className="row assistant">
                <div className={`ast-circle${m.streaming && !m.text ? " pulsing" : ""}`}>
                  <HexIcon size={16} className="ast-hex" />
                </div>
                <div className="ast-content">
                  {m.data
                    ? <AssistantBody data={m.data} />
                    : m.streaming && !m.text
                      ? <Thinking />
                      : <Answer text={m.text} streaming={m.streaming} />}
                </div>
              </div>
            )
          )}
          <div ref={endRef} />
        </div>

        <div className="composer">
          <div className="composer-box">
            <input
              value={input}
              placeholder="Message the assistant..."
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && send()}
            />
            <div className="composer-foot">
              <div className="cfoot-left">
                <button className="ci" title="Attach">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
                  </svg>
                </button>
                <button className="ci" title="Image">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                  </svg>
                </button>
                <button className="ci" title="Code">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                  </svg>
                </button>
                <AgentSelector agent={agent} setAgent={setAgent} />
              </div>
              <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
              </button>
            </div>
          </div>
          <p className="disclaimer">AI responses may contain inaccuracies. Please verify critical information.</p>
        </div>
      </main>
              )}
        </div>
      </div>
    </div>
  );
}

/* ---- Multi-agent shell ---- */
const NAV = [
  { id: "dashboard",   name: "Dashboard",         desc: "Workspace overview",  status: "live", group: "Workspace" },
  { id: "engineering", name: "Engineering Agent", desc: "Specs & knowledge",   status: "live", group: "Agents" },
  { id: "quotation",   name: "Quotation Agent",   desc: "Budgetary quotes",    status: "live", group: "Agents" },
  { id: "drawing",     name: "Drawing Agent",     desc: "2D GA drawings",      status: "soon", group: "Agents" },
  { id: "knowledge",   name: "Knowledge Base",    desc: "Extracted offer data", status: "live", group: "Data" },
  { id: "upload",      name: "Upload & Extract",  desc: "Add offer / CAD files", status: "live", group: "Data" },
];

function Sidebar({ view, setView }) {
  const groups = [...new Set(NAV.map(n => n.group))];
  return (
    <aside className="sidebar">
      {groups.map(g => (
        <div key={g}>
          <div className="side-label">{g}</div>
          {NAV.filter(n => n.group === g).map(n => (
            <button key={n.id} className={`side-item${view === n.id ? " active" : ""}`}
                    onClick={() => setView(n.id)}>
              <span className="side-name">{n.name}</span>
              <span className="side-desc">{n.desc}</span>
              {n.status === "soon" && <span className="side-soon">soon</span>}
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}

function AgentPlaceholder({ id }) {
  const n = NAV.find(x => x.id === id) || {};
  return (
    <div className="placeholder">
      <div className="hero-icon"><HexIcon size={48} className="hero-hex" /></div>
      <h1>{n.name}</h1>
      <p>{n.desc} — on the roadmap.</p>
      <p className="ph-note">This agent will run on the same deterministic engine and be
        orchestrated by the Supervisor Agent. Coming in a later phase.</p>
    </div>
  );
}

const catLabel = c => (c || "other").replace(/_/g, " ").replace(/\b\w/g, m => m.toUpperCase());
const inrMaybe = n => (n == null ? "—" : "₹ " + Number(n).toLocaleString("en-IN"));

function Dashboard({ setView }) {
  const [health, setHealth] = useState(null);
  const [offers, setOffers] = useState(null);
  const [agentUp, setAgentUp] = useState(null);

  useEffect(() => {
    fetch("/api/health").then(r => r.json()).then(setHealth).catch(() => setHealth({ status: "down" }));
    fetch("/api/offers").then(r => r.json()).then(setOffers).catch(() => setOffers({ count: 0, offers: [] }));
    fetch("/flowise/api/v1/ping").then(r => setAgentUp(r.ok)).catch(() => setAgentUp(false));
  }, []);

  if (!offers) return <div className="dash"><p className="dash-load">Loading workspace…</p></div>;

  const list    = offers.offers || [];
  const clients = new Set(list.map(o => o.client).filter(Boolean)).size;
  const priced  = list.filter(o => o.price_total != null).length;

  const counts = {};
  list.forEach(o => { const c = o.category || "other"; counts[c] = (counts[c] || 0) + 1; });
  const cats = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max  = Math.max(...cats.map(c => c[1]), 1);

  const recent = list.filter(o => o.date)
    .sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 6);

  const backendOk = health?.status === "ok";
  const svc = [
    { name: "Backend API",       ok: backendOk,      detail: backendOk ? "Deterministic engine online" : "Not reachable — run start-all.sh" },
    { name: "Engineering Agent", ok: agentUp === true, detail: agentUp === null ? "Checking…" : agentUp ? "Flowise reachable" : "Flowise not reachable on :3000" },
    { name: "Language model",    ok: !!health?.llm_model, detail: health?.llm_model || "unknown" },
    { name: "Knowledge index",   ok: (health?.documents_indexed || 0) > 0, detail: `${health?.documents_indexed ?? 0} records in ChromaDB` },
  ];

  return (
    <div className="dash">
      <div className="dash-head">
        <h1>Dashboard</h1>
        <p>Live overview of the Vitech engineering workspace.</p>
      </div>

      {/* Headline numbers — stat tiles, not a chart */}
      <div className="dash-kpis">
        <Kpi n={offers.count ?? list.length} l="Offers indexed" />
        <Kpi n={clients}                     l="Clients" />
        <Kpi n={cats.length}                 l="Equipment categories" />
        <Kpi n={priced}                      l="Offers with pricing" />
      </div>

      <div className="dash-grid">
        {/* One measure across categories -> single-hue ranked bars */}
        <section className="dash-card">
          <h2>Offers by equipment category</h2>
          <div className="bars">
            {cats.map(([c, n]) => (
              <div className="bar-row" key={c} title={`${catLabel(c)}: ${n} offer${n === 1 ? "" : "s"}`}>
                <span className="bar-label">{catLabel(c)}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
                </div>
                <span className="bar-val">{n}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="dash-card">
          <h2>System health</h2>
          <ul className="svc">
            {svc.map(s => (
              <li key={s.name}>
                <span className={`dot ${s.ok ? "dot-ok" : "dot-bad"}`} aria-hidden="true" />
                <span className="svc-name">{s.name}</span>
                <span className="svc-state">{s.ok ? "OK" : "Down"}</span>
                <span className="svc-detail">{s.detail}</span>
              </li>
            ))}
          </ul>
          <div className="dash-actions">
            <button className="ap-btn" onClick={() => setView("engineering")}>Open Engineering Chat</button>
            <button className="dash-btn2" onClick={() => setView("quotation")}>Generate a quotation</button>
          </div>
        </section>

        <section className="dash-card dash-wide">
          <h2>Recent offers</h2>
          <table className="dash-table">
            <thead>
              <tr><th>Client</th><th>Category</th><th>Reference</th><th>Date</th><th className="ta-r">Value</th></tr>
            </thead>
            <tbody>
              {recent.map(o => (
                <tr key={o.id}>
                  <td>{o.client || "—"}</td>
                  <td><span className="pill">{catLabel(o.category)}</span></td>
                  <td className="mono">{o.ref || "—"}</td>
                  <td>{o.date || "—"}</td>
                  <td className="ta-r mono">{inrMaybe(o.price_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}

function Kpi({ n, l }) {
  return <div className="kpi"><b>{n}</b><span>{l}</span></div>;
}

function KnowledgeBase() {
  const [data, setData] = useState(null);
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null);      // full record of the opened file
  useEffect(() => {
    fetch("/api/offers").then(r => r.json()).then(setData).catch(() => setData({ count: 0, offers: [] }));
  }, []);
  if (!data) return <div className="placeholder"><p>Loading knowledge base…</p></div>;

  const cats = ["all", ...Array.from(new Set(data.offers.map(o => o.category))).sort()];
  const term = q.trim().toLowerCase();
  const rows = data.offers.filter(o =>
    (cat === "all" || o.category === cat) &&
    (!term || `${o.id} ${o.client} ${o.ref}`.toLowerCase().includes(term)));
  const open = id => fetch(`/api/offers/${id}`).then(r => r.json()).then(setSel).catch(() => {});

  return (
    <div className="kb">
      <div className="kb-head">
        <h1>Knowledge Base</h1>
        <p>{data.count} offer files extracted into the platform — click any file to see exactly what was captured.</p>
      </div>
      <div className="kb-filters">
        <select value={cat} onChange={e => setCat(e.target.value)}>
          {cats.map(c => <option key={c} value={c}>{c === "all" ? "All types" : catLabel(c)}</option>)}
        </select>
        <input placeholder="Search client / id / ref…" value={q} onChange={e => setQ(e.target.value)} />
        <span className="kb-count">{rows.length} shown</span>
      </div>
      <div className="kb-tablewrap">
        <table className="kb-table">
          <thead><tr>
            <th>ID</th><th>Type</th><th>Client</th><th>Ref</th><th>Date</th>
            <th>Fields</th><th>Price</th><th>Source file</th>
          </tr></thead>
          <tbody>
            {rows.map(o => (
              <tr key={o.id} className="kb-row" onClick={() => open(o.id)}>
                <td className="mono">{o.id}</td>
                <td>{catLabel(o.category)}</td>
                <td>{o.client}</td>
                <td className="mono">{o.ref}</td>
                <td>{o.date}</td>
                <td>{o.n_given}+{o.n_tech}</td>
                <td>{inrMaybe(o.price_total)}</td>
                <td className="kb-src" title={o.source_file}>{o.source_file}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sel && <OfferDrawer rec={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

function _fields(obj) {
  const fmt = v => (v && typeof v === "object")
    ? Object.entries(v).map(([k, x]) => `${k}: ${x}`).join("; ") : String(v);
  return Object.entries(obj || {}).map(([k, v]) => ({ k: k.replace(/_/g, " "), v: fmt(v) }));
}

function OfferDrawer({ rec, onClose }) {
  const ps = rec.price_schedule || {};
  const priceItems = Object.entries(ps).filter(([k]) => k !== "currency");
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="drawer-id">{rec.id}</div>
            <div className="drawer-client">{rec.client}</div>
          </div>
          <button className="drawer-x" onClick={onClose}>×</button>
        </div>
        <div className="drawer-meta">
          {rec.source_file && <span>📄 {rec.source_file}</span>}
          {rec.ref && <span>Ref: {rec.ref}</span>}
          {rec.date && <span>{rec.date}</span>}
        </div>

        <div className="drawer-sec-t">Given data (requirement)</div>
        <div className="drawer-grid">
          {_fields(rec.given_data).map((f, i) => (
            <div className="dg-row" key={i}><span>{f.k}</span><b>{f.v}</b></div>
          ))}
        </div>

        <div className="drawer-sec-t">Technical details (engineered solution)</div>
        <div className="drawer-grid">
          {_fields(rec.technical_details).map((f, i) => (
            <div className="dg-row" key={i}><span>{f.k}</span><b>{f.v}</b></div>
          ))}
        </div>

        {priceItems.length > 0 && (
          <>
            <div className="drawer-sec-t">Price schedule</div>
            <div className="drawer-grid">
              {priceItems.map(([k, v], i) => (
                <div className="dg-row" key={i}><span>{k.replace(/_/g, " ")}</span>
                  <b>{typeof v === "number" ? inrMaybe(v) : String(v)}</b></div>
              ))}
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function QuotationPage() {
  const [req, setReq] = useState("");
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const examples = [
    "wet scrubber 800 cfm 750mm tower 4 nos",
    "paint booth 10 x 6 powder",
    "dust collector 12000 cmh",
  ];
  async function gen(text) {
    const question = (text ?? req).trim();
    if (!question || loading) return;
    setReq(question); setLoading(true); setErr(""); setQuote(null);
    try {
      const r = await fetch("/api/tools/quote", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const d = await r.json();
      if (d.ok) setQuote(d); else setErr(d.message || "Could not generate a quotation.");
    } catch { setErr("Backend not reachable (API on :8000?)."); }
    finally { setLoading(false); }
  }
  return (
    <div className="agentpage">
      <div className="ap-head">
        <h1>Quotation Agent</h1>
        <p>Describe the requirement — the agent builds a <b>budgetary quotation</b> from your historical offers.
          Every number is deterministic; the price cites the projects it was scaled from.</p>
      </div>
      <div className="ap-form">
        <input value={req} placeholder="e.g. wet scrubber 800 cfm 750mm tower 4 nos"
          onChange={e => setReq(e.target.value)} onKeyDown={e => e.key === "Enter" && gen()} />
        <button className="ap-btn" onClick={() => gen()} disabled={loading || !req.trim()}>
          {loading ? "Generating…" : "Generate quotation"}</button>
      </div>
      <div className="ap-examples">
        {examples.map(x => <button key={x} className="chip" onClick={() => gen(x)}>{x}</button>)}
      </div>
      {err && <div className="ap-err">{err}</div>}
      {quote && <div className="ap-result"><QuotationCard q={quote} /></div>}
    </div>
  );
}

function UploadPage() {
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { refresh(); }, []);
  function refresh() {
    fetch("/api/uploads").then(r => r.json()).then(d => setFiles(d.files || [])).catch(() => {});
  }
  async function upload(list) {
    setBusy(true);
    for (const f of list) {
      const fd = new FormData(); fd.append("file", f);
      try { await fetch("/api/uploads", { method: "POST", body: fd }); } catch { /* skip */ }
    }
    setBusy(false); refresh();
  }
  const kb = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const STEPS = ["Upload", "Extract (OCR / parse)", "Engineer review", "Into Knowledge Base"];

  return (
    <div className="agentpage">
      <div className="ap-head">
        <h1>Upload &amp; Extract</h1>
        <p>Add offer PDFs and CAD drawings. Files are stored now; <b>automatic extraction into the
          Knowledge Base is the next phase</b> — uploads are queued for it.</p>
      </div>

      <label className={`dropzone${drag ? " over" : ""}`}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files?.length) upload(e.dataTransfer.files); }}>
        <input type="file" multiple hidden
          onChange={e => e.target.files?.length && upload(e.target.files)} />
        <div className="dz-ic">⬆</div>
        <div className="dz-t">{busy ? "Uploading…" : "Drag files here, or click to browse"}</div>
        <div className="dz-s">PDF · DXF · DWG · images</div>
      </label>

      <div className="pipeline">
        {STEPS.map((s, i) => (
          <div key={s} className={`pl-step${i === 0 ? " done" : " soon"}`}>
            <span className="pl-n">{i + 1}</span><span className="pl-lbl">{s}</span>
            {i < STEPS.length - 1 && <span className="pl-arrow">→</span>}
          </div>
        ))}
      </div>
      <p className="pl-note">Steps 2–4 arrive with the data-extraction pipeline (PDF parsing + CAD OCR →
        engineer review → normalized database).</p>

      {files.length > 0 && (
        <div className="up-list">
          <div className="up-list-h">Uploaded files ({files.length})</div>
          {files.map(f => (
            <div className="up-row" key={f.filename}>
              <span className="up-name" title={f.filename}>{f.filename}</span>
              <span className="up-kind">{f.kind}</span>
              <span className="up-size">{kb(f.size)}</span>
              <span className="up-status">queued for extraction</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---- Agent Selector Component ---- */
function AgentSelector({ agent, setAgent }) {
  const [open, setOpen] = useState(false);
  const options = ["Auto (Hybrid Routing)", "ATS Quotation Engineer", "Consulting Engineer", "Ollama (llama3.1)"];
  
  return (
    <div className="agent-selector">
      <button className="agent-btn" onClick={() => setOpen(!open)} title="Select Agent/Model">
        <span className="agent-label">{agent}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      {open && (
        <>
          <div className="agent-backdrop" onClick={() => setOpen(false)} />
          <div className="agent-dropdown">
            {options.map(opt => (
              <div 
                key={opt} 
                className={`agent-option ${opt === agent ? 'active' : ''}`} 
                onClick={() => { setAgent(opt); setOpen(false); }}
              >
                {opt}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ---- Thinking indicator (Claude-style shimmer) ---- */
function Thinking() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI(v => Math.min(v + 1, THINK_LABELS.length - 1)), 2000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="thinking">
      <span className="shimmer">{THINK_LABELS[i]}</span>
    </div>
  );
}

/* ---- AssistantBody ---- */
function AssistantBody({ data }) {
  // Greetings / small talk: just the reply, no badges or sources.
  if (data.small_talk) return <Answer text={data.answer} />;
  return (
    <>
      <div className="badge-row">
        {data.spec_mode === "knowledge" && <span className="badge gen">Consulting Engineer</span>}
        {data.spec_mode === "data" && <span className="badge cat">ATS Quotation Engineer</span>}
        {!data.spec_mode && data.grounded === false && <span className="badge gen">General knowledge</span>}
        {!data.spec_mode && data.grounded && data.category_label && <span className="badge cat">{data.category_label}</span>}
        {data.spec_mode && data.category_label && <span className="badge info">{data.category_label}</span>}
        {data.intent && <span className="badge info">{data.intent}</span>}
        {data.deterministic && <span className="badge ok">Deterministic</span>}
        {data.llm && <span className="badge soft">via {data.llm}</span>}
      </div>
      <Answer text={data.answer} />
      {data.quotation && <QuotationCard q={data.quotation} />}
      {data.grounded && data.sources?.length > 0 && (
        <div className="sources">
          <span className="sources-title">Sources</span>
          {data.sources.map(s => (
            <span key={s.id} className={`source ${s.type}`}>{s.source_file || s.id}</span>
          ))}
        </div>
      )}
      <div className="msg-actions"><CopyButton text={data.answer} /></div>
    </>
  );
}

/* ---- Analysis panel cards ---- */
function Card({ icon, title, right, children, accent }) {
  return (
    <div className={`pcard${accent ? " accent" : ""}`}>
      <div className="pcard-h">
        <span className="pic">{icon}</span>
        <span className="pt">{title}</span>
        {right && <span className="pcard-r">{right}</span>}
      </div>
      <div className="pcard-b">{children}</div>
    </div>
  );
}

function ConfidenceRing({ pct, label }) {
  const cls = (label || "").toLowerCase();
  return (
    <div className={`ring ring-${cls}`} style={{ "--p": pct }}>
      <div className="ring-in"><b>{pct}%</b><span>{label}</span></div>
    </div>
  );
}

const inr = n => "₹ " + Number(n || 0).toLocaleString("en-IN");

async function downloadQuotePdf(q) {
  try {
    const resp = await fetch("/api/quotation/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(q),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(q.ref || "quotation").replace(/\s+/g, "_")}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch { /* offline / backend down — no-op */ }
}

function QuotationCard({ q }) {
  if (!q) return null;
  const p = q.price || {};
  const scope = (q.scope || []).filter(s => s.origin !== "given");
  return (
    <div className="quote">
      <div className="quote-top">
        <div>
          <div className="quote-name">{q.headline}</div>
          <div className="quote-ref">{q.ref} · {q.date}</div>
        </div>
        <div className="quote-top-r">
          <span className="badge warn">DRAFT</span>
          <button className="pdf-btn" onClick={() => downloadQuotePdf(q)}>Download PDF</button>
        </div>
      </div>

      <div className="quote-price">
        <div className="qp-l">
          <div className="qp-amt">{inr(p.amount)}</div>
          <div className="qp-sub">
            budgetary range {inr(p.range_low)} – {inr(p.range_high)}
            {p.qty > 1 && <> · {inr(p.unit_price)} × {p.qty} units</>}
          </div>
        </div>
        <ConfidenceRing pct={q.confidence_pct} label={q.confidence_label} />
      </div>

      {q.given_data?.length > 0 && (
        <div className="quote-req">
          {q.given_data.map((g, i) => (
            <span className="req-chip" key={i}><b>{g.label}</b> {g.value}</span>
          ))}
        </div>
      )}

      {scope.length > 0 && (
        <div className="quote-sec">
          <div className="quote-sec-t">Scope of supply</div>
          <div className="scope">
            {scope.map((s, i) => (
              <div className="scope-row" key={i}>
                <span className="scope-item">{s.item}</span>
                <span className="scope-spec">{s.spec}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="quote-sec">
        <div className="quote-sec-t">Commercial terms</div>
        <div className="terms">
          {(q.terms || []).map((t, i) => (
            <div className="term-row" key={i}><b>{t[0]}</b> — {t[1]}</div>
          ))}
        </div>
      </div>

      <div className="quote-foot">
        {q.basis_offers?.length > 0 && <span>Priced from {q.basis_offers.join(", ")}</span>}
        <span className="quote-note">{q.note}</span>
      </div>
    </div>
  );
}

function AnalysisPanel({ analysis }) {
  const { given_data, similar_offers, exact_match, nearest_match, match,
    technical_details, criteria, missing_inputs, confidence_pct, confidence_label,
    knowledge_used, knowledge_contribution, decision_origin, assumptions,
    confidence_factors, confidence_notes } = analysis;
  if (!technical_details?.length) return null;
  const chosen = exact_match || nearest_match;

  return (
    <div className="analysis">
      {given_data?.length > 0 && (
        <Card icon="📋" title="Requirement">
          <div className="kvgrid">
            {given_data.map((g, i) => (
              <div key={i} className="kvtile">
                <span className="kvl">{g.label}</span>
                <span className="kvv">{g.value}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {match && (
        <Card icon="🎯" title="Engineering match" right={<b className="big">{match.overall}%</b>}>
          <div className="sub">closest design <b>{chosen}</b></div>
          <div className="match-bars">
            {match.driver   != null && <MatchBar label={match.driver_label}       v={match.driver} />}
            {match.dimension!= null && <MatchBar label="Dimension"               v={match.dimension} />}
            {match.process  != null && <MatchBar label="Process"                  v={match.process} />}
            {match.historical!= null && <MatchBar label="Historical similarity"   v={match.historical} muted />}
          </div>
        </Card>
      )}

      {decision_origin?.length > 0 && (
        <Card icon="🧩" title="Decision origin">
          <div className="chiprow">
            {decision_origin.map(r => (
              <span key={r.type}
                className={`dchip dt-${r.type.toLowerCase().replace(/ /g, "-")}${r.count === 0 ? " off" : ""}`}>
                <b>{r.count}</b> {r.type}
              </span>
            ))}
          </div>
        </Card>
      )}

      {similar_offers?.length > 0 && (
        <Card icon="📑" title="Alternatives considered">
          <table className="tbl">
            <thead><tr><th>Offer</th><th>Difference</th><th>Source</th></tr></thead>
            <tbody>
              {similar_offers.map(p => (
                <tr key={p.id} className={p.id === chosen ? "chosen" : ""}>
                  <td>{p.id}{p.id === chosen ? " ◄" : ""}</td>
                  <td>{p.difference}</td>
                  <td className="src">{p.source_file || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Card icon="🛠️" title="Engineering decisions">
        <table className="tbl spec">
          <thead><tr><th>Decision</th><th>Value</th><th>Source</th><th>Reason</th></tr></thead>
          <tbody>
            {technical_details.map((it, i) => (
              <tr key={i}>
                <td>{it.label}</td>
                <td className="val">{it.value}</td>
                <td><span className={`origin ${it.origin}`}>{it.origin_label}{it.support ? ` (${it.support})` : ""}</span></td>
                <td className="reason">{it.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {assumptions?.length > 0 && (
        <Card icon="⚠️" title="Assumptions" accent>
          {assumptions.map((a, i) => (
            <div key={i} className="assume"><b>{a.label}: {a.value}</b> — {a.reason}</div>
          ))}
        </Card>
      )}

      {knowledge_used && (
        <Card icon="🧠" title="Knowledge reasoning summary">
          <div className="stats">
            <Stat n={knowledge_used.historical_projects} l="projects" />
            <Stat n={knowledge_used.rules}               l="rules" />
            <Stat n={knowledge_used.standards}           l="standards" />
            <Stat n={knowledge_used.components_compared} l="components" />
            <Stat n={knowledge_used.decisions}           l="decisions" />
          </div>
          {knowledge_contribution?.length > 0 && (
            <>
              <div className="sub" style={{ marginTop: 12 }}>Knowledge contribution</div>
              <div className="contrib">
                {knowledge_contribution.map((c, i) => (
                  <div key={i} className="cbar">
                    <span className="clabel">{c.source}</span>
                    <span className="ctrack"><span className="cfill" style={{ width: `${c.pct}%` }} /></span>
                    <span className="cval">{c.pct}%</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      )}

      <Card icon="📊" title="Confidence" right={<ConfidenceRing pct={confidence_pct} label={confidence_label} />}>
        {confidence_factors?.length > 0 && (
          <div className="factors">
            {confidence_factors.map((f, i) => (
              <div key={i} className="factor"><span className="fl">{f.label}</span><b>{f.value}</b></div>
            ))}
          </div>
        )}
        {criteria?.map((c, i) => (
          <div key={i} className={`crit ${c.ok ? "ok" : "no"}`}>{c.ok ? "✓" : "✗"} {c.label}</div>
        ))}
        {confidence_notes?.length > 0 && (
          <div className="conf-notes">
            <span className="cn-title">Confidence reduced because:</span>
            {confidence_notes.map((n, i) => <div key={i} className="crit missing">– {n}</div>)}
          </div>
        )}
        {missing_inputs?.length > 0 && (
          <div className="crit missing">Missing inputs: {missing_inputs.join(", ")}</div>
        )}
      </Card>
    </div>
  );
}

function Stat({ n, l }) {
  return <div className="stat"><b>{n}</b><span>{l}</span></div>;
}

function MatchBar({ label, v, muted }) {
  return (
    <div className="mbar">
      <span className="mlabel">{label}</span>
      <span className="mtrack"><span className={`mfill${muted ? " muted" : ""}`} style={{ width: `${v}%` }} /></span>
      <span className="mval">{v}%</span>
    </div>
  );
}

const isTableRow = (s) => /^\s*\|.*\|\s*$/.test(s);
const isTableSep = (s) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.includes("-");
const cells = (s) => s.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

function Answer({ text, streaming }) {
  if (!text) return null;
  const lines = text.split("\n");
  const out = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].replace(/\s+$/, "").trim();

    // markdown table: header row + separator row + body rows
    if (isTableRow(lines[i]) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(lines[i]);
      const rows = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) { rows.push(cells(lines[i])); i++; }
      i--;
      out.push(
        <div key={key++} className="tbl-wrap">
          <table className="mdtable">
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{head.map((_, ci) => <td key={ci}>{inline(r[ci] ?? "")}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>);
      continue;
    }

    if (!t) { out.push(<div key={key++} className="gap" />); continue; }

    const h = t.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      out.push(<div key={key++} className={`h h${h[1].length}`}>{inline(h[2])}</div>);
      continue;
    }
    if (t.startsWith(">")) {
      out.push(<blockquote key={key++}>{inline(t.slice(1).trim())}</blockquote>);
      continue;
    }
    const ol = t.match(/^(\d+)[.)]\s+(.*)$/);
    if (ol) {
      out.push(
        <div key={key++} className="li ol">
          <span className="marker">{ol[1]}.</span>
          <span className="li-body">{inline(ol[2])}</span>
        </div>);
      continue;
    }
    const ul = t.match(/^[•\-*]\s+(.*)$/);
    if (ul) {
      out.push(
        <div key={key++} className="li ul">
          <span className="marker">•</span>
          <span className="li-body">{inline(ul[1])}</span>
        </div>);
      continue;
    }
    out.push(<p key={key++} className="para">{inline(t)}</p>);
  }
  return (
    <div className="answer">
      {out}
      {streaming && <span className="caret" />}
    </div>
  );
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  if (!text) return null;
  return (
    <button className="copy-btn" title="Copy" onClick={() => {
      navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1400); });
    }}>
      {done ? "✓ Copied" : "⧉ Copy"}
    </button>
  );
}

function inline(text) {
  return String(text).split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`")  && p.endsWith("`"))  return <code key={i}>{p.slice(1, -1)}</code>;
    if (p.startsWith("_")  && p.endsWith("_"))  return <em key={i}>{p.slice(1, -1)}</em>;
    return <span key={i}>{p}</span>;
  });
}
