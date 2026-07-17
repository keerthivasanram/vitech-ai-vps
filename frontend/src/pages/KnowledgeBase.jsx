import { useEffect, useMemo, useState } from "react";
import { OfferDrawer } from "../components/OfferDrawer";
import { OfferTable, useOfferSearch } from "./OfferTable";
import { COLL_BADGE, COLL_STATE } from "./collectionMeta";

/**
 * Organised view of everything stored: stats, the collection taxonomy,
 * equipment facets and the searchable record table.
 * Every count is computed by the backend from the actual store.
 */
export function KnowledgeBase({ setView }) {
  const [ov, setOv] = useState(null);      // structured overview (collections / equipment / stats)
  const [data, setData] = useState(null);  // offer rows for the table
  const [sel, setSel] = useState(null);    // full record of the opened file

  useEffect(() => {
    fetch("/api/knowledge/overview").then((r) => r.json()).then(setOv).catch(() => setOv(null));
    fetch("/api/offers").then((r) => r.json()).then(setData).catch(() => setData({ count: 0, offers: [] }));
  }, []);

  const search = useOfferSearch(data?.offers);
  const rules = useMemo(
    () => ov?.collections.find((c) => c.key === "rules")?.count ?? 0,
    [ov]
  );

  if (!data) return <div className="placeholder"><p>Loading knowledge base…</p></div>;

  const open = (id) =>
    fetch(`/api/offers/${id}`).then((r) => r.json()).then(setSel).catch(() => {});

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Knowledge Base</h1>
        <p>Structured engineering knowledge — every count below is computed from what is actually stored.</p>
      </header>

      {ov && (
        <>
          <div className="stats">
            <div className="stat"><b>{ov.stats.records}</b><span>Historical projects</span></div>
            <div className="stat"><b>{ov.stats.equipment_types}</b><span>Equipment types</span></div>
            <div className="stat"><b>{ov.stats.clients}</b><span>Clients</span></div>
            <div className="stat"><b>{ov.stats.documents}</b><span>Reference docs</span></div>
            <div className="stat"><b>{rules}</b><span>Engine rule sets</span></div>
          </div>
          <p className="kb-meta">
            Offer coverage {ov.stats.date_from} → {ov.stats.date_to} · organised by{" "}
            {ov.metadata_fields.join(" · ")}
          </p>

          <h2 className="section-label">Collections</h2>
          <div className="kb-collections">
            {ov.collections.map((c) => (
              <button key={c.key} type="button" className="kb-coll" onClick={() => setView(c.key)}>
                <span className="kb-coll-top">
                  <span className="kb-coll-ic">{c.icon}</span>
                  <span className="kb-coll-n">{c.count}</span>
                </span>
                <span className="kb-coll-label">{c.label}</span>
                <span className="kb-coll-desc">{c.desc}</span>
                <span className={`badge ${COLL_BADGE[c.state] || "soft"}`}>
                  {COLL_STATE[c.state] || c.state}
                </span>
              </button>
            ))}
          </div>

          <h2 className="section-label">Historical projects by equipment</h2>
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
        </>
      )}

      <h2 className="section-label">Records</h2>
      <OfferTable search={search} onOpen={open} />

      {sel && <OfferDrawer rec={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
