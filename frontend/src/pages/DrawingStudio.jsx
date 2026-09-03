import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Bot, ChevronDown, ClipboardPaste, Download, Expand,
  FileText, Layers, ListPlus, Minus, PanelLeft, PanelLeftClose, PanelRight,
  PanelRightClose, PenTool, Plus, Scan, Send, Shrink, Trash2, User,
} from "lucide-react";
import { agentUrl } from "../lib/constants";
import { sanitizeAgentReply } from "../lib/agentReply";
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
const MIN_ZOOM = 0.05;
const MAX_ZOOM = 8;
/* CSS resolves 1mm as 96/25.4 px, so a sheet sized in millimetres renders at
   true printed size when the scale factor is 1. That is what makes the zoom
   readout mean something: 100% is A3 at A3, not "as wide as the panel". */
const MM_PX = 96 / 25.4;
/* Breathing room left around the sheet when fitting it to the viewport. */
const FIT_PAD = 24;
// Zoom response per pixel of wheel travel. A mouse notch is 120 px, so this is
// a ~4% step: deliberately gentle, because a 10-15% step compounded past 300%
// in a dozen turns and made the sheet impossible to hold steady.
const ZOOM_SENSITIVITY = 0.00033;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** The sheet's true size in mm, read from the SVG's own viewBox. */
function sheetSizeMm(svg) {
  const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg || "");
  return m ? { w: parseFloat(m[1]), h: parseFloat(m[2]) } : null;
}

/**
 * One starting point per catalog category, each carrying that category's REQUIRED
 * inputs so a click always produces a drawable sheet rather than a prompt for more
 * information. Previously only two existed, which made the studio look as though
 * paint booths and scrubbers were the only equipment it could draw — the category
 * dropdown has always been catalog-driven and offered all fourteen.
 *
 * The values are ordinary starting sizes to be edited, never engineering advice.
 */
const PRESETS = [
  { label: "Paint booth", hint: "5 × 3 × 4 m, liquid", category: "paint_booth",
    values: { length_m: 5, width_m: 3, height_m: 4, paint_type: "liquid" } },
  { label: "Wet scrubber", hint: "800 CFM, 750 mm tower", category: "wet_scrubber",
    values: { air_volume_cfm: 800, tower_diameter_mm: 750, qty: 1 } },
  // Duty-specified categories are sized by airflow or track length, not by an
  // L/W/H in their profile, so a preset that gave only the duty produced a
  // correct but VIEWLESS sheet. Each therefore also carries the studio's
  // optional overall-size inputs — the casing//envelope the client states — which
  // are drawing inputs only and never enter the catalog profile.
  { label: "Dust collector", hint: "6000 m³/h, 2.5 × 1.2 × 1.2 m", category: "dust_collector",
    values: { air_volume_cmh: 6000, dust_type: "dry industrial dust",
              length_m: 2.5, width_m: 1.2, height_m: 1.2 } },
  { label: "Powder coating plant", hint: "3 × 2 × 2.5 m component", category: "powder_coating_plant",
    values: { length_m: 3, width_m: 2, height_m: 2.5, booth_type: "dry down draft",
              painting_method: "manual", throughput: "100 components/shift" } },
  { label: "Hot air oven", hint: "3 × 2 × 2 m, 200 °C", category: "hot_air_oven",
    values: { length_m: 3, width_m: 2, height_m: 2, operating_temp: "200" } },
  { label: "Paint drying oven", hint: "4 × 2 × 2.5 m", category: "paint_drying_oven",
    values: { length_m: 4, width_m: 2, height_m: 2.5 } },
  { label: "Pretreatment plant", hint: "6 × 2 × 2 m, 7 tank", category: "pretreatment_plant",
    values: { length_m: 6, width_m: 2, height_m: 2, process_stages: "7 tank",
              throughput: "100 components/shift" } },
  { label: "Cleaning room", hint: "4 × 3 × 3 m", category: "cleaning_room",
    values: { length_m: 4, width_m: 3, height_m: 3 } },
  { label: "Buffing booth", hint: "3 × 2 × 2.5 m", category: "buffing_booth",
    values: { length_m: 3, width_m: 2, height_m: 2.5 } },
  { label: "Flash off zone", hint: "4 × 2 × 2.5 m", category: "flash_off_zone",
    values: { length_m: 4, width_m: 2, height_m: 2.5 } },
  { label: "Blast booth", hint: "5 × 3 × 3 m, steel grit", category: "blast_booth",
    values: { length_m: 5, width_m: 3, height_m: 3, blast_media: "steel grit",
              recovery_type: "mechanical" } },
  { label: "Fume extraction", hint: "4000 m³/h, welding", category: "fume_extraction",
    values: { air_volume_cmh: 4000, source_process: "welding", capture_points: "4",
              length_m: 2, width_m: 1.2, height_m: 2.5 } },
  { label: "Conveyor", hint: "overhead, 35 m track", category: "conveyor",
    values: { conveyor_type: "overhead", track_length_m: 35, load_capacity: "500 kg",
              length_m: 35, width_m: 0.6, height_m: 3 } },
  { label: "Ducting", hint: "6000 m³/h, 20 m run", category: "ducting",
    values: { air_volume_cmh: 6000, layout_length_m: 20, material: "MS 2mm" } },
];

