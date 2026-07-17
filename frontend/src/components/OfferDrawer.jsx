import { memo, useEffect } from "react";
import { X } from "lucide-react";
import { catLabel, inrMaybe } from "../lib/format";

/** Flatten a record's nested field object into label/value rows. */
function fields(obj) {
  const fmt = (v) =>
    v && typeof v === "object"
      ? Object.entries(v).map(([k, x]) => `${k}: ${x}`).join("; ")
      : String(v);
  return Object.entries(obj || {}).map(([k, v]) => ({ k: k.replace(/_/g, " "), v: fmt(v) }));
}

const DrawerSection = memo(function DrawerSection({ title, sub, rows, tone }) {
  if (!rows.length) return null;
  return (
    <div className={`dsection${tone ? ` dsection-${tone}` : ""}`}>
      <div className="dsection-h">
        <span>{title}</span>
        {sub && <span className="dsection-sub">{sub}</span>}
        <span className="dsection-n">{rows.length}</span>
      </div>
      <div className="dsection-b">
        {rows.map((f, i) => (
          <div className="dg-row" key={i}>
            <span>{f.k}</span>
            <b className={f.price ? "dg-price" : ""}>{f.v}</b>
          </div>
        ))}
      </div>
    </div>
  );
});

/** Slide-over inspector: exactly how one offer record is stored. */
export const OfferDrawer = memo(function OfferDrawer({ rec, onClose }) {
  // Esc closes — expected of any slide-over.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ps = rec.price_schedule || {};
  const cur = ps.currency || "INR";
  const priceRows = Object.entries(ps)
    .filter(([k]) => k !== "currency")
    .map(([k, v]) => ({
      k: k.replace(/_/g, " "),
      v: typeof v === "number" ? inrMaybe(v) : String(v),
      price: typeof v === "number",
    }));

  return (
    <>
      <button type="button" className="drawer-scrim" aria-label="Close record" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Record ${rec.id}`}>
        <div className="drawer-head">
          <div className="drawer-head-l">
            {rec.category && <span className="badge cat drawer-cat">{catLabel(rec.category)}</span>}
            <div className="drawer-id">{rec.id}</div>
            <div className="drawer-client">{rec.client || "—"}</div>
          </div>
          <button type="button" className="drawer-x" onClick={onClose} aria-label="Close">
            <X size={18} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>

        <div className="drawer-meta">
          {rec.source_file && <span className="dmeta" title={rec.source_file}>{rec.source_file}</span>}
          {rec.ref && <span className="dmeta">Ref {rec.ref}</span>}
          {rec.date && <span className="dmeta">{rec.date}</span>}
          {rec.vendor && <span className="dmeta">{rec.vendor}</span>}
        </div>

        <DrawerSection title="Given data" sub="what the client supplied" rows={fields(rec.given_data)} />
        <DrawerSection title="Technical details" sub="what Vitech engineered" rows={fields(rec.technical_details)} />
        <DrawerSection title="Price schedule" sub={cur} rows={priceRows} tone="price" />
      </aside>
    </>
  );
});
