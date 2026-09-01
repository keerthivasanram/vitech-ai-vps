import { useCallback, useMemo, useRef, useState } from "react";

/**
 * Place resolved equipment on a customer's site photograph.
 *
 * The whole page exists to collect ONE thing the backend cannot infer: a real
 * dimension. A photograph carries no scale, so until an engineer marks a
 * rectangle they measured and types its size, nothing here can be placed. The
 * step list below is not decoration — each step is a fact the geometry needs,
 * and the Place button stays disabled until they are all present, because a
 * half-scaled overlay is worse than none.
 *
 * All geometry is computed server-side in `app/siting/`. This page collects
 * clicks and renders what comes back; it never scales or projects anything
 * itself, for the same reason `lib/drawingSvg.js` was deleted — geometry living
 * in both Python and JS is precisely the drift golden rule #2 forbids.
 */

const CORNER_LABELS = ["near-left", "near-right", "far-right", "far-left"];
const MAX_MB = 12;

export function SitePlacement() {
  const [photo, setPhoto] = useState(null); // {dataUrl, base64, mime, w, h, name}
  const [corners, setCorners] = useState([]);
  const [refW, setRefW] = useState("");
  const [refD, setRefD] = useState("");
  const [vertical, setVertical] = useState([]); // [base, top]
  const [vertH, setVertH] = useState("");
  const [mode, setMode] = useState("floor"); // floor | vertical
  const [requirement, setRequirement] = useState("");
  const [posX, setPosX] = useState("");
  const [posY, setPosY] = useState("");
  const [rotation, setRotation] = useState(0);
  const [clearance, setClearance] = useState(1);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const imgRef = useRef(null);

  const onFile = useCallback((file) => {
    setError("");
    if (!file) return;
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`That photograph is larger than ${MAX_MB} MB.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
      const probe = new Image();
      probe.onload = () => {
        setPhoto({ dataUrl, base64, mime: file.type || "image/jpeg",
                   w: probe.naturalWidth, h: probe.naturalHeight, name: file.name });
        setCorners([]);
        setVertical([]);
        setResult(null);
      };
      probe.onerror = () => setError("That file could not be read as an image.");
      probe.src = dataUrl;
    };
    reader.onerror = () => setError("That file could not be read.");
    reader.readAsDataURL(file);
  }, []);

  /* A click is recorded in the PHOTOGRAPH's own pixel coordinates, not the
     displayed ones. The image is scaled to fit the panel, so a click at 400px
     on screen is a different pixel in a 4000px-wide photo — and the homography
     is solved in the photo's frame. Getting this wrong scales every result. */
  const onClick = useCallback((e) => {
    if (!photo || !imgRef.current) return;
    const r = imgRef.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * photo.w;
    const y = ((e.clientY - r.top) / r.height) * photo.h;
    if (mode === "floor") {
      setCorners((c) => (c.length >= 4 ? [[x, y]] : [...c, [x, y]]));
    } else {
      setVertical((v) => (v.length >= 2 ? [[x, y]] : [...v, [x, y]]));
    }
    setResult(null);
  }, [photo, mode]);

  const toDisplay = useCallback((p) => {
    if (!photo) return { left: 0, top: 0 };
    return { left: `${(p[0] / photo.w) * 100}%`, top: `${(p[1] / photo.h) * 100}%` };
  }, [photo]);

  const ready = useMemo(
    () => Boolean(photo && corners.length === 4 && Number(refW) > 0 && Number(refD) > 0
                  && requirement.trim()),
    [photo, corners, refW, refD, requirement]
  );

  const place = useCallback(async () => {
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        photo_base64: photo.base64, photo_mime: photo.mime,
        image_w: photo.w, image_h: photo.h,
        reference: { points: corners, width_m: Number(refW), depth_m: Number(refD) },
        question: requirement,
        position: {
          x_m: posX === "" ? Number(refW) / 2 : Number(posX),
          y_m: posY === "" ? Number(refD) / 2 : Number(posY),
          rotation_deg: Number(rotation) || 0,
          clearance_m: Number(clearance) || 0,
        },
      };
      if (vertical.length === 2 && Number(vertH) > 0) {
        body.vertical = { base: vertical[0], top: vertical[1], height_m: Number(vertH) };
      }
      const res = await fetch("/api/siting/place", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message || "That could not be placed.");
        setResult(null);
      } else {
        setResult(data);
      }
    } catch (err) {
      setError(String(err && err.message ? err.message : err));
    } finally {
      setBusy(false);
    }
  }, [ready, photo, corners, refW, refD, requirement, posX, posY, rotation, clearance,
      vertical, vertH]);

  const download = useCallback(() => {
    if (!result?.svg) return;
    const blob = new Blob([result.svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "siting-view.svg";
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const step = !photo ? 1 : corners.length < 4 ? 2 : !(Number(refW) > 0 && Number(refD) > 0) ? 3
    : !requirement.trim() ? 4 : 5;

  return (
    <div className="siting">
      <header className="siting-head">
        <div>
          <h1>Site Placement</h1>
          <p className="siting-sub">
            Put a resolved machine on the customer&apos;s own floor, to scale and in
            perspective. Scale comes from a rectangle <strong>you</strong> measured — a
            photograph carries none of its own.
          </p>
        </div>
        {result && (
          <button type="button" className="siting-btn ghost" onClick={download}>
            Download SVG
          </button>
        )}
      </header>

      <div className="siting-grid">
        <aside className="siting-panel">
          <Step n={1} now={step} title="The photograph">
            <input
              type="file"
              accept="image/*"
              onChange={(e) => onFile(e.target.files && e.target.files[0])}
            />
            {photo && (
              <p className="siting-note">
                {photo.name} — {photo.w} × {photo.h} px
              </p>
            )}
          </Step>

          <Step n={2} now={step} title="Mark a measured floor rectangle">
            <p className="siting-note">
              Click four floor corners in order: {CORNER_LABELS.join(", ")}.
            </p>
            <div className="siting-row">
              <button
                type="button"
                className={`siting-btn ${mode === "floor" ? "" : "ghost"}`}
                onClick={() => setMode("floor")}
              >
                Mark floor ({corners.length}/4)
              </button>
              <button type="button" className="siting-btn ghost"
                      onClick={() => { setCorners([]); setResult(null); }}>
                Clear
              </button>
            </div>
          </Step>

          <Step n={3} now={step} title="What that rectangle measures">
            <div className="siting-row">
              <label>Width (m)
                <input type="number" step="0.01" value={refW}
                       onChange={(e) => setRefW(e.target.value)} />
              </label>
              <label>Depth (m)
                <input type="number" step="0.01" value={refD}
                       onChange={(e) => setRefD(e.target.value)} />
              </label>
            </div>
            <p className="siting-note">
              These two numbers are the scale of the whole photograph.
            </p>
          </Step>

          <Step n={4} now={step} title="The equipment">
            <input
              type="text"
              placeholder="paint booth 5m x 3m x 4m liquid"
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
            />
            <p className="siting-note">
              The size comes from the resolved specification, not from this box — so the
              siting view can never show a machine the spec does not describe.
            </p>
          </Step>

          <Step n={5} now={step} title="Height reference (optional)">
            <p className="siting-note">
              Click the base then the top of something vertical you know the height of — a
              shutter, a column. <strong>Without it the footprint is drawn and the height
              is not</strong>: a photo cannot be scaled vertically without one.
            </p>
            <div className="siting-row">
              <button
                type="button"
                className={`siting-btn ${mode === "vertical" ? "" : "ghost"}`}
                onClick={() => setMode("vertical")}
              >
                Mark vertical ({vertical.length}/2)
              </button>
              <label>Height (m)
                <input type="number" step="0.01" value={vertH}
                       onChange={(e) => setVertH(e.target.value)} />
              </label>
            </div>
          </Step>

          <Step n={6} now={step} title="Where it stands">
            <div className="siting-row">
              <label>X (m)
                <input type="number" step="0.1" value={posX} placeholder="centre"
                       onChange={(e) => setPosX(e.target.value)} />
              </label>
              <label>Y (m)
                <input type="number" step="0.1" value={posY} placeholder="centre"
                       onChange={(e) => setPosY(e.target.value)} />
              </label>
            </div>
            <div className="siting-row">
              <label>Rotation (°)
                <input type="number" step="15" value={rotation}
                       onChange={(e) => setRotation(e.target.value)} />
              </label>
              <label>Clearance (m)
                <input type="number" step="0.1" value={clearance}
                       onChange={(e) => setClearance(e.target.value)} />
              </label>
            </div>
            <p className="siting-note">
              Position is yours, not the platform&apos;s — services, access and fire routes
              are not in a photograph.
            </p>
          </Step>

          <button type="button" className="siting-btn primary" disabled={!ready || busy}
                  onClick={place}>
            {busy ? "Placing…" : "Place on site"}
          </button>
          {error && <p className="siting-error">{error}</p>}
          {result && (
            <div className={`siting-verdict ${result.fits ? "ok" : "bad"}`}>
              {result.fits
                ? "FITS the measured floor area"
                : `DOES NOT FIT — ${(result.problems || []).join("; ")}`}
              {(result.notes || []).map((n) => (
                <p key={n} className="siting-note">{n}</p>
              ))}
            </div>
          )}
        </aside>

        <section className="siting-stage">
          {!photo && (
            <div className="siting-empty">
              <p>Upload a photograph of the customer&apos;s floor to begin.</p>
            </div>
          )}

          {photo && !result && (
            <div className="siting-canvas" onClick={onClick}>
              <img ref={imgRef} src={photo.dataUrl} alt="Site" />
              {corners.map((p, i) => (
                <span key={`c${i}`} className="siting-mark floor" style={toDisplay(p)}>
                  {i + 1}
                </span>
              ))}
              {vertical.map((p, i) => (
                <span key={`v${i}`} className="siting-mark vert" style={toDisplay(p)}>
                  {i === 0 ? "B" : "T"}
                </span>
              ))}
            </div>
          )}

          {result && (
            <div className="siting-result">
              {/* The sheet is returned as one self-contained SVG with the photo
                  embedded, so what is shown here is byte-identical to what
                  downloads and to what the artifact digest covers. */}
              <div dangerouslySetInnerHTML={{ __html: result.svg }} />
              <button type="button" className="siting-btn ghost"
                      onClick={() => setResult(null)}>
                Back to marking
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Step({ n, now, title, children }) {
  const state = n < now ? "done" : n === now ? "active" : "todo";
  return (
    <div className={`siting-step ${state}`}>
      <h2><span className="siting-step-n">{n}</span>{title}</h2>
      {children}
    </div>
  );
}
