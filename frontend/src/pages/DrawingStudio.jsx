import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Download, Layers, ListTree, Loader2, Maximize2, Minus,
  PenTool, Plus, RotateCcw, Ruler, Send,
} from "lucide-react";
import { Button } from "../common/Button";

/**
 * Drawing Studio — split controls + live GA canvas.
 *
 * The drawing comes from the BACKEND engine (`POST /api/drawing/render`), the
 * same deterministic geometry the Drawing Agent's `generate_drawing` tool
 * returns. Nothing about the drawing is computed in the browser: this file
 * collects inputs, renders the returned SVG and handles view state only.
 *
 * The form is DATA-DRIVEN from `GET /api/drawing/catalog` — equipment
 * categories, their input fields, drawing types and sheet sizes all come from
 * the backend catalog, so adding a category server-side makes it selectable
 * here with no change to this file.
 */
const PRESETS = [
  { label: "Paint booth 5 x 3 x 4 m", category: "paint_booth",
    values: { length_m: 5, width_m: 3, height_m: 4, paint_type: "liquid" } },
  { label: "Wet scrubber 800 CFM", category: "wet_scrubber",
    values: { air_volume_cfm: 800, tower_diameter_mm: 750, qty: 1 } },
];

export function DrawingStudio() {
  const [catalog, setCatalog] = useState(null);
  const [category, setCategory] = useState("");
  const [drawingType, setDrawingType] = useState("ga");
  const [sheetSize, setSheetSize] = useState("A3");
  const [values, setValues] = useState({});
  const [client, setClient] = useState("");
  const [ref, setRef] = useState("");

  const [drawing, setDrawing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(() => new Set());

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef(null);

  // Load the catalog once; it defines every choice the form offers.
  useEffect(() => {
    let alive = true;
    fetch("/api/drawing/catalog")
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        setCatalog(d);
        setSheetSize(d.default_sheet || "A3");
        const first = d.categories?.[0];
        if (first) {
          setCategory(first.key);
          setValues({});
        }
      })
      .catch(() => alive && setError("Could not load the drawing catalog. Is the backend running?"));
    return () => { alive = false; };
  }, []);

  const activeCategory = useMemo(
    () => catalog?.categories?.find((c) => c.key === category) || null,
    [catalog, category],
  );

  const missingRequired = useMemo(() => {
    if (!activeCategory) return [];
    return activeCategory.fields
      .filter((f) => f.required && (values[f.key] === undefined || values[f.key] === ""))
      .map((f) => f.label);
  }, [activeCategory, values]);

  const generate = useCallback(async () => {
    if (!category) return;
    setBusy(true); setError("");
    try {
      const res = await fetch("/api/drawing/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category, values, sheet_size: sheetSize,
          drawing_type: drawingType, client, ref,
        }),
      });
      const d = await res.json();
      if (!d.ok) { setError(d.error || "The drawing could not be generated."); setDrawing(null); }
      else { setDrawing(d); setHidden(new Set()); setZoom(1); setPan({ x: 0, y: 0 }); }
    } catch {
      setError("Could not reach the drawing engine.");
    } finally {
      setBusy(false);
    }
  }, [category, values, sheetSize, drawingType, client, ref]);

  const applyPreset = (p) => {
    setCategory(p.category);
    setValues(p.values);
    setDrawing(null);
  };

  const toggleLayer = (id) =>
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const onWheel = useCallback((e) => {
    e.preventDefault();
    setZoom((z) => Math.min(6, Math.max(0.3, z * (e.deltaY < 0 ? 1.1 : 0.9))));
  }, []);
  const onDown = (e) => { drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; };
  const onMove = (e) => {
    if (!drag.current) return;
    setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
  };
  const onUp = () => { drag.current = null; };
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  const exportSvg = () => {
    if (!drawing?.svg) return;
    const blob = new Blob([drawing.svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(drawing.category_label || "drawing").replace(/\s+/g, "-").toLowerCase()}-GA.svg`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Layer visibility is applied as a scoped stylesheet rather than fixed CSS
  // classes, so any layer the backend adds later toggles without a UI change.
  const layerCss = [...hidden]
    .map((id) => `.studio-stage [data-layer="${id}"]{display:none}`)
    .join("");

  return (
    <div className="studio">
      <aside className="studio-side">
        <div className="studio-side-head">
          <span className="studio-badge"><PenTool size={13} strokeWidth={2} /> Drawing Studio</span>
          {drawing && <span className="studio-preview-tag">{drawing.scale}</span>}
        </div>

        {!catalog && !error && (
          <p className="studio-note"><Loader2 size={13} className="spin" /> Loading equipment catalog…</p>
        )}

        <div className="studio-chips">
          {PRESETS.map((p) => (
            <button key={p.label} type="button" className="studio-chip" onClick={() => applyPreset(p)}>
              {p.label}
            </button>
          ))}
        </div>

        {/* ---- what to draw ---- */}
        <label className="studio-label">Equipment category</label>
        <select
          className="studio-select"
          value={category}
          onChange={(e) => { setCategory(e.target.value); setValues({}); setDrawing(null); }}
        >
          {catalog?.categories?.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}{c.has_symbols ? "  •  detailed" : ""}
            </option>
          ))}
        </select>

        <div className="studio-grid2">
          <div>
            <label className="studio-label">Drawing type</label>
            <select className="studio-select" value={drawingType}
                    onChange={(e) => setDrawingType(e.target.value)}>
              {catalog?.drawing_types?.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="studio-label">Sheet</label>
            <select className="studio-select" value={sheetSize}
                    onChange={(e) => setSheetSize(e.target.value)}>
              {catalog?.sheet_sizes?.map((s) => (
                <option key={s.key} value={s.key}>{s.key}</option>
              ))}
            </select>
          </div>
        </div>

        {/* ---- inputs, rendered from the catalog ---- */}
        {activeCategory && (
          <div className="studio-section">
            <span className="studio-section-h"><Ruler size={13} strokeWidth={2} /> Inputs</span>
            <div className="studio-fields">
              {activeCategory.fields.map((f) => (
                <label key={f.key} className="studio-dim">
                  <span>
                    {f.label}{f.unit ? ` (${f.unit})` : ""}
                    {f.required && <em className="req">*</em>}
                  </span>
                  <input
                    type={f.type === "number" ? "number" : "text"}
                    value={values[f.key] ?? ""}
                    placeholder={f.required ? "required" : "optional"}
                    onChange={(e) =>
                      setValues((p) => ({ ...p, [f.key]: e.target.value }))}
                  />
                </label>
              ))}
            </div>
          </div>
        )}

        {/* ---- title block ---- */}
        <div className="studio-section">
          <span className="studio-section-h"><ListTree size={13} strokeWidth={2} /> Title block</span>
          <div className="studio-fields">
            <label className="studio-dim">
              <span>Client</span>
              <input value={client} placeholder="(to be completed)"
                     onChange={(e) => setClient(e.target.value)} />
            </label>
            <label className="studio-dim">
              <span>Drawing no.</span>
              <input value={ref} placeholder="auto"
                     onChange={(e) => setRef(e.target.value)} />
            </label>
          </div>
        </div>

        <Button variant="primary" size="sm" icon={busy ? Loader2 : Send}
                onClick={generate} disabled={busy || !category}>
          {busy ? "Generating…" : "Generate drawing"}
        </Button>
        {missingRequired.length > 0 && !drawing && (
          <p className="studio-note">
            Required inputs still empty: {missingRequired.join(", ")}. The sheet will
            schedule anything undetermined rather than guess it.
          </p>
        )}
        {error && <p className="studio-error"><AlertTriangle size={13} /> {error}</p>}

        {/* ---- layers ---- */}
        {drawing?.layers?.length > 0 && (
          <div className="studio-section">
            <span className="studio-section-h"><Layers size={13} strokeWidth={2} /> Layers</span>
            {drawing.layers.map((l) => (
              <label key={l.id} className="studio-toggle">
                <input type="checkbox" checked={!hidden.has(l.id)}
                       onChange={() => toggleLayer(l.id)} />
                <span>{l.label}</span>
              </label>
            ))}
          </div>
        )}

        {/* ---- legend ---- */}
        {drawing?.legend?.length > 0 && (
          <div className="studio-section">
            <span className="studio-section-h">Legend</span>
            {drawing.legend.map((l) => (
              <span key={l.tag} className="studio-legend-row">
                <b>{l.tag}.</b> {l.description}
              </span>
            ))}
          </div>
        )}

        {/* ---- honest gaps ---- */}
        {drawing?.tbd?.length > 0 && (
          <div className="studio-section studio-tbd">
            <span className="studio-section-h">
              <AlertTriangle size={13} strokeWidth={2} /> To be determined ({drawing.tbd.length})
            </span>
            {drawing.tbd.map((t) => <span key={t} className="studio-tbd-row">{t}</span>)}
          </div>
        )}

        {/* ---- bill of material ---- */}
        {drawing?.bom?.length > 0 && (
          <div className="studio-section">
            <span className="studio-section-h">Bill of material</span>
            {drawing.bom.map((b) => (
              <span key={b.item} className="studio-bom-row">
                <b>{b.item}</b><span>{b.spec}</span>
              </span>
            ))}
          </div>
        )}

        <div className="studio-actions">
          <Button variant="primary" size="sm" icon={Download}
                  onClick={exportSvg} disabled={!drawing}>Export SVG</Button>
          <Button variant="ghost" size="sm" disabled
                  title="DXF and PDF export arrive in the next phase">PDF / DXF</Button>
        </div>
        <p className="studio-note">
          Geometry is generated deterministically by the backend engine from the
          engineering specification. Component positions are schematic; anything
          not yet engineered is listed above and on the sheet, never guessed.
        </p>
      </aside>

      {/* canvas */}
      <div className="studio-canvas" onWheel={onWheel} onMouseDown={onDown}
           onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        <div className="studio-canvas-toolbar">
          <button type="button" onClick={() => setZoom((z) => Math.min(6, z * 1.15))} aria-label="Zoom in"><Plus size={15} /></button>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.3, z * 0.87))} aria-label="Zoom out"><Minus size={15} /></button>
          <button type="button" onClick={reset} aria-label="Reset view"><RotateCcw size={14} /></button>
          <button type="button" onClick={reset} aria-label="Fit"><Maximize2 size={14} /></button>
          <span className="studio-zoom">{Math.round(zoom * 100)}%</span>
        </div>

        {layerCss && <style>{layerCss}</style>}

        {drawing ? (
          <div
            className="studio-stage"
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            dangerouslySetInnerHTML={{ __html: drawing.svg }}
          />
        ) : (
          <div className="studio-empty">
            <PenTool size={30} strokeWidth={1.4} />
            <b>No drawing yet</b>
            <span>Pick an equipment category, enter its dimensions and generate the general arrangement.</span>
          </div>
        )}
      </div>
    </div>
  );
}
