import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownToLine, FileText, Layers, PenTool, ReceiptText, Search,
  ShieldCheck, X,
} from "lucide-react";
import { Button } from "../common/Button";

/**
 * Engineering Job History & Package Center.
 *
 * Every specification, drawing, BOM, quotation and package the platform has
 * produced is a persisted job, so this is the place an engineer comes back to
 * rather than regenerating. Reads `/api/jobs`; everything shown is stored, not
 * recomputed, which is why an artifact downloaded here is byte-for-byte the
 * document that was issued.
 */

const KINDS = [
  { id: "", label: "All" },
  { id: "package", label: "Packages", icon: Layers },
  { id: "specification", label: "Specifications", icon: FileText },
  { id: "drawing", label: "Drawings", icon: PenTool },
  { id: "quotation", label: "Quotations", icon: ReceiptText },
  { id: "bom", label: "BOM", icon: Layers },
];

const KIND_ICON = {
  package: Layers, specification: FileText, drawing: PenTool,
  quotation: ReceiptText, bom: Layers, ingest: ArrowDownToLine,
};

// The client's own release ladder. Colour follows meaning, not decoration:
// anything not yet fit to send a customer reads as a warning.
const RELEASE_TONE = {
  "Customer Ready": "ok",
  "Customer Review Draft": "warn",
  "Engineering Draft": "warn",
  "Released Design": "ok",
};

