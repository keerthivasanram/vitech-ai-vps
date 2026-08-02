import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Box, Bot, Download, Expand, FileText, Layers, Maximize2,
  Minus, Package, PenTool, Plus, Ruler, Send, Shrink, Sparkles, User, Wrench,
} from "lucide-react";
import { agentUrl } from "../lib/constants";
import { Answer } from "../lib/markdown";

/**
 * Drawing Studio — a CAD workspace, not a form.
 *
 * Three columns: parameters, the drawing viewport (the primary surface), and
 * the AI assistant. The drawing itself always comes from the BACKEND engine —
 * `/api/drawing/render` for the form, `/api/tools/drawing` for the agent — so
 * nothing about the geometry is computed in the browser. This file collects
 * inputs, renders the returned SVG and owns view state only.
 *
 * The form is DATA-DRIVEN from `GET /api/drawing/catalog`: categories, their
 * input fields, drawing types and sheet sizes all come from the backend, so a
 * category added server-side appears here with no change to this file.
 */
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 8;
// Zoom response per pixel of wheel travel. A mouse notch is 120 px, so this is
// a ~4% step: deliberately gentle, because a 10-15% step compounded past 300%
// in a dozen turns and made the sheet impossible to hold steady.
const ZOOM_SENSITIVITY = 0.00033;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

const PRESETS = [
  { label: "Paint booth", hint: "5 × 3 × 4 m, liquid", category: "paint_booth",
    values: { length_m: 5, width_m: 3, height_m: 4, paint_type: "liquid" } },
  { label: "Wet scrubber", hint: "800 CFM, 750 mm tower", category: "wet_scrubber",
    values: { air_volume_cfm: 800, tower_diameter_mm: 750, qty: 1 } },
];

