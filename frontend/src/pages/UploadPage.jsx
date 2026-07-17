import { useCallback, useEffect, useState } from "react";
import { UploadCloud } from "lucide-react";
import { fileSize } from "../lib/format";

const STEPS = ["Upload", "Extract (OCR / parse)", "Engineer review", "Into Knowledge Base"];

/** Add offer PDFs and CAD drawings. Files are stored; extraction is next phase. */
export function UploadPage() {
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetch("/api/uploads")
      .then((r) => r.json())
      .then((d) => setFiles(d.files || []))
      .catch(() => {});
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const upload = useCallback(async (list) => {
    setBusy(true);
    for (const f of list) {
      const fd = new FormData();
      fd.append("file", f);
      try { await fetch("/api/uploads", { method: "POST", body: fd }); }
      catch { /* one bad file shouldn't abort the batch */ }
    }
    setBusy(false);
    refresh();
  }, [refresh]);

  return (
    <div className="page-inner">
      <header className="page-head">
        <h1>Documents</h1>
        <p>
          Add offer PDFs and CAD drawings. Files are stored now; <b>automatic extraction into
          the Knowledge Base is the next phase</b> — uploads are queued for it.
        </p>
      </header>

      <label
        className={`dropzone${drag ? " is-over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (e.dataTransfer.files?.length) upload(e.dataTransfer.files);
        }}
      >
        <input
          type="file"
          multiple
          hidden
          onChange={(e) => e.target.files?.length && upload(e.target.files)}
        />
        <UploadCloud size={30} strokeWidth={1.8} className="dz-ic" aria-hidden="true" />
        <span className="dz-t">{busy ? "Uploading…" : "Drag files here, or click to browse"}</span>
        <span className="dz-s">PDF · DXF · DWG · images</span>
      </label>

      <div className="pipeline">
        {STEPS.map((s, i) => (
          <div key={s} className={`pl-step${i === 0 ? " is-done" : ""}`}>
            <span className="pl-n">{i + 1}</span>
            <span>{s}</span>
            {i < STEPS.length - 1 && <span className="pl-arrow" aria-hidden="true">→</span>}
          </div>
        ))}
      </div>
      <p className="pl-note">
        Steps 2–4 arrive with the data-extraction pipeline (PDF parsing + CAD OCR →
        engineer review → normalized database).
      </p>

      {files.length > 0 && (
        <div className="up-list">
          <div className="up-list-h">Uploaded files ({files.length})</div>
          {files.map((f) => (
            <div className="up-row" key={f.filename}>
              <span className="up-name" title={f.filename}>{f.filename}</span>
              <span className="up-kind">{f.kind}</span>
              <span className="up-size">{fileSize(f.size)}</span>
              <span className="badge warn">queued for extraction</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