// Chat starters. The last two demonstrate CORRECTION, which is the studio's
// least discoverable capability: a follow-up amends the sheet as a new revision
// instead of starting a fresh drawing.
const SUGGESTIONS = [
  "draw a paint booth 6m x 4m x 3m",
  "dust collector 6000 cmh pulse jet",
  "powder coating plant component 3m x 2m x 2.5m",
  "change the length to 8m",
  "make it 9000 cmh instead",
];

/** A collapsible parameter section. The panel carries a lot of ground now, so
 *  each concern folds away rather than forcing a long scroll. */
function Group({ icon: Icon, title, count, open, onToggle, children }) {
  return (
    <section className={`ds-group${open ? "" : " is-closed"}`}>
      <button type="button" className="ds-group-h is-btn" onClick={onToggle}
              aria-expanded={open}>
        {Icon && <Icon size={12} strokeWidth={2} />}
        <span dangerouslySetInnerHTML={{ __html: title }} />
        {count !== undefined && <span className="ds-count">{count}</span>}
        <ChevronDown className="ds-caret" size={13} strokeWidth={2} />
      </button>
      {open && <div className="ds-group-body">{children}</div>}
    </section>
  );
}

/** One catalog-driven input. */
function Field({ f, values, setValues }) {
  return (
    <label className="ds-field">
      <span>
        {f.label}{f.unit ? ` (${f.unit})` : ""}
        {f.required && <em className="req">*</em>}
      </span>
      <input className="ds-input" type={f.type === "number" ? "number" : "text"}
             value={values[f.key] ?? ""}
             placeholder={f.required ? "required" : "optional"}
             onChange={(e) => setValues((p) => ({ ...p, [f.key]: e.target.value }))} />
    </label>
  );
}