const SUGGESTIONS = [
  "draw a paint booth 6m x 4m x 3m",
  "wet scrubber 800 cfm 750 mm tower",
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
  // How the CURRENT drawing was asked for (studio form or chat requirement),
  // replayed to the export endpoint so DXF/PDF rebuild the identical sheet.
  const [source, setSource] = useState(null);
  const [exporting, setExporting] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(() => new Set());

  // Zoom and translation live together: zoom-to-cursor computes the new pan
  // from the new zoom, and two separate setState calls read a stale partner.
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const drag = useRef(null);
  const viewportRef = useRef(null);

  const [chat, setChat] = useState([]);
  const [ask, setAsk] = useState("");
  const [thinking, setThinking] = useState(false);
  const chatId = useRef(`studio-${Math.random().toString(36).slice(2, 10)}`);
  const logEnd = useRef(null);

  const [focus, setFocus] = useState(false);
  useEffect(() => {
    document.body.classList.toggle("studio-focus", focus);
    return () => document.body.classList.remove("studio-focus");
  }, [focus]);
  useEffect(() => {
    if (!focus) return undefined;
    const onKey = (e) => e.key === "Escape" && setFocus(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus]);

  useEffect(() => { logEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" }); },
    [chat, thinking]);

  useEffect(() => {
    let alive = true;
    fetch("/api/drawing/catalog")
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        setCatalog(d);
        setSheetSize(d.default_sheet || "A3");
        if (d.categories?.[0]) { setCategory(d.categories[0].key); setValues({}); }
      })
      .catch(() => alive && setError("Could not load the equipment catalog. Is the backend running?"));
    return () => { alive = false; };
  }, []);

  const activeCategory = useMemo(
    () => catalog?.categories?.find((c) => c.key === category) || null, [catalog, category]);

  const missingRequired = useMemo(() => (activeCategory?.fields || [])
    .filter((f) => f.required && !String(values[f.key] ?? "").trim())
    .map((f) => f.label), [activeCategory, values]);

  const generate = useCallback(async () => {
    if (!category) return;
    setBusy(true); setError("");
    const req = { category, values, sheet_size: sheetSize, drawing_type: drawingType, client, ref };
    try {
      const res = await fetch("/api/drawing/render", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      const d = await res.json();
      if (!d.ok) { setError(d.error || "The drawing could not be generated."); setDrawing(null); setSource(null); }
      else { setDrawing(d); setSource(req); setHidden(new Set()); setView({ zoom: 1, x: 0, y: 0 }); }
    } catch { setError("Could not reach the drawing engine."); }
    finally { setBusy(false); }
  }, [category, values, sheetSize, drawingType, client, ref]);

  /**
   * The agent replies in prose and never carries the drawing — the tool strips
   * the SVG before the model sees it, because vector data would swamp an 8B
   * context. So when it reports drawing something, the viewport is refreshed
   * from the SAME requirement through the deterministic endpoint; agent and
   * canvas therefore cannot disagree.
   */
  const sendChat = useCallback(async (text) => {
    const q = (text ?? ask).trim();
    if (!q || thinking) return;
    setAsk("");
    setChat((c) => [...c, { role: "user", text: q }]);
    setThinking(true);
    try {
      const res = await fetch(agentUrl("drawing"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, chatId: chatId.current }),
      });
      const d = await res.json();
      const drew = (d.usedTools || []).find((u) => u.tool === "generate_drawing");
      setChat((c) => [...c, { role: "agent", text: d.text || d.answer || "(no reply)" }]);
      if (drew) {
        const req = { question: drew.toolInput?.question || q, sheet_size: sheetSize };
        const r = await fetch("/api/tools/drawing", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req),
        });
        const dr = await r.json();
        if (dr.ok && dr.svg) {
          setDrawing(dr); setSource(req); setHidden(new Set()); setView({ zoom: 1, x: 0, y: 0 });
        }
      }
    } catch { setChat((c) => [...c, { role: "agent", text: "Could not reach the Drawing Agent." }]); }
    finally { setThinking(false); }
  }, [ask, thinking, sheetSize]);

  // React attaches wheel handlers PASSIVELY, so preventDefault inside an onWheel
  // prop is ignored and floods the console. Registering it natively with
  // passive:false is the only way to zoom without also scrolling the page.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      const delta = clamp(e.deltaY * unit, -120, 120);
      const step = Math.exp(-delta * ZOOM_SENSITIVITY);
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left - rect.width / 2;
      const cy = e.clientY - rect.top - rect.height / 2;
      setView((v) => {
        const zoom = clamp(v.zoom * step, MIN_ZOOM, MAX_ZOOM);
        const k = zoom / v.zoom;
        return { zoom, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onDown = (e) => { if (e.button === 0) drag.current = { x: e.clientX - view.x, y: e.clientY - view.y }; };
  const onMove = (e) => { if (drag.current) setView((v) => ({ ...v, x: e.clientX - drag.current.x, y: e.clientY - drag.current.y })); };
  const onUp = () => { drag.current = null; };
  const fit = () => setView({ zoom: 1, x: 0, y: 0 });
  const nudge = (f) => setView((v) => ({ ...v, zoom: clamp(v.zoom * f, MIN_ZOOM, MAX_ZOOM) }));

  const toggleLayer = (id) => setHidden((p) => {
    const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const download = (blob, name) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    a.click(); URL.revokeObjectURL(url);
  };

  /**
   * DXF and PDF are produced by the backend from the SAME compose() the canvas
   * renders, so an exported sheet can never disagree with the approved one.
   * `source` records how the current drawing was requested (studio form or a
   * chat requirement) and is replayed verbatim to the export endpoint.
   */
  const exportAs = useCallback(async (fmt) => {
    if (!drawing) return;
    const stem = `${(drawing.category_label || "drawing").replace(/\s+/g, "-").toLowerCase()}-GA`;
    if (fmt === "svg") {                       // already in hand, byte-identical
      download(new Blob([drawing.svg], { type: "image/svg+xml" }), `${stem}.svg`);
      return;
    }
    if (!source) { setError("Regenerate the drawing before exporting it."); return; }
    setExporting(fmt); setError("");
    try {
      const res = await fetch("/api/drawing/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...source, format: fmt }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.error || `The ${fmt.toUpperCase()} export failed.`);
        return;
      }
      download(await res.blob(), `${stem}.${fmt}`);
    } catch { setError(`Could not reach the export service for ${fmt.toUpperCase()}.`); }
    finally { setExporting(""); }
  }, [drawing, source]);

  // Applied as a scoped stylesheet so a layer the backend adds later toggles
  // without any change here.
  const layerCss = [...hidden].map((id) => `.ds-stage [data-layer="${id}"]{display:none}`).join("");
  const env = drawing?.envelope_mm;

  return (
    <div className="ds">
      {/* ---------------- top toolbar ---------------- */}
      <header className="ds-bar">
        <span className="ds-bar-brand"><PenTool size={16} strokeWidth={2} /> Drawing Studio</span>
        <span className="ds-bar-sub">Deterministic 2D general arrangement</span>
        <div className="ds-bar-spacer" />
        {drawing && (
          <div className="ds-bar-group">
            <span className="ds-chip is-live">{drawing.scale}</span>
            <span className="ds-chip">{drawing.sheet_size}</span>
            {drawing.tbd?.length > 0 && <span className="ds-chip is-warn">{drawing.tbd.length} TBD</span>}
          </div>
        )}
        <div className="ds-bar-group ds-export">
          <span className="ds-export-label"><Download size={14} strokeWidth={2} /> Export</span>
          {["svg", "dxf", "pdf"].map((fmt) => (
            <button key={fmt} type="button" className="ds-btn is-fmt"
                    onClick={() => exportAs(fmt)}
                    disabled={!drawing || !!exporting}
                    title={fmt === "dxf" ? "DXF R12 for AutoCAD / LibreCAD"
                           : fmt === "pdf" ? "True-size vector PDF for printing"
                           : "Scalable vector graphic"}>
              {exporting === fmt ? "…" : fmt.toUpperCase()}
            </button>
          ))}
          <button type="button" className="ds-btn is-icon" onClick={() => setFocus((f) => !f)}
                  title={focus ? "Exit expanded view (Esc)" : "Expand workspace"}
                  aria-label={focus ? "Exit focus mode" : "Enter focus mode"}>
            {focus ? <Shrink size={15} /> : <Expand size={15} />}
          </button>
        </div>
      </header>

      {/* ---------------- parameters ---------------- */}
      <aside className="ds-panel ds-params">
        <div className="ds-panel-head"><Wrench size={14} strokeWidth={2} /><h3>Parameters</h3></div>

        <div className="ds-panel-body">
          <section className="ds-group">
            <div className="ds-group-h"><Sparkles size={12} strokeWidth={2} /> Quick start</div>
            <div className="ds-presets">
              {PRESETS.map((p) => (
                <button key={p.label} type="button" className="ds-preset"
                        onClick={() => { setCategory(p.category); setValues(p.values); setDrawing(null); }}>
                  <Box size={15} strokeWidth={1.9} />
                  <span>{p.label}<small>{p.hint}</small></span>
                </button>
              ))}
            </div>
          </section>

          <section className="ds-group">
            <div className="ds-group-h"><Package size={12} strokeWidth={2} /> Equipment</div>
            <label className="ds-field">
              <span>Category</span>
              <select className="ds-select" value={category}
                      onChange={(e) => { setCategory(e.target.value); setValues({}); setDrawing(null); }}>
                {catalog?.categories?.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}{c.has_symbols ? " — detailed" : ""}</option>
                ))}
              </select>
            </label>
            <div className="ds-grid2">
              <label className="ds-field">
                <span>Drawing type</span>
                <select className="ds-select" value={drawingType} onChange={(e) => setDrawingType(e.target.value)}>
                  {catalog?.drawing_types?.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </label>
              <label className="ds-field">
                <span>Sheet</span>
                <select className="ds-select" value={sheetSize} onChange={(e) => setSheetSize(e.target.value)}>
                  {catalog?.sheet_sizes?.map((s) => <option key={s.key} value={s.key}>{s.key}</option>)}
                </select>
              </label>
            </div>
          </section>

          {activeCategory && (
            <section className="ds-group">
              <div className="ds-group-h">
                <Ruler size={12} strokeWidth={2} /> Geometry &amp; process
                <span className="ds-count">{activeCategory.fields.length}</span>
              </div>
              <div className="ds-grid2">
                {activeCategory.fields.map((f) => (
                  <label key={f.key} className="ds-field">
                    <span>{f.label}{f.unit ? ` (${f.unit})` : ""}{f.required && <em className="req">*</em>}</span>
                    <input className="ds-input" type={f.type === "number" ? "number" : "text"}
                           value={values[f.key] ?? ""} placeholder={f.required ? "required" : "optional"}
                           onChange={(e) => setValues((p) => ({ ...p, [f.key]: e.target.value }))} />
                  </label>
                ))}
              </div>
            </section>
          )}

          <section className="ds-group">
            <div className="ds-group-h"><FileText size={12} strokeWidth={2} /> Title block</div>
            <div className="ds-grid2">
              <label className="ds-field"><span>Client</span>
                <input className="ds-input" value={client} placeholder="(to be completed)"
                       onChange={(e) => setClient(e.target.value)} /></label>
              <label className="ds-field"><span>Drawing no.</span>
                <input className="ds-input" value={ref} placeholder="auto"
                       onChange={(e) => setRef(e.target.value)} /></label>
            </div>
          </section>

          {error && <div className="ds-alert"><AlertTriangle size={14} /> <span>{error}</span></div>}

          {drawing?.layers?.length > 0 && (
            <section className="ds-group">
              <div className="ds-group-h"><Layers size={12} strokeWidth={2} /> Layers</div>
              {drawing.layers.map((l) => (
                <label key={l.id} className="ds-toggle">
                  <input type="checkbox" checked={!hidden.has(l.id)} onChange={() => toggleLayer(l.id)} />
                  <span>{l.label}</span>
                </label>
              ))}
            </section>
          )}

          {drawing?.legend?.length > 0 && (
            <section className="ds-group">
              <div className="ds-group-h">Legend</div>
              <div className="ds-list">
                {drawing.legend.map((l) => (
                  <div key={l.tag} className="ds-row">
                    <span className="ds-tag">{l.tag}</span><span>{l.description}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {drawing?.tbd?.length > 0 && (
            <section className="ds-group">
              <div className="ds-group-h"><AlertTriangle size={12} strokeWidth={2} /> To be determined
                <span className="ds-count">{drawing.tbd.length}</span></div>
              <div className="ds-list">
                {drawing.tbd.map((t) => <div key={t} className="ds-row is-tbd">— <span>{t}</span></div>)}
              </div>
            </section>
          )}

          {drawing?.bom?.length > 0 && (
            <section className="ds-group">
              <div className="ds-group-h">Bill of material<span className="ds-count">{drawing.bom.length}</span></div>
              <div className="ds-list">
                {drawing.bom.map((b) => (
                  <div key={b.item} className="ds-row"><b>{b.item}</b><span>{b.spec}</span></div>
                ))}
              </div>
            </section>
          )}

          <p className="ds-note">
            Geometry is generated deterministically by the engineering engine.
            Component positions are schematic; anything not yet engineered is
            listed above and on the sheet, never guessed.
          </p>
        </div>

        <div className="ds-panel-foot">
          {busy && <div className="ds-progress" style={{ marginBottom: 9 }}><i /></div>}
          <button type="button" className="ds-btn is-primary is-block" onClick={generate} disabled={busy || !category}>
            <Send size={14} strokeWidth={2} /> {busy ? "Generating…" : "Generate drawing"}
          </button>
          {missingRequired.length > 0 && !drawing && (
            <p className="ds-note" style={{ marginTop: 8 }}>
              {missingRequired.join(", ")} still empty — the sheet will schedule
              anything undetermined rather than guess it.
            </p>
          )}
        </div>
      </aside>

      {/* ---------------- viewport ---------------- */}
      <section className="ds-viewport" ref={viewportRef}
               onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        <div className="ds-tools">
          <button type="button" onClick={() => nudge(1 / 1.2)} title="Zoom out" aria-label="Zoom out"><Minus size={15} /></button>
          <button type="button" className="ds-zoom" onClick={fit} title="Reset to 100%">{Math.round(view.zoom * 100)}%</button>
          <button type="button" onClick={() => nudge(1.2)} title="Zoom in" aria-label="Zoom in"><Plus size={15} /></button>
          <i className="sep" />
          <button type="button" onClick={fit} title="Fit to view" aria-label="Fit to view"><Maximize2 size={14} /></button>
          <i className="sep" />
          <button type="button" className={focus ? "is-on" : ""} onClick={() => setFocus((f) => !f)}
                  title={focus ? "Exit expanded view (Esc)" : "Expand workspace"}
                  aria-label={focus ? "Exit focus mode" : "Enter focus mode"}>
            {focus ? <Shrink size={15} /> : <Expand size={15} />}
          </button>
        </div>

        {layerCss && <style>{layerCss}</style>}

        {drawing ? (
          <>
            <div className="ds-stage"
                 style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }}
                 dangerouslySetInnerHTML={{ __html: drawing.svg }} />
            <div className="ds-status">
              <b>{drawing.category_label}</b><i className="sep" />
              <span>Scale <b>{drawing.scale}</b></span><i className="sep" />
              <span>Sheet <b>{drawing.sheet_size}</b></span><i className="sep" />
              <span>{env?.length
                ? <>Envelope <b>{env.length} × {env.width} × {env.height}</b> mm</>
                : <>Envelope <b>not determined</b></>}</span>
              <i className="sep" />
              <span>{drawing.views.length} view{drawing.views.length === 1 ? "" : "s"}</span>
              {drawing.tbd?.length > 0 && <><i className="sep" /><span className="warn">{drawing.tbd.length} TBD</span></>}
            </div>
          </>
        ) : (
          <div className="ds-empty">
            <div className="ds-empty-icon"><PenTool size={26} strokeWidth={1.6} /></div>
            <h4>No drawing yet</h4>
            <p>
              Set the equipment and its dimensions on the left, or just ask the
              assistant — try <kbd>draw a paint booth 5m x 3m x 4m</kbd>.
            </p>
          </div>
        )}
      </section>

      {/* ---------------- AI assistant ---------------- */}
      <aside className="ds-panel ds-ai">
        <div className="ds-panel-head">
          <Bot size={14} strokeWidth={2} /><h3>Drawing Assistant</h3>
          <div className="ds-bar-spacer" />
          {thinking && <span className="ds-chip is-live">working</span>}
        </div>

        <div className="ds-ai-log">
          {chat.length === 0 && !thinking && (
            <div className="ds-msg agent">
              <span className="ds-msg-av"><Bot size={13} strokeWidth={2} /></span>
              <div className="ds-msg-body">
                <p>Describe the equipment and I'll draw its general arrangement. Dimensions,
                   scale and bill of material come from the engineering engine, so nothing
                   here is estimated.</p>
              </div>
            </div>
          )}
          {chat.map((m, i) => (
            <div key={i} className={`ds-msg ${m.role}`}>
              <span className="ds-msg-av">
                {m.role === "user" ? <User size={13} strokeWidth={2} /> : <Bot size={13} strokeWidth={2} />}
              </span>
              <div className="ds-msg-body">
                {m.role === "user" ? <p>{m.text}</p> : <Answer text={m.text} />}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="ds-msg agent">
              <span className="ds-msg-av"><Bot size={13} strokeWidth={2} /></span>
              <div className="ds-msg-body"><span className="ds-typing"><span /><span /><span /></span></div>
            </div>
          )}
          <div ref={logEnd} />
        </div>

        <div className="ds-composer">
          {chat.length === 0 && (
            <div className="ds-suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => sendChat(s)}>{s}</button>
              ))}
            </div>
          )}
          <div className="ds-composer-in">
            <input value={ask} placeholder="Ask the Drawing Assistant…"
                   onChange={(e) => setAsk(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && sendChat()} />
            <button type="button" className="ds-send" onClick={() => sendChat()}
                    disabled={thinking || !ask.trim()} aria-label="Send">
              <Send size={14} strokeWidth={2} />
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
