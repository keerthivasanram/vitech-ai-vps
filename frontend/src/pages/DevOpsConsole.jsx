import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Database, FileClock, Gauge, HardDrive,
  RefreshCw, ScrollText, Search, ShieldCheck, Timer, X,
} from "lucide-react";
import { Button } from "../common/Button";

/**
 * Developer Operations Console — the SERVICE PROVIDER's view of the platform.
 *
 * This is not a Vitech-facing feature. Vitech's engineers use the agents, the
 * studio and the Package Center; this console is how we, running the service,
 * see what the platform is doing: health, request traces, job history,
 * structured logs, metrics, the audit trail and cache behaviour.
 *
 * That is why every endpoint it reads sits behind `/api/admin/*` and the
 * administrator role — an engineer is never shown this, and would be refused by
 * the server if they reached it anyway.
 *
 * Read-only. Nothing here mutates engineering data.
 */

const TABS = [
  { id: "health", label: "Health", icon: Activity },
  { id: "metrics", label: "Metrics", icon: Gauge },
  { id: "requests", label: "Requests", icon: Timer },
  { id: "jobs", label: "Jobs", icon: FileClock },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "audit", label: "Audit", icon: ShieldCheck },
  { id: "cache", label: "Cache", icon: Database },
];

const fmtTime = (epoch) =>
  epoch ? new Date(epoch * 1000).toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    second: "2-digit",
  }) : "—";

const ms = (v) => (v == null ? "—" : `${v} ms`);

function useEndpoint(url, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setError("");
    fetch(url)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) (d.ok === false ? setError(d.error || "Request failed.") : setData(d)); })
      .catch(() => { if (!cancelled) setError("Could not reach the server."); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, nonce, ...deps]);

  return { data, error, reload };
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className={`dv-stat${tone ? ` is-${tone}` : ""}`}>
      <b>{value}</b>
      <span>{label}</span>
      {sub && <em>{sub}</em>}
    </div>
  );
}

/* ---------------- Health + service status ---------------- */
function HealthTab() {
  const { data, error, reload } = useEndpoint("/api/admin/health/detail");
  if (error) return <div className="jc-err">{error}</div>;
  if (!data) return <p className="jc-muted">Checking services…</p>;
  const services = Object.entries(data.services || {});
  const down = services.filter(([, s]) => !s.ok).length;

  return (
    <>
      <div className="dv-bar">
        <span className={`jc-pill is-${down ? "bad" : "ok"}`}>
          {down ? `${down} service(s) down` : "All services responding"}
        </span>
        <Button variant="ghost" onClick={reload}>
          <RefreshCw size={14} strokeWidth={2} /> Refresh
        </Button>
      </div>

      <div className="dv-cards">
        {services.map(([name, s]) => (
          <div key={name} className={`dv-card${s.ok ? "" : " is-bad"}`}>
            <div className="dv-card-h">
              <b>{name.replace(/_/g, " ")}</b>
              <span className={`jc-pill is-${s.ok ? "ok" : "bad"}`}>{s.ok ? "up" : "down"}</span>
            </div>
            <p className="dv-card-d">{s.detail}</p>
            <span className="dv-card-m">{s.ms} ms</span>
          </div>
        ))}
      </div>

      <div className="card dv-block">
        <h3 className="card-h2">Language model</h3>
        <dl className="jc-dl">
          <div><dt>Model</dt><dd>{data.llm?.model}</dd></div>
          <div><dt>Host</dt><dd>{data.llm?.host}</dd></div>
        </dl>
      </div>
    </>
  );
}

