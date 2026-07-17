import { memo } from "react";
import { Download } from "lucide-react";
import { inr } from "../lib/format";

/** Conic-gradient confidence dial. */
export const ConfidenceRing = memo(function ConfidenceRing({ pct, label }) {
  const cls = (label || "").toLowerCase();
  return (
    <div className={`ring ring-${cls}`} style={{ "--p": pct }} role="img"
         aria-label={`Confidence ${pct}% (${label})`}>
      <div className="ring-in">
        <b>{pct}%</b>
        <span>{label}</span>
      </div>
    </div>
  );
});

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
  } catch {
    /* offline / backend down — no-op */
  }
}

/**
 * Budgetary quotation, rendered from the deterministic engine's payload.
 * Every number here comes from the backend — nothing is computed in the UI.
 */
export const QuotationCard = memo(function QuotationCard({ q }) {
  if (!q) return null;
  const p = q.price || {};
  const scope = (q.scope || []).filter((s) => s.origin !== "given");

  return (
    <div className="quote">
      <div className="quote-top">
        <div>
          <div className="quote-name">{q.headline}</div>
          <div className="quote-ref">{q.ref} · {q.date}</div>
        </div>
        <div className="quote-top-r">
          <span className="badge warn">DRAFT</span>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => downloadQuotePdf(q)}>
            <Download size={14} strokeWidth={1.8} aria-hidden="true" />
            Download PDF
          </button>
        </div>
      </div>

      <div className="quote-price">
        <div>
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
            <span className="req-chip" key={i}><b>{g.label}</b>{g.value}</span>
          ))}
        </div>
      )}

      {scope.length > 0 && (
        <div className="quote-sec">
          <div className="quote-sec-t">Scope of supply</div>
          {scope.map((s, i) => (
            <div className="scope-row" key={i}>
              <span className="scope-item">{s.item}</span>
              <span className="scope-spec">{s.spec}</span>
            </div>
          ))}
        </div>
      )}

      <div className="quote-sec">
        <div className="quote-sec-t">Commercial terms</div>
        {(q.terms || []).map((t, i) => (
          <div className="term-row" key={i}><b>{t[0]}</b> — {t[1]}</div>
        ))}
      </div>

      <div className="quote-foot">
        {q.basis_offers?.length > 0 && <span>Priced from {q.basis_offers.join(", ")}</span>}
        <span className="quote-note">{q.note}</span>
      </div>
    </div>
  );
});