function fmtDate(epoch) {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function fmtBytes(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function StatusPill({ status }) {
  const tone = status === "succeeded" ? "ok"
    : status === "failed" ? "bad"
    : status === "running" ? "warn" : "muted";
  return <span className={`jc-pill is-${tone}`}>{status}</span>;
}

/** Job detail: what was asked, what came out, and what can be downloaded. */
function JobDrawer({ job, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError("");
    fetch(`/api/jobs/${encodeURIComponent(job.job_id)}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) (d.ok ? setDetail(d.job) : setError(d.error || "Could not load the job.")); })
      .catch(() => { if (!cancelled) setError("Could not reach the server."); });
    return () => { cancelled = true; };
  }, [job.job_id]);

  const Icon = KIND_ICON[job.kind] || FileText;
  const summary = useMemo(() => {
    try { return detail?.summary ? JSON.parse(detail.summary) : null; } catch { return null; }
  }, [detail]);

  return (
    <>
      <div className="jc-scrim" onClick={onClose} />
      <aside className="jc-drawer" aria-label="Job details">
        <header className="jc-drawer-h">
          <div className="jc-drawer-t">
            <Icon size={17} strokeWidth={1.9} />
            <div>
              <b>{job.equipment ? job.equipment.replace(/_/g, " ") : job.kind}</b>
              <span>{job.kind} · {job.job_id}</span>
            </div>
          </div>
          <button className="jc-x" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </header>

        <div className="jc-drawer-b">
          {/* The customer's own words. Stored verbatim on the job because every
              later question about the document resolves against it. */}
          <section className="jc-sec">
            <h4>Customer requirement</h4>
            <blockquote className="jc-quote">
              {job.requirement || <em>Not recorded.</em>}
            </blockquote>
          </section>

          <section className="jc-sec">
            <h4>Outcome</h4>
            <dl className="jc-dl">
              <div><dt>Status</dt><dd><StatusPill status={job.status} /></dd></div>
              <div><dt>Revision</dt><dd>Rev {job.revision ?? "0"}</dd></div>
              <div><dt>Release status</dt><dd>
                {job.release_status
                  ? <span className={`jc-pill is-${RELEASE_TONE[job.release_status] || "muted"}`}>
                      {job.release_status}
                    </span>
                  : "—"}
              </dd></div>
              <div><dt>Confidence</dt><dd>{job.confidence_pct != null ? `${job.confidence_pct}%` : "—"}</dd></div>
              <div><dt>Warnings</dt><dd>{job.warning_count ?? 0}</dd></div>
              <div><dt>Open items</dt><dd>{job.tbd_count ?? 0}</dd></div>
              <div><dt>Created</dt><dd>{fmtDate(job.created_at)}</dd></div>
              <div><dt>Duration</dt><dd>{job.duration_ms != null ? `${job.duration_ms} ms` : "—"}</dd></div>
              <div><dt>By</dt><dd>{job.actor || "—"}</dd></div>
              {job.project && <div><dt>Project</dt><dd>{job.project}</dd></div>}
              {job.client && <div><dt>Client</dt><dd>{job.client}</dd></div>}
            </dl>
            {job.error && <div className="jc-err">{job.error}</div>}
          </section>

          {summary && (
            <section className="jc-sec">
              <h4>Summary</h4>
              <dl className="jc-dl">
                {Object.entries(summary).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k.replace(/_/g, " ")}</dt>
                    <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section className="jc-sec">
            <h4>
              Artifacts
              {detail?.artifacts?.length ? <span className="jc-count">{detail.artifacts.length}</span> : null}
            </h4>
            {error && <div className="jc-err">{error}</div>}
            {!detail && !error && <p className="jc-muted">Loading…</p>}
            {detail && !detail.artifacts?.length && (
              <p className="jc-muted">
                No stored files. Documents are kept when a package is exported;
                interactive previews are regenerated on demand.
              </p>
            )}
            {detail?.artifacts?.map((a) => (
              <a
                key={a.name}
                className="jc-artifact"
                href={`/api/jobs/${encodeURIComponent(job.job_id)}/artifact/${encodeURIComponent(a.name)}`}
                download={a.name}
              >
                <ArrowDownToLine size={15} strokeWidth={1.9} />
                <span className="jc-artifact-n">{a.name}</span>
                <span className="jc-artifact-s">{fmtBytes(a.bytes)}</span>
                {/* Shown because it is the guarantee: this file is the one that
                    was issued, not a fresh render that might differ. */}
                <span className="jc-artifact-h" title={`SHA-256 ${a.sha256}`}>
                  <ShieldCheck size={13} strokeWidth={2} />
                  {String(a.sha256 || "").slice(0, 8)}
                </span>
              </a>
            ))}
          </section>
        </div>
      </aside>
    </>
  );
}

export function PackageCenter() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("newest");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setJobs(null);
    const params = new URLSearchParams({ limit: "300" });
    if (kind) params.set("kind", kind);
    fetch(`/api/jobs?${params}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) (d.ok ? setJobs(d.jobs) : setError(d.error || "Could not load jobs.")); })
      .catch(() => { if (!cancelled) setError("Could not reach the server."); });
    return () => { cancelled = true; };
  }, [kind]);

  const rows = useMemo(() => {
    let out = jobs || [];
    const needle = q.trim().toLowerCase();
    if (needle) {
      out = out.filter((j) =>
        [j.equipment, j.client, j.project, j.requirement, j.actor, j.job_id,
         j.release_status, j.kind]
          .some((v) => String(v || "").toLowerCase().includes(needle)));
    }
    const by = {
      newest: (a, b) => (b.created_at || 0) - (a.created_at || 0),
      oldest: (a, b) => (a.created_at || 0) - (b.created_at || 0),
      equipment: (a, b) => String(a.equipment || "").localeCompare(String(b.equipment || "")),
      client: (a, b) => String(a.client || "").localeCompare(String(b.client || "")),
      status: (a, b) => String(a.status).localeCompare(String(b.status)),
    }[sort];
    return [...out].sort(by);
  }, [jobs, q, sort]);

  const counts = useMemo(() => {
    const c = {};
    for (const j of jobs || []) c[j.kind] = (c[j.kind] || 0) + 1;
    return c;
  }, [jobs]);

  return (
    <div className="page">
      <div className="page-inner">
        <div className="page-head">
          <h1>Package Center</h1>
          <p>
            Every specification, drawing, bill of materials, quotation and
            engineering package this platform has produced. Stored, not
            regenerated — a download here is the document that was issued.
          </p>
        </div>

        <div className="jc-controls">
          <div className="jc-search">
            <Search size={15} strokeWidth={1.9} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search customer, equipment, project or requirement…"
              aria-label="Search jobs"
            />
          </div>
          <select className="jc-select" value={sort} onChange={(e) => setSort(e.target.value)}
                  aria-label="Sort by">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="equipment">Equipment</option>
            <option value="client">Customer</option>
            <option value="status">Status</option>
          </select>
        </div>

        <div className="chips-row jc-kinds">
          {KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              className={`fchip${kind === k.id ? " is-on" : ""}`}
              onClick={() => setKind(k.id)}
            >
              {k.label}
              {k.id && counts[k.id] ? <b>{counts[k.id]}</b> : null}
            </button>
          ))}
        </div>

        {error && <div className="jc-err">{error}</div>}
        {!jobs && !error && <p className="jc-muted">Loading job history…</p>}

        {jobs && !rows.length && (
          <div className="col-empty">
            <div className="col-empty-ic">📦</div>
            <p className="col-empty-line">
              {q || kind
                ? "No jobs match this filter."
                : "Nothing generated yet. Produce a specification, drawing or package and it appears here automatically."}
            </p>
          </div>
        )}

        {rows.length > 0 && (
          <div className="card jc-tablecard">
            <table className="jc-table">
              <thead>
                <tr>
                  <th>Type</th><th>Equipment</th><th>Customer / Project</th>
                  <th>Rev</th><th>Release status</th><th>Status</th><th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => {
                  const Icon = KIND_ICON[j.kind] || FileText;
                  return (
                    <tr key={j.job_id} onClick={() => setSelected(j)} tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && setSelected(j)}>
                      <td>
                        <span className="jc-kind">
                          <Icon size={14} strokeWidth={1.9} />
                          {j.kind}
                        </span>
                      </td>
                      <td>{j.equipment ? j.equipment.replace(/_/g, " ") : "—"}</td>
                      <td>
                        {j.client || j.project
                          ? <>{j.client || "—"}{j.project ? <span className="jc-sub"> · {j.project}</span> : null}</>
                          : <span className="jc-muted">—</span>}
                      </td>
                      <td>{j.revision ?? "0"}</td>
                      <td>
                        {j.release_status
                          ? <span className={`jc-pill is-${RELEASE_TONE[j.release_status] || "muted"}`}>
                              {j.release_status}
                            </span>
                          : <span className="jc-muted">—</span>}
                      </td>
                      <td><StatusPill status={j.status} /></td>
                      <td className="jc-date">{fmtDate(j.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <JobDrawer job={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
