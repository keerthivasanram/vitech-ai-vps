import { useEffect, useState } from "react";
import { Button } from "../common/Button";
import { OfferDrawer } from "../components/OfferDrawer";
import { OfferTable, useOfferSearch } from "./OfferTable";
import { COLL_BADGE, COLL_STATE } from "./collectionMeta";

/** State-aware panel for a collection that has no rows to show yet. */
function CollectionEmpty({ meta, ov, setView }) {
  const isQuotes = meta.key === "quotations";
  const agentLabel = isQuotes ? "Quotation" : "Engineering";
  const onDemandAgent = isQuotes ? "quotation" : "engineering";

  const cta = {
    ingest: {
      line: "No documents ingested yet. Drop files into the pipeline and they appear here — chunked, embedded and searchable, grounding the agents.",
      btn: { label: "Go to Documents", to: "upload" },
    },
    on_demand: {
      line: `Not archived — these are produced on demand by the ${agentLabel} Agent, deterministically, whenever you ask.`,
      btn: { label: `Open ${agentLabel} Agent`, to: onDemandAgent },
    },
    roadmap: {
      line: "On the roadmap — the CAD Engineering Agent will populate this collection.",
      btn: null,
    },
    engine: {
      line: "These are the equipment profiles and sizing rules baked into the deterministic engine — every number the agents quote is derived from them.",
      btn: null,
    },
  }[meta.state] || { line: meta.desc, btn: null };

  return (
    <div className="col-empty">
      <div className="col-empty-ic">{meta.icon}</div>
      <div className="col-empty-n">
        {meta.count}<span> {meta.state === "engine" ? "rule sets" : "documents"}</span>
      </div>
      <p className="col-empty-line">{cta.line}</p>

      {meta.state === "engine" && (
        <div className="chips-row">
          {ov.equipment.map((e) => (
            <span key={e.key} className="fchip is-static">{e.label}</span>
          ))}
        </div>
      )}

      {cta.btn && (
        <Button variant="ghost" onClick={() => setView(cta.btn.to)}>{cta.btn.label}</Button>
      )}
    </div>
  );
}

/** Detail page for one knowledge-base collection. */
export function CollectionPage({ collection, setView }) {
  const [ov, setOv] = useState(null);
  const [data, setData] = useState(null);   // offer rows (Historical Projects only)
  const [sel, setSel] = useState(null);
  const isProjects = collection === "historical_projects";

  const search = useOfferSearch(isProjects && data ? data.offers : []);
  const { setQ, setCat } = search;

  useEffect(() => {
    fetch("/api/knowledge/overview").then((r) => r.json()).then(setOv).catch(() => setOv(null));
    if (isProjects) {
      fetch("/api/offers").then((r) => r.json()).then(setData).catch(() => setData({ count: 0, offers: [] }));
    }
    setQ("");
    setCat("all");
    setSel(null);
  }, [collection, isProjects, setQ, setCat]);

  if (!ov) return <div className="placeholder"><p>Loading collection…</p></div>;

  const meta = ov.collections.find((c) => c.key === collection);
  if (!meta) return <div className="placeholder"><p>Unknown collection.</p></div>;

  const open = (id) =>
    fetch(`/api/offers/${id}`).then((r) => r.json()).then(setSel).catch(() => {});

  return (
    <div className="page-inner">
      <nav className="crumb" aria-label="Breadcrumb">
        <button type="button" className="crumb-link" onClick={() => setView("knowledge")}>
          Knowledge Base
        </button>
        <span aria-hidden="true">›</span>
        <span>{meta.label}</span>
      </nav>

      <header className="col-head">
        <span className="col-ic">{meta.icon}</span>
        <div className="col-head-t">
          <h1>{meta.label}</h1>
          <p>{meta.desc}</p>
        </div>
        <span className={`badge ${COLL_BADGE[meta.state] || "soft"}`}>
          {COLL_STATE[meta.state] || meta.state}
        </span>
      </header>

      <div className="stats">
        <div className="stat">
          <b>{meta.count}</b><span>{isProjects ? "Projects" : "Documents"}</span>
        </div>
        {isProjects && <div className="stat"><b>{ov.equipment.length}</b><span>Equipment types</span></div>}
        {isProjects && <div className="stat"><b>{ov.stats.clients}</b><span>Clients</span></div>}
        <div className="stat">
          <b className="stat-sm">{meta.last_updated || "—"}</b><span>Last updated</span>
        </div>
      </div>

      {isProjects ? (
        <>
          <h2 className="section-label">Filter by equipment</h2>
          <div className="chips-row">
            <button
              type="button"
              className={`fchip${search.cat === "all" ? " is-on" : ""}`}
              onClick={() => search.setCat("all")}
            >
              All <b>{ov.stats.records}</b>
            </button>
            {ov.equipment.map((e) => (
              <button
                key={e.key}
                type="button"
                className={`fchip${search.cat === e.key ? " is-on" : ""}`}
                onClick={() => search.setCat(e.key)}
              >
                {e.label} <b>{e.count}</b>
              </button>
            ))}
          </div>

          <h2 className="section-label">Records</h2>
          <OfferTable search={search} onOpen={open} />
        </>
      ) : (
        <CollectionEmpty meta={meta} ov={ov} setView={setView} />
      )}

      {sel && <OfferDrawer rec={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
