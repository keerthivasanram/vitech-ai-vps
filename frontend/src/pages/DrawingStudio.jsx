import { useCallback, useMemo, useRef, useState } from "react";
import {
  Download, Layers, Maximize2, Minus, PenTool, Plus, RotateCcw, Ruler, Send,
} from "lucide-react";
import { Button } from "../common/Button";
import { buildDrawingSvg, parseEnvelope, tbdList } from "../lib/drawingSvg";

/**
 * Drawing Studio — split controls + live GA canvas.
 *
 * Frontend preview: the drawing is generated deterministically client-side
 * (see lib/drawingSvg) from the dimensions you type, so the studio is real and
 * usable now. When the backend `generate_drawing` engine + Flowise Drawing Agent
 * land (see docs/drawing-agent-plan.md), swap the SVG source for the tool
 * response — this UI (canvas, pan/zoom, layers, export) stays unchanged.
 */
const LAYERS = [
  { id: "envelope", label: "Envelope" },
  { id: "dimensions", label: "Dimensions" },
  { id: "titleblock", label: "Title block" },
  { id: "grid", label: "Grid" },
];

export function DrawingStudio() {
  const [prompt, setPrompt] = useState("");
  const [env, setEnv] = useState(() => parseEnvelope("wet scrubber 3 x 1.5 x 4 m"));
  const [layers, setLayers] = useState({ envelope: true, dimensions: true, titleblock: true, grid: true });

  // pan/zoom on the canvas
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef(null);

  const svg = useMemo(() => buildDrawingSvg(env, { ref: "VT/DRG/PREVIEW" }), [env]);
  const tbds = useMemo(() => tbdList(env), [env]);

  const generate = useCallback((text) => {
    const t = (text ?? prompt).trim();
    if (!t) return;
    setEnv(parseEnvelope(t));
    setZoom(1); setPan({ x: 0, y: 0 });
  }, [prompt]);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    setZoom((z) => Math.min(4, Math.max(0.4, z * (e.deltaY < 0 ? 1.1 : 0.9))));
  }, []);
  const onDown = (e) => { drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }; };
  const onMove = (e) => {
    if (!drag.current) return;
    setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
  };
  const onUp = () => { drag.current = null; };
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  const exportSvg = () => {
    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(env.label || "drawing").replace(/\s+/g, "-").toLowerCase()}-GA.svg`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const hideClass = LAYERS.filter((l) => !layers[l.id]).map((l) => `hide-${l.id}`).join(" ");

  return (
    <div className="studio">
      {/* controls */}
      <aside className="studio-side">
        <div className="studio-side-head">
          <span className="studio-badge"><PenTool size={13} strokeWidth={2} /> Drawing Studio</span>
          <span className="studio-preview-tag">Preview</span>
        </div>

        <label className="studio-label">Describe the equipment</label>
        <div className="studio-prompt">
          <input
            className="studio-input"
            placeholder="wet scrubber 3 x 1.5 x 4 m"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && generate()}
          />
          <button type="button" className="studio-send" onClick={() => generate()} aria-label="Generate drawing">
            <Send size={16} strokeWidth={1.9} />
          </button>
        </div>
        <div className="studio-chips">
          {["wet scrubber 3 x 1.5 x 4 m", "paint booth 5 x 3 x 4 m", "hot air oven 2 x 2 x 2.5 m"].map((c) => (
            <button key={c} type="button" className="studio-chip" onClick={() => { setPrompt(c); generate(c); }}>{c}</button>
          ))}
        </div>

        <div className="studio-dims">
          {[["length", "Length"], ["width", "Width"], ["height", "Height"]].map(([k, lbl]) => (
            <label key={k} className="studio-dim">
              <span>{lbl} (mm)</span>
              <input
                type="number"
                value={env[k] ?? ""}
                placeholder="TBD"
                onChange={(e) => setEnv((p) => ({ ...p, [k]: e.target.value === "" ? null : Math.round(+e.target.value) }))}
              />
            </label>
          ))}
        </div>

        <div className="studio-section">
          <span className="studio-section-h"><Layers size={13} strokeWidth={2} /> Layers</span>
          {LAYERS.map((l) => (
            <label key={l.id} className="studio-toggle">
              <input type="checkbox" checked={layers[l.id]} onChange={(e) => setLayers((p) => ({ ...p, [l.id]: e.target.checked }))} />
              <span>{l.label}</span>
            </label>
          ))}
        </div>

        {tbds.length > 0 && (
          <div className="studio-section studio-tbd">
            <span className="studio-section-h"><Ruler size={13} strokeWidth={2} /> To be determined</span>
            {tbds.map((t) => <span key={t} className="studio-tbd-row">{t}</span>)}
          </div>
        )}

        <div className="studio-actions">
          <Button variant="primary" size="sm" icon={Download} onClick={exportSvg}>Export SVG</Button>
          <Button variant="ghost" size="sm" onClick={() => {}} disabled title="Arrives with the backend engine">PDF / DXF</Button>
        </div>
        <p className="studio-note">
          Preview drawings are generated in-browser from the dimensions above.
          Full GA output (DXF/PDF, component symbols, BOM) arrives with the
          Drawing Agent backend.
        </p>
      </aside>

      {/* canvas */}
      <div className="studio-canvas" onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        <div className="studio-canvas-toolbar">
          <button type="button" onClick={() => setZoom((z) => Math.min(4, z * 1.15))} aria-label="Zoom in"><Plus size={15} /></button>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.4, z * 0.87))} aria-label="Zoom out"><Minus size={15} /></button>
          <button type="button" onClick={reset} aria-label="Reset view"><RotateCcw size={14} /></button>
          <button type="button" onClick={reset} aria-label="Fit"><Maximize2 size={14} /></button>
          <span className="studio-zoom">{Math.round(zoom * 100)}%</span>
        </div>
        <div
          className={`studio-stage ${hideClass}`}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