/* ---------------- Metrics ---------------- */
function MetricsTab() {
  const [hours, setHours] = useState(24);
  const { data, error, reload } = useEndpoint(`/api/admin/metrics?window_hours=${hours}`);
  if (error) return <div className="jc-err">{error}</div>;
  if (!data) return <p className="jc-muted">Loading metrics…</p>;

  const rt = data.response_time || {};
  const failPct = ((data.failure_rate || 0) * 100).toFixed(1);

  return (
    <>
      <div className="dv-bar">
        <select className="jc-select" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          <option value={1}>Last hour</option>
          <option value={24}>Last 24 hours</option>
          <option value={168}>Last 7 days</option>
        </select>
        <Button variant="ghost" onClick={reload}>
          <RefreshCw size={14} strokeWidth={2} /> Refresh
        </Button>
      </div>

      <div className="dv-stats">
        <Stat label="Requests" value={data.requests} />
        <Stat label="Failure rate" value={`${failPct}%`}
              tone={data.failures ? "bad" : "ok"} sub={`${data.failures} failed`} />
        <Stat label="Avg response" value={ms(rt.avg_ms)} sub={`p95 ${ms(rt.p95_ms)}`} />
        <Stat label="LLM latency" value={ms(data.llm?.avg_ms)} sub={`${data.llm?.count || 0} calls`} />
        <Stat label="Retrieval" value={ms(data.retrieval?.avg_ms)} sub={`${data.retrieval?.count || 0} lookups`} />
        <Stat label="Package build" value={ms(data.package_generation?.avg_ms)}
              sub={`${data.package_generation?.count || 0} packages`} />
        <Stat label="Active users" value={data.active_users} />
        <Stat label="Service principals" value={data.active_service_principals} />
      </div>

      <div className="dv-two">
        <div className="card dv-block">
          <h3 className="card-h2">By tool</h3>
          {(data.by_tool || []).length === 0 && <p className="jc-muted">No tool calls in this window.</p>}
          {(data.by_tool || []).map((t) => (
            <div key={t.tool} className="dv-row">
              <span>{t.tool}</span>
              <span className="jc-muted">{t.n} · {ms(Math.round(t.avg_ms || 0))}</span>
            </div>
          ))}
        </div>
        <div className="card dv-block">
          <h3 className="card-h2">By equipment</h3>
          {(data.by_equipment || []).length === 0 && <p className="jc-muted">No equipment resolved in this window.</p>}
          {(data.by_equipment || []).map((e) => (
            <div key={e.equipment} className="dv-row">
              <span>{String(e.equipment).replace(/_/g, " ")}</span>
              <span className="jc-muted">{e.n}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card dv-block">
        <h3 className="card-h2">Telemetry writer</h3>
        {/* Surfaced because dropped records mean the trace is incomplete, and a
            silently incomplete trace is worse than none. */}
        <dl className="jc-dl">
          <div><dt>Written</dt><dd>{data.telemetry_writer?.written}</dd></div>
          <div><dt>Dropped</dt><dd className={data.telemetry_writer?.dropped ? "dv-warn" : ""}>
            {data.telemetry_writer?.dropped}</dd></div>
          <div><dt>Queued</dt><dd>{data.telemetry_writer?.queued}</dd></div>
          <div><dt>Errors</dt><dd>{data.telemetry_writer?.errors}</dd></div>
        </dl>
      </div>
    </>
  );
}

/* ---------------- Request timeline + trace viewer ---------------- */
function TraceDrawer({ requestId, onClose }) {
  const { data, error } = useEndpoint(`/api/admin/trace/${encodeURIComponent(requestId)}`);
  const req = data?.request;
  const spans = data?.spans || [];
  const widest = Math.max(1, ...spans.map((s) => s.duration_ms || 0));

  return (
    <>
      <div className="jc-scrim" onClick={onClose} />
      <aside className="jc-drawer is-wide" aria-label="Execution trace">
        <header className="jc-drawer-h">
          <div className="jc-drawer-t">
            <Timer size={17} strokeWidth={1.9} />
            <div>
              <b>Execution trace</b>
              <span>{requestId}</span>
            </div>
          </div>
          <button className="jc-x" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </header>

        <div className="jc-drawer-b">
          {error && <div className="jc-err">{error}</div>}
          {!data && !error && <p className="jc-muted">Reconstructing…</p>}

          {req && (
            <section className="jc-sec">
              <h4>Request</h4>
              <dl className="jc-dl">
                <div><dt>Route</dt><dd>{req.method} {req.path}</dd></div>
                <div><dt>Status</dt><dd>
                  <span className={`jc-pill is-${req.ok ? "ok" : "bad"}`}>{req.status}</span></dd></div>
                <div><dt>Actor</dt><dd>{req.actor || "—"} <span className="jc-muted">({req.actor_kind})</span></dd></div>
                <div><dt>Duration</dt><dd>{ms(req.duration_ms)}</dd></div>
                <div><dt>Agent / tool</dt><dd>{req.agent || "—"}{req.tool ? ` · ${req.tool}` : ""}</dd></div>
                <div><dt>Equipment</dt><dd>{req.equipment ? req.equipment.replace(/_/g, " ") : "—"}</dd></div>
                <div><dt>Historical retrieval</dt><dd>{req.retrieval_count}</dd></div>
                <div><dt>Engineering rules</dt><dd>{req.rule_count}</dd></div>
                <div><dt>Warnings</dt><dd>{req.warning_count}</dd></div>
                <div><dt>LLM time</dt><dd>{ms(req.llm_ms)}</dd></div>
              </dl>
            </section>
          )}

          <section className="jc-sec">
            <h4>Execution path {spans.length ? <span className="jc-count">{spans.length}</span> : null}</h4>
            {!spans.length && <p className="jc-muted">No spans recorded.</p>}
            {spans.map((s) => (
              <div key={s.id} className="dv-span">
                <div className="dv-span-h">
                  <span className="dv-span-n">{s.name}</span>
                  <span className="dv-span-k">{s.kind}</span>
                  <span className="dv-span-t">{ms(s.duration_ms)}</span>
                </div>
                <div className="dv-span-bar">
                  <i style={{ width: `${Math.max(2, ((s.duration_ms || 0) / widest) * 100)}%` }} />
                </div>
                {s.detail && Object.keys(s.detail).length > 0 && (
                  <div className="dv-span-d">
                    {Object.entries(s.detail).map(([k, v]) => (
                      <span key={k}>{k}: <b>{String(v)}</b></span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </section>

          {!!data?.jobs?.length && (
            <section className="jc-sec">
              <h4>Jobs produced</h4>
              {data.jobs.map((j) => (
                <div key={j.job_id} className="dv-row">
                  <span>{j.kind} · {j.equipment || "—"}</span>
                  <span className="jc-muted">{j.status} · {(j.artifacts || []).length} artifacts</span>
                </div>
              ))}
            </section>
          )}

          {!!data?.log_lines?.length && (
            <section className="jc-sec">
              <h4>Log lines</h4>
              <pre className="dv-pre">
                {data.log_lines.map((l, i) => `${l.level} ${l.msg} ${l.path || ""}`.trim()).join("\n")}
              </pre>
            </section>
          )}
        </div>
      </aside>
    </>
  );
}

function RequestsTab() {
  const [failedOnly, setFailedOnly] = useState(false);
  const [trace, setTrace] = useState(null);
  const { data, error, reload } = useEndpoint(
    `/api/admin/requests?limit=150${failedOnly ? "&failed_only=true" : ""}`);

  return (
    <>
      <div className="dv-bar">
        <button type="button" className={`fchip${failedOnly ? " is-on" : ""}`}
                onClick={() => setFailedOnly((v) => !v)}>
          <AlertTriangle size={13} strokeWidth={2} /> Failures only
        </button>
        <Button variant="ghost" onClick={reload}>
          <RefreshCw size={14} strokeWidth={2} /> Refresh
        </Button>
      </div>

      {error && <div className="jc-err">{error}</div>}
      {!data && !error && <p className="jc-muted">Loading requests…</p>}

      {data && (
        <div className="card jc-tablecard">
          <table className="jc-table">
            <thead>
              <tr>
                <th>When</th><th>Route</th><th>Actor</th><th>Tool</th>
                <th>Equipment</th><th>Duration</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.requests.map((r) => (
                <tr key={r.request_id} onClick={() => setTrace(r.request_id)} tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && setTrace(r.request_id)}>
                  <td className="jc-date">{fmtTime(r.at)}</td>
                  <td><span className="dv-route">{r.method} {r.path}</span></td>
                  <td>{r.actor || <span className="jc-muted">anonymous</span>}</td>
                  <td>{r.tool || <span className="jc-muted">—</span>}</td>
                  <td>{r.equipment ? r.equipment.replace(/_/g, " ") : <span className="jc-muted">—</span>}</td>
                  <td>{ms(r.duration_ms)}</td>
                  <td><span className={`jc-pill is-${r.ok ? "ok" : "bad"}`}>{r.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {trace && <TraceDrawer requestId={trace} onClose={() => setTrace(null)} />}
    </>
  );
}

/* ---------------- Jobs (operator view) ---------------- */
function JobsTab() {
  const { data, error, reload } = useEndpoint("/api/admin/jobs?limit=200");
  return (
    <>
      <div className="dv-bar">
        <span className="jc-muted">Permanent record — job history is never purged.</span>
        <Button variant="ghost" onClick={reload}><RefreshCw size={14} strokeWidth={2} /> Refresh</Button>
      </div>
      {error && <div className="jc-err">{error}</div>}
      {!data && !error && <p className="jc-muted">Loading jobs…</p>}
      {data && (
        <div className="card jc-tablecard">
          <table className="jc-table">
            <thead>
              <tr><th>Kind</th><th>Equipment</th><th>Actor</th><th>Release</th>
                  <th>Status</th><th>Duration</th><th>Created</th></tr>
            </thead>
            <tbody>
              {data.jobs.map((j) => (
                <tr key={j.job_id}>
                  <td>{j.kind}</td>
                  <td>{j.equipment ? j.equipment.replace(/_/g, " ") : "—"}</td>
                  <td>{j.actor || "—"}</td>
                  <td>{j.release_status || <span className="jc-muted">—</span>}</td>
                  <td><span className={`jc-pill is-${j.status === "succeeded" ? "ok" : j.status === "failed" ? "bad" : "muted"}`}>{j.status}</span></td>
                  <td>{ms(j.duration_ms)}</td>
                  <td className="jc-date">{fmtTime(j.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/* ---------------- Structured logs ---------------- */
function LogsTab() {
  const [level, setLevel] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const { data, error, reload } = useEndpoint(
    `/api/admin/logs?limit=250${level ? `&level=${level}` : ""}${applied ? `&contains=${encodeURIComponent(applied)}` : ""}`);

  return (
    <>
      <div className="dv-bar">
        <div className="jc-search">
          <Search size={15} strokeWidth={1.9} />
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && setApplied(q)}
                 placeholder="Search log lines… (Enter)" aria-label="Search logs" />
        </div>
        <select className="jc-select" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">All levels</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <Button variant="ghost" onClick={reload}><RefreshCw size={14} strokeWidth={2} /> Refresh</Button>
      </div>

      {/* Stated because it is a deliberate design decision, not an omission. */}
      <p className="dv-note">
        <ShieldCheck size={13} strokeWidth={2} />
        Customer requirements are never written to logs — they are held on the
        job record instead. Log lines carry the request id, so a trace can still
        be reconstructed.
      </p>

      {error && <div className="jc-err">{error}</div>}
      {!data && !error && <p className="jc-muted">Loading logs…</p>}
      {data && (
        <>
          <div className="card jc-tablecard">
            <table className="jc-table dv-logtable">
              <thead><tr><th>Time</th><th>Level</th><th>Message</th><th>Route</th><th>ms</th></tr></thead>
              <tbody>
                {data.entries.map((e, i) => (
                  <tr key={i}>
                    <td className="jc-date">{e.time?.replace("T", " ") || "—"}</td>
                    <td><span className={`jc-pill is-${e.level === "ERROR" ? "bad" : e.level === "WARNING" ? "warn" : "muted"}`}>{e.level}</span></td>
                    <td>{e.msg}</td>
                    <td className="dv-route">{e.path || "—"}</td>
                    <td>{e.ms ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="jc-muted dv-foot">
            <HardDrive size={12} strokeWidth={2} /> {data.files?.files?.length || 0} file(s),
            {" "}{Math.round((data.files?.total_bytes || 0) / 1024)} KB on disk
          </p>
        </>
      )}
    </>
  );
}

/* ---------------- Audit ---------------- */
function AuditTab() {
  const { data, error, reload } = useEndpoint("/api/admin/audit?limit=250");
  return (
    <>
      <div className="dv-bar">
        <span className="jc-muted">Every non-public request, reads included. Never purged.</span>
        <Button variant="ghost" onClick={reload}><RefreshCw size={14} strokeWidth={2} /> Refresh</Button>
      </div>
      {error && <div className="jc-err">{error}</div>}
      {!data && !error && <p className="jc-muted">Loading audit trail…</p>}
      {data && (
        <div className="card jc-tablecard">
          <table className="jc-table">
            <thead><tr><th>When</th><th>Actor</th><th>Role</th><th>Action</th><th>Status</th><th>Detail</th></tr></thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id}>
                  <td className="jc-date">{fmtTime(e.at)}</td>
                  <td>{e.actor}</td>
                  <td>{e.role || <span className="jc-muted">—</span>}</td>
                  <td className="dv-route">{e.action}</td>
                  <td>
                    <span className={`jc-pill is-${!e.status || e.status < 400 ? "ok" : e.status < 500 ? "warn" : "bad"}`}>
                      {e.status ?? "—"}
                    </span>
                  </td>
                  <td className="jc-muted">{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/* ---------------- Cache ---------------- */
function CacheTab() {
  const { data, error, reload } = useEndpoint("/api/admin/cache");
  if (error) return <div className="jc-err">{error}</div>;
  if (!data) return <p className="jc-muted">Loading cache statistics…</p>;
  const ratio = data.hit_ratio == null ? "—" : `${(data.hit_ratio * 100).toFixed(1)}%`;
  return (
    <>
      <div className="dv-bar">
        <Button variant="ghost" onClick={reload}><RefreshCw size={14} strokeWidth={2} /> Refresh</Button>
      </div>
      <div className="dv-stats">
        <Stat label="Hit ratio" value={ratio} />
        <Stat label="Hits" value={data.hits} />
        <Stat label="Misses" value={data.misses} />
        <Stat label="Lookups" value={data.lookups} />
      </div>
      <p className="dv-note"><ShieldCheck size={13} strokeWidth={2} />{data.note}</p>
    </>
  );
}

const PANES = {
  health: HealthTab, metrics: MetricsTab, requests: RequestsTab,
  jobs: JobsTab, logs: LogsTab, audit: AuditTab, cache: CacheTab,
};

export function DevOpsConsole() {
  const [tab, setTab] = useState("health");
  const Pane = PANES[tab];

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-head">
          <h1>Developer Operations</h1>
          <p>
            Service-provider view of the running platform — health, execution
            traces, job history, logs, metrics and the audit trail. Read-only:
            nothing here changes engineering data.
          </p>
        </div>

        <div className="dv-tabs" role="tablist">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={`dv-tab${tab === t.id ? " is-on" : ""}`}
                onClick={() => setTab(t.id)}
              >
                <Icon size={14} strokeWidth={1.9} />
                {t.label}
              </button>
            );
          })}
        </div>

        <Pane />
      </div>
    </div>
  );
}
