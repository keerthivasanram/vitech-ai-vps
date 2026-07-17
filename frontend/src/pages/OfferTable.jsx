import { memo, useMemo, useState } from "react";
import { catLabel, inrMaybe } from "../lib/format";

/**
 * Category + free-text filtering over the offer rows.
 * Shared by the Knowledge Base and the Historical Projects collection, which
 * render the identical table.
 */
export function useOfferSearch(offers) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (offers || []).filter(
      (o) =>
        (cat === "all" || o.category === cat) &&
        (!term || `${o.id} ${o.client} ${o.ref}`.toLowerCase().includes(term))
    );
  }, [offers, q, cat]);

  return { q, setQ, cat, setCat, rows };
}

/** Searchable table of stored offer records. Rows open the record drawer. */
export const OfferTable = memo(function OfferTable({ search, onOpen }) {
  const { q, setQ, cat, rows } = search;

  return (
    <>
      <div className="filters">
        <input
          className="input"
          placeholder="Search client / id / ref…"
          aria-label="Search records"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="filters-count">
          {rows.length} shown{cat !== "all" ? ` · ${catLabel(cat)}` : ""}
        </span>
      </div>

      <div className="tablewrap">
        <table className="dtable-full">
          <thead>
            <tr>
              <th>ID</th><th>Type</th><th>Client</th><th>Ref</th>
              <th>Date</th><th>Fields</th><th>Price</th><th>Source file</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.id} className="is-click" onClick={() => onOpen(o.id)}>
                <td className="mono">{o.id}</td>
                <td>{catLabel(o.category)}</td>
                <td>{o.client}</td>
                <td className="mono">{o.ref}</td>
                <td>{o.date}</td>
                <td>{o.n_given}+{o.n_tech}</td>
                <td>{inrMaybe(o.price_total)}</td>
                <td className="cell-src" title={o.source_file}>{o.source_file}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
});