export function DrawingStudio() {
  const [catalog, setCatalog] = useState(null);
  const [category, setCategory] = useState("");
  const [drawingType, setDrawingType] = useState("ga");
  const [sheetSize, setSheetSize] = useState("A3");
  const [values, setValues] = useState({});
  const [client, setClient] = useState("");
  const [ref, setRef] = useState("");

  const [drawnBy, setDrawnBy] = useState("");
  const [checkedBy, setCheckedBy] = useState("");
  const [project, setProject] = useState("");
  const [specText, setSpecText] = useState("");
  const [extraRows, setExtraRows] = useState([]);

  /**
   * REVISIONS. A new drawing never replaces the last one — it is appended as
   * the next revision, and the strip over the canvas keeps every earlier sheet
   * one click away. Engineering review is iterative, and "alter it" must not
   * mean "lose what we had". Each entry keeps its own `source` so an old
   * revision can still be exported to DXF/PDF exactly as it was drawn.
   */
  const [revisions, setRevisions] = useState([]);
  const [activeRev, setActiveRev] = useState(-1);
  const drawing = activeRev >= 0 ? revisions[activeRev]?.drawing ?? null : null;
  const source = activeRev >= 0 ? revisions[activeRev]?.source ?? null : null;

  const [exporting, setExporting] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(() => new Set());

  // Zoom and translation live together: zoom-to-cursor computes the new pan
  // from the new zoom, and two separate setState calls read a stale partner.
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const drag = useRef(null);
  const viewportRef = useRef(null);
  const rootRef = useRef(null);

  /* The studio lays itself out from ITS OWN width, not the window's.
     Media queries got this wrong in a way that was easy to miss: at a 1280px
     window the app's navigation rail is already taking 264px, so the studio
     had ~1000px and still tried to hold two side rails and a canvas — the
     sheet fitted at 24% and was unreadable. */
  const [deck, setDeck] = useState(1400);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return undefined;
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setDeck(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Below ~1180 the assistant stacks under the drawing; below ~900 so do the
  // parameters, because a canvas narrower than that cannot show a sheet.
  const layout = deck < 900 ? "is-stack" : deck < 1180 ? "is-narrow" : "is-wide";

  const [chat, setChat] = useState([]);
  const [ask, setAsk] = useState("");
  const [thinking, setThinking] = useState(false);
  const chatId = useRef(`studio-${Math.random().toString(36).slice(2, 10)}`);
  const logEnd = useRef(null);

  /* The two rails collapse so the sheet can own the window. Remembered,
     because which rails an engineer wants open is a working preference, not a
     per-visit decision. */
  const [railL, setRailL] = useState(() => localStorage.getItem("vitech_ds_l") !== "0");
  /* The assistant starts CLOSED. It was 320px of mostly empty rail on open —
     one paragraph at the top, a composer at the bottom — and it was taking a
     third of the width away from the sheet, which is the thing this screen is
     for. It is one click away in the toolbar and stays open once opened. */
  const [railR, setRailR] = useState(() => localStorage.getItem("vitech_ds_r") === "1");
  const toggleRailL = () => setRailL((v) => { localStorage.setItem("vitech_ds_l", v ? "0" : "1"); return !v; });
  const toggleRailR = () => setRailR((v) => { localStorage.setItem("vitech_ds_r", v ? "0" : "1"); return !v; });

  /* The panel used to be one accordion of nine sections, so the category
     selector sat below fourteen preset cards and the layer switches below
     everything. Three tabs give each concern a home at the top of the panel. */
  const [tab, setTab] = useState("setup");

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

  const required = useMemo(
    () => (activeCategory?.fields || []).filter((f) => f.required), [activeCategory]);
  const optional = useMemo(
    () => (activeCategory?.fields || []).filter((f) => !f.required), [activeCategory]);

  const [open, setOpen] = useState({
    required: true, optional: true, extra: false, spec: false, title: false,
  });
  const toggle = (k) => setOpen((p) => ({ ...p, [k]: !p[k] }));

  /** Append a drawing as the next revision and make it the active one. */
  const pushRevision = useCallback((d, req, label) => {
    setRevisions((prev) => {
      const next = [...prev, { drawing: d, source: req, label, at: Date.now() }];
      setActiveRev(next.length - 1);
      return next;
    });
    setHidden(new Set());
  }, []);

  // The title block's REV cell shows the revision this sheet actually is, so a
  // printed or exported drawing is self-describing away from the studio.
  const titleFields = useCallback(() => ({
    client, ref, drawn: drawnBy, checked: checkedBy,
    title: project, rev: String(revisions.length),
    // The sheet carries its own revision history, so a printed or exported
    // drawing says what changed without the studio open beside it.
    revisions: revisions.map((r, i) => ({
      rev: String(i), description: r.label,
      date: new Date(r.at).toLocaleDateString("en-GB"),
    })),
  }), [client, ref, drawnBy, checkedBy, project, revisions]);

  const generate = useCallback(async (override) => {
    if (!category) return;
    setBusy(true); setError("");
    // `override` exists for the edit-as-inputs path: React state has not
    // committed yet at the moment an edit is applied, so the new value is
    // passed in directly rather than read back a tick later.
    const vals = override && !override.nativeEvent ? override : values;
    const req = {
      category, values: vals, sheet_size: sheetSize, drawing_type: drawingType,
      extra_rows: extraRows.filter((r) => r.label.trim() && r.value.trim()),
      ...titleFields(),
    };
    try {
      const res = await fetch("/api/drawing/render", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      const d = await res.json();
      if (!d.ok) setError(d.error || "The drawing could not be generated.");
      else pushRevision(d, req, activeCategory?.label || category);
    } catch { setError("Could not reach the drawing engine."); }
    finally { setBusy(false); }
  }, [category, values, sheetSize, drawingType, extraRows, titleFields,
      pushRevision, activeCategory]);

  /**
   * EDIT AS INPUTS, which is the whole point of this interaction.
   *
   * Clicking a dimension on the sheet does NOT edit the sheet. It opens the
   * REQUIREMENT FIELD that produced that dimension, and committing a value
   * re-runs the engine — so every other number on the drawing follows from the
   * change, as engineering rather than as typing. A hand-edited sheet would be
   * a drawing no engine agrees with, and the moment one exists nobody can tell
   * which numbers were engineered and which were typed over.
   *
   * The dimensions carry `data-edit` naming the envelope axis they measure.
   * ONLY the overall dimensions carry it: those map one-to-one onto an input.
   * A component dimension has no input to send the reader to, and making it
   * look clickable would promise an edit the engine cannot honour.
   */
  const AXIS_INPUT = { length: "length_m", width: "width_m", height: "height_m" };
  const [edit, setEdit] = useState(null);

  const onSheetClick = useCallback((e) => {
    const hit = e.target?.closest?.("[data-edit]");
    if (!hit) { setEdit(null); return; }
    const axis = hit.getAttribute("data-edit");
    const key = AXIS_INPUT[axis];
    if (!key) return;
    const field = (activeCategory?.fields || []).find((f) => f.key === key);
    const box = hit.getBoundingClientRect();
    setEdit({
      axis, key,
      label: field?.label || `Overall ${axis}`,
      unit: field?.unit || "m",
      value: values[key] ?? "",
      x: box.left + box.width / 2, y: box.top,
    });
  }, [activeCategory, values]);

  const commitEdit = useCallback(() => {
    if (!edit) return;
    const next = { ...values, [edit.key]: edit.value };
    setValues(next);
    setEdit(null);
    generate(next);
  }, [edit, values, generate]);

  /** Draw a generated engineering specification exactly as it stands. */
  const generateFromSpec = useCallback(async () => {
    if (!specText.trim()) return;
    setBusy(true); setError("");
    const req = { spec: specText, sheet_size: sheetSize, ...titleFields() };
    try {
      const res = await fetch("/api/drawing/from-spec", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      const d = await res.json();
      if (!d.ok) setError(d.error || "That specification could not be drawn.");
      else pushRevision(d, req, `${d.category_label} (from spec)`);
    } catch { setError("Could not reach the drawing engine."); }
    finally { setBusy(false); }
  }, [specText, sheetSize, titleFields, pushRevision]);

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
      setChat((c) => [...c, { role: "agent", text: sanitizeAgentReply(
        d.text || d.answer || "(no reply)",
        (raw) => console.warn("[agent] tool-call mechanics suppressed:", raw)) }]);
      if (drew) {
        const req = { question: drew.toolInput?.question || q, sheet_size: sheetSize };
        const r = await fetch("/api/tools/drawing", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req),
        });
        const dr = await r.json();
        // A chat-driven change is a REVISION too, so asking the assistant to
        // alter something never discards the sheet it started from.
        if (dr.ok && dr.svg) pushRevision(dr, req, q.slice(0, 42));
      }
    } catch { setChat((c) => [...c, { role: "agent", text: "Could not reach the Drawing Agent." }]); }
    finally { setThinking(false); }
  }, [ask, thinking, sheetSize, pushRevision]);

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
  const nudge = (f) => setView((v) => ({ ...v, zoom: clamp(v.zoom * f, MIN_ZOOM, MAX_ZOOM) }));

  /* The sheet is laid out at its TRUE millimetre size, so it has a fixed
     pixel footprint the viewport can be measured against. */
  const sheetMm = useMemo(() => sheetSizeMm(drawing?.svg), [drawing]);

  /**
   * FIT — the control this viewport did not have.
   *
   * "Reset to 100%" used to mean "the sheet is as wide as the stage", which on
   * a tall viewport left the drawing floating in half a screen of nothing and
   * on a short one cropped it. Fit measures the viewport and scales the sheet
   * to it, which is what every CAD package means by the word.
   */
  const fit = useCallback(() => {
    const el = viewportRef.current;
    if (!el || !sheetMm) { setView({ zoom: 1, x: 0, y: 0 }); return; }
    const box = el.getBoundingClientRect();
    const zoom = clamp(
      Math.min((box.width - FIT_PAD * 2) / (sheetMm.w * MM_PX),
               (box.height - FIT_PAD * 2) / (sheetMm.h * MM_PX)),
      MIN_ZOOM, MAX_ZOOM);
    setView({ zoom, x: 0, y: 0 });
  }, [sheetMm]);

  /* Refit whenever the sheet changes or the space around it does — collapsing
     a rail or entering focus mode gives the viewport a different shape, and a
     sheet that stayed at the old scale would be the obvious wrong answer. */
  useEffect(() => { fit(); }, [fit, railL, railR, focus]);
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => fit());
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  /* F fits, 0 goes to true printed size. Both ignored while typing. */
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.tagName === "SELECT") return;
      if (e.key === "f" || e.key === "F") { e.preventDefault(); fit(); }
      if (e.key === "0") { e.preventDefault(); setView({ zoom: 1, x: 0, y: 0 }); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fit]);

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


  const sheetCount = drawing?.views?.length ?? 0;

  return (
    <div ref={rootRef}
         className={`ds ${layout}${railL ? "" : " no-l"}${railR ? "" : " no-r"}`}>
      {/* ---------------- top toolbar ----------------
          One dense strip, CAD-fashion: identity, what is on the sheet, the
          layout switches and the export cluster. The scale / sheet / TBD chips
          that used to sit here are gone — they were a second copy of the
          status bar under the drawing, which is where a draughtsman reads
          them. */}
      <header className="ds-bar">
        <button type="button" className="ds-tbtn" onClick={toggleRailL}
                title={railL ? "Hide parameters" : "Show parameters"}
                aria-pressed={railL} aria-label={railL ? "Hide parameters" : "Show parameters"}>
          {railL ? <PanelLeftClose size={16} /> : <PanelLeft size={16} />}
        </button>

        <span className="ds-bar-brand"><PenTool size={15} strokeWidth={2} /> Drawing Studio</span>

        {drawing ? (
          <span className="ds-bar-doc">
            <b>{drawing.category_label}</b>
            <i>·</i>{drawing.sheet_size}
            <i>·</i>{drawing.scale}
            <i>·</i>Rev {activeRev}
          </span>
        ) : (
          <span className="ds-bar-sub">Deterministic 2D general arrangement</span>
        )}

        <div className="ds-bar-spacer" />

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
        </div>

        <i className="ds-bar-sep" />

        <button type="button" className="ds-tbtn" onClick={() => setFocus((f) => !f)}
                title={focus ? "Exit expanded view (Esc)" : "Expand workspace"}
                aria-label={focus ? "Exit focus mode" : "Enter focus mode"}>
          {focus ? <Shrink size={16} /> : <Expand size={16} />}
        </button>
        <button type="button" className="ds-tbtn" onClick={toggleRailR}
                title={railR ? "Hide assistant" : "Show assistant"}
                aria-pressed={railR} aria-label={railR ? "Hide assistant" : "Show assistant"}>
          {railR ? <PanelRightClose size={16} /> : <PanelRight size={16} />}
        </button>
      </header>

      {/* ---------------- parameters ---------------- */}
      {railL && (
      <aside className="ds-panel ds-params">
        {/* Tabs, not one nine-section scroll: the category selector used to sit
            below fourteen preset cards and the layer switches below everything
            else, so the two controls used most were the two hardest to reach. */}
        <div className="ds-tabs" role="tablist" aria-label="Parameter sections">
          {[["setup", "Setup"], ["detail", "Detail"], ["sheet", "Sheet"]].map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k}
                    className={`ds-tab${tab === k ? " is-on" : ""}`}
                    onClick={() => setTab(k)}>
              {label}
              {k === "sheet" && drawing?.tbd?.length > 0 && (
                <span className="ds-tab-dot" title={`${drawing.tbd.length} to be determined`} />
              )}
            </button>
          ))}
        </div>

        <div className="ds-panel-body">
          {tab === "setup" && (
            <>
              <section className="ds-group">
                <div className="ds-group-h">Equipment</div>
                <label className="ds-field">
                  <span>Category</span>
                  <select className="ds-select" value={category}
                          onChange={(e) => { setCategory(e.target.value); setValues({}); setError(""); }}>
                    {catalog?.categories?.map((c) => (
                      <option key={c.key} value={c.key}>{c.label}{c.has_symbols ? " — detailed" : ""}</option>
                    ))}
                  </select>
                </label>
                {/* Full width, not a half each: "General Arrangement (3 views)"
                    truncated to "General Arrangeme…" in half a 268px rail, and
                    the half it was sharing held three characters. */}
                <label className="ds-field">
                  <span>Drawing type</span>
                  <select className="ds-select" value={drawingType} onChange={(e) => setDrawingType(e.target.value)}>
                    {catalog?.drawing_types?.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                  </select>
                </label>
                <label className="ds-field">
                  <span>Sheet size</span>
                  <select className="ds-select" value={sheetSize} onChange={(e) => setSheetSize(e.target.value)}>
                    {catalog?.sheet_sizes?.map((s) => (
                      <option key={s.key} value={s.key}>{s.label || s.key}</option>
                    ))}
                  </select>
                </label>
                {/* Presets are a one-line starting point rather than fourteen
                    cards: they seed a category's required inputs, and after the
                    first use nobody needs to see the whole catalogue again. */}
                <label className="ds-field">
                  <span>Start from a typical size</span>
                  <select className="ds-select" value=""
                          onChange={(e) => {
                            const pre = PRESETS.find((x) => x.label === e.target.value);
                            if (!pre) return;
                            setCategory(pre.category); setValues(pre.values); setError("");
                          }}>
                    <option value="">Choose a starting point…</option>
                    {PRESETS.map((pre) => (
                      <option key={pre.label} value={pre.label}>{pre.label} — {pre.hint}</option>
                    ))}
                  </select>
                </label>
              </section>

              {/* Required and optional inputs are separated: what the engine
                  NEEDS to size the equipment should not be buried among
                  nice-to-haves. */}
              {activeCategory && required.length > 0 && (
                <Group title="Required inputs" count={required.length}
                       open={open.required} onToggle={() => toggle("required")}>
                  <div className="ds-grid2">
                    {required.map((f) => <Field key={f.key} f={f} values={values} setValues={setValues} />)}
                  </div>
                </Group>
              )}

              {activeCategory && optional.length > 0 && (
                <Group title="Process &amp; options" count={optional.length}
                       open={open.optional} onToggle={() => toggle("optional")}>
                  <div className="ds-grid2">
                    {optional.map((f) => <Field key={f.key} f={f} values={values} setValues={setValues} />)}
                  </div>
                  {optional.some((f) => f.drawing_only) && (
                    <p className="ds-note">
                      Overall sizes are drawing inputs for equipment specified by duty
                      rather than size. Leave them blank and the sheet schedules them
                      as TBD instead of guessing.
                    </p>
                  )}
                </Group>
              )}
            </>
          )}

          {tab === "detail" && (
            <>
              {/* Manually entered specification lines. These are the engineer's
                  own stated values, carried as "From Requirement" — never
                  dressed up as something the engine calculated. */}
              <Group icon={ListPlus} title="Additional specification" count={extraRows.length}
                     open={open.extra} onToggle={() => toggle("extra")}>
                {extraRows.map((r, i) => (
                  <div key={i} className="ds-pair">
                    <input className="ds-input" placeholder="Parameter" value={r.label}
                           onChange={(e) => setExtraRows((p) => p.map((x, j) =>
                             j === i ? { ...x, label: e.target.value } : x))} />
                    <input className="ds-input" placeholder="Value" value={r.value}
                           onChange={(e) => setExtraRows((p) => p.map((x, j) =>
                             j === i ? { ...x, value: e.target.value } : x))} />
                    <button type="button" className="ds-icon-btn" aria-label="Remove line"
                            onClick={() => setExtraRows((p) => p.filter((_, j) => j !== i))}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
                <button type="button" className="ds-btn is-block"
                        onClick={() => setExtraRows((p) => [...p, { label: "", value: "" }])}>
                  <Plus size={13} strokeWidth={2} /> Add specification line
                </button>
                <p className="ds-note">
                  Anything added here is recorded as a stated value, not a calculated
                  one, and appears in the sheet's bill of material.
                </p>
              </Group>

              {/* Draw an existing specification exactly as written. */}
              <Group icon={ClipboardPaste} title="From a specification"
                     open={open.spec} onToggle={() => toggle("spec")}>
                <textarea className="ds-textarea" rows={6} value={specText}
                          placeholder="Paste a generated engineering specification here…"
                          onChange={(e) => setSpecText(e.target.value)} />
                <button type="button" className="ds-btn is-block" disabled={busy || !specText.trim()}
                        onClick={generateFromSpec}>
                  <FileText size={13} strokeWidth={2} /> Draw this specification
                </button>
                <p className="ds-note">
                  Draws the specification as it stands — every reviewed value and
                  every accepted TBD — rather than re-deriving it.
                </p>
              </Group>

              <Group icon={FileText} title="Title block"
                     open={open.title} onToggle={() => toggle("title")}>
                <label className="ds-field"><span>Project / drawing title</span>
                  <input className="ds-input" value={project} placeholder="auto from equipment"
                         onChange={(e) => setProject(e.target.value)} /></label>
                <div className="ds-grid2">
                  <label className="ds-field"><span>Client</span>
                    <input className="ds-input" value={client} placeholder="(to be completed)"
                           onChange={(e) => setClient(e.target.value)} /></label>
                  <label className="ds-field"><span>Drawing no.</span>
                    <input className="ds-input" value={ref} placeholder="auto"
                           onChange={(e) => setRef(e.target.value)} /></label>
                  <label className="ds-field"><span>Drawn by</span>
                    <input className="ds-input" value={drawnBy} placeholder="Vitech AI"
                           onChange={(e) => setDrawnBy(e.target.value)} /></label>
                  <label className="ds-field"><span>Checked by</span>
                    <input className="ds-input" value={checkedBy} placeholder="(engineer)"
                           onChange={(e) => setCheckedBy(e.target.value)} /></label>
                </div>
                <p className="ds-note">
                  The sheet is stamped <b>Rev {revisions.length}</b> and marked DRAFT
                  until an engineer signs it off.
                </p>
              </Group>
            </>
          )}

          {tab === "sheet" && (
            drawing ? (
              <>
                {drawing.layers?.length > 0 && (
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

                {/* The engine returns each unresolved parameter WITH the action
                    that clears it and who owns it. A bare list of gaps tells a
                    reader what is missing; this tells them what to do, and
                    whether it is theirs to do or the customer's. Falls back to
                    the plain list for an older response. */}
                {drawing.unresolved?.length > 0 ? (
                  <section className="ds-group">
                    <div className="ds-group-h"><AlertTriangle size={12} strokeWidth={2} /> Required to complete
                      <span className="ds-count">{drawing.unresolved.length}</span></div>
                    <div className="ds-list">
                      {drawing.unresolved.map((u, i) => (
                        <div key={`${u.parameter}-${i}`} className={`ds-unres is-${u.kind}`}>
                          <div className="ds-unres-h">
                            <b>{u.parameter}</b>
                            <span className="ds-unres-status">{u.status}</span>
                          </div>
                          <span className="ds-unres-act">{u.action}</span>
                        </div>
                      ))}
                    </div>
                    <p className="ds-note">
                      Geometry items block a dimensioned drawing; the rest enrich it.
                      Anything marked for the customer is their process input, not ours
                      to assume.
                    </p>
                  </section>
                ) : drawing.tbd?.length > 0 && (
                  <section className="ds-group">
                    <div className="ds-group-h"><AlertTriangle size={12} strokeWidth={2} /> To be determined
                      <span className="ds-count">{drawing.tbd.length}</span></div>
                    <div className="ds-list">
                      {drawing.tbd.map((t) => <div key={t} className="ds-row is-tbd"><span>{t}</span></div>)}
                    </div>
                  </section>
                )}

                {drawing.legend?.length > 0 && (
                  <section className="ds-group">
                    <div className="ds-group-h">Legend<span className="ds-count">{drawing.legend.length}</span></div>
                    <div className="ds-list">
                      {drawing.legend.map((l) => (
                        <div key={l.tag} className="ds-row">
                          <span className="ds-tag">{l.tag}</span><span>{l.description}</span>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {drawing.bom?.length > 0 && (
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
                  listed here and on the sheet, never guessed.
                </p>
              </>
            ) : (
              <p className="ds-note">
                Layers, the legend, the bill of material and anything left to be
                determined are listed here once a sheet has been drawn.
              </p>
            )
          )}

          {error && <div className="ds-alert"><AlertTriangle size={14} /> <span>{error}</span></div>}
        </div>

        <div className="ds-panel-foot">
          {busy && <div className="ds-progress"><i /></div>}
          <button type="button" className="ds-btn is-primary is-block" onClick={() => generate()} disabled={busy || !category}>
            <Send size={14} strokeWidth={2} /> {busy ? "Generating…" : "Generate drawing"}
          </button>
          {missingRequired.length > 0 && !drawing && (
            <p className="ds-note">
              {missingRequired.join(", ")} still empty — the sheet will schedule
              anything undetermined rather than guess it.
            </p>
          )}
        </div>
      </aside>
      )}

      {/* ---------------- viewport ---------------- */}
      <section className="ds-viewport" ref={viewportRef}
               onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
        {layerCss && <style>{layerCss}</style>}

        {drawing && (
          <div className="ds-stage">
            <div className="ds-sheet is-editable"
                 onClick={onSheetClick}
                 style={{
                   width: sheetMm ? `${sheetMm.w}mm` : "100%",
                   height: sheetMm ? `${sheetMm.h}mm` : "100%",
                   transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom}) translate(-50%, -50%)`,
                 }}
                 dangerouslySetInnerHTML={{ __html: drawing.svg }} />
          </div>
        )}

        {/* The sheet's own claim about itself, over the canvas. A schematic
            says NOT FOR FABRICATION on the paper; without this the studio
            around it said nothing, so the state was invisible until you read
            the drawing. */}
        {drawing?.state && drawing.state !== "fully_dimensioned" && (
          <div className={`ds-state is-${drawing.state}`}>
            <AlertTriangle size={13} strokeWidth={2} />
            <div>
              <b>{drawing.state_label}</b>
              {drawing.missing_axes?.length > 0 && (
                <span> — overall {drawing.missing_axes.join(", ")} not yet engineered</span>
              )}
            </div>
          </div>
        )}

        {/* Editing a dimension edits the INPUT behind it, never the sheet. */}
        {edit && (
          <div className="ds-edit" style={{ left: edit.x, top: edit.y }}
               onClick={(e) => e.stopPropagation()}>
            <div className="ds-edit-h">{edit.label}</div>
            <div className="ds-edit-row">
              <input className="ds-input" autoFocus type="number" step="any"
                     value={edit.value}
                     onChange={(e) => setEdit((p) => ({ ...p, value: e.target.value }))}
                     onKeyDown={(e) => {
                       if (e.key === "Enter") commitEdit();
                       if (e.key === "Escape") setEdit(null);
                     }} />
              <span className="ds-edit-unit">{edit.unit}</span>
            </div>
            <div className="ds-edit-acts">
              <button type="button" className="ds-btn is-primary" onClick={commitEdit}>
                Apply &amp; re-resolve
              </button>
              <button type="button" className="ds-btn" onClick={() => setEdit(null)}>Cancel</button>
            </div>
            <p className="ds-edit-note">
              Changes the requirement and re-runs the engine. The sheet is never
              edited directly.
            </p>
          </div>
        )}

        {!drawing && (
          <div className="ds-empty">
            <div className="ds-empty-icon"><PenTool size={22} strokeWidth={1.6} /></div>
            <h4>No drawing yet</h4>
            <p>
              Set the equipment and its dimensions on the left, then Generate.
              {!railR && <> Or describe it in words — open the
              <button type="button" className="ds-link" onClick={toggleRailR}>Drawing Assistant</button>
              and try <kbd>draw a paint booth 5m x 3m x 4m</kbd>.</>}
            </p>
          </div>
        )}

        {/* Revision strip: every sheet generated this session, newest last.
            Small and out of the way — it is a way back, not the subject. */}
        {revisions.length > 0 && (
          <div className="ds-revs" role="tablist" aria-label="Drawing revisions">
            {revisions.map((r, i) => (
              <button key={r.at} type="button" role="tab"
                      className={`ds-rev${i === activeRev ? " is-on" : ""}`}
                      aria-selected={i === activeRev}
                      onClick={() => { setActiveRev(i); setHidden(new Set()); }}
                      title={`Rev ${i}: ${r.label}`}>
                <span className="ds-rev-thumb"
                      dangerouslySetInnerHTML={{ __html: r.drawing.svg }} />
                <span className="ds-rev-n">{i}</span>
              </button>
            ))}
          </div>
        )}

        <div className="ds-tools">
          <button type="button" onClick={() => nudge(1 / 1.25)} title="Zoom out" aria-label="Zoom out"><Minus size={15} /></button>
          <button type="button" className="ds-zoom" onClick={() => setView((v) => ({ ...v, zoom: 1 }))}
                  title="True printed size (0)">{Math.round(view.zoom * 100)}%</button>
          <button type="button" onClick={() => nudge(1.25)} title="Zoom in" aria-label="Zoom in"><Plus size={15} /></button>
          <i className="sep" />
          <button type="button" onClick={fit} title="Fit sheet to view (F)" aria-label="Fit sheet to view"><Scan size={15} /></button>
        </div>

        {/* Status bar — the draughtsman's read-out, spanning the foot of the
            canvas rather than floating in a corner of it. */}
        <div className="ds-status">
          {drawing ? (
            <>
              <b>{drawing.category_label}</b>
              <i className="sep" /><span>Scale <b>{drawing.scale}</b></span>
              <i className="sep" /><span>Sheet <b>{drawing.sheet_size}</b></span>
              <i className="sep" />
              <span>{env?.length
                ? <>Envelope <b>{env.length} × {env.width} × {env.height}</b> mm</>
                : <>Envelope <b>not determined</b></>}</span>
              <i className="sep" /><span>{sheetCount} view{sheetCount === 1 ? "" : "s"}</span>
              {drawing.tbd?.length > 0 && (
                <><i className="sep" /><span className="warn">{drawing.tbd.length} TBD</span></>
              )}
              <span className="ds-status-r">Rev {activeRev} of {revisions.length - 1}</span>
            </>
          ) : (
            <span>Ready — scroll to zoom, drag to pan, <b>F</b> to fit</span>
          )}
        </div>
      </section>

      {/* ---------------- AI assistant ---------------- */}
      {railR && (
      <aside className="ds-panel ds-ai">
        <div className="ds-panel-head">
          <Bot size={14} strokeWidth={2} /><h3>Drawing Assistant</h3>
          <div className="ds-bar-spacer" />
          {thinking && <span className="ds-chip is-live">working</span>}
        </div>

        <div className="ds-ai-log">
          {chat.length === 0 && !thinking && (
            <>
              <div className="ds-msg agent">
                <span className="ds-msg-av"><Bot size={13} strokeWidth={2} /></span>
                <div className="ds-msg-body">
                  <p>Describe the equipment and I'll draw its general arrangement. Dimensions,
                     scale and bill of material come from the engineering engine, so nothing
                     here is estimated.</p>
                </div>
              </div>
              {/* The starters sat pinned above the composer with the whole rail
                  empty between them and the one message above. They belong with
                  the sentence that invites them. */}
              <div className="ds-suggest">
                {SUGGESTIONS.map((sug) => (
                  <button key={sug} type="button" onClick={() => sendChat(sug)}>{sug}</button>
                ))}
              </div>
            </>
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
      )}
    </div>
  );
}
