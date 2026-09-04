"""File uploads (the extraction pipeline is a later phase)."""
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config

router = APIRouter()


# --- file uploads (extraction pipeline is the next phase) -------------------
UPLOAD_DIR = config.BASE_DIR / "uploads"
# `_KIND` is BOTH the display label and the accepted-type allow-list. Keeping
# one table means a type can never be accepted but unlabelled, or labelled but
# refused.
_KIND = {"pdf": "PDF document", "dxf": "CAD (DXF)", "dwg": "CAD (DWG)",
         "png": "Image", "jpg": "Image", "jpeg": "Image",
         "xlsx": "Spreadsheet", "docx": "Document"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
_CHUNK = 1024 * 1024


def _file_kind(name: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return _KIND.get(ext, (ext.upper() + " file") if ext else "File")


@router.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)):
    """Store an uploaded offer/CAD file. Automatic extraction is a later phase —
    for now the file is saved and queued.

    LIMITS (readiness review S6). The route is administrator-only, so this is
    not an anonymous surface, but it had no size cap and no type allow-list:
    one request could fill the disk that Postgres, the vector store and the
    artifact store all sit on, and take the platform down by way of a
    write failure somewhere else entirely.

    The extension list is an ALLOW-list, not a deny-list. `_KIND` below existed
    already but only labelled a file for display — it never decided whether to
    accept one, which is the kind of near-miss that reads as a control and is
    not.
    """
    name = Path(file.filename or "").name               # strip path components
    if not name:
        raise HTTPException(status_code=400, detail="A filename is required.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext not in _KIND:
        raise HTTPException(
            status_code=415,
            detail=(f"'{ext or name}' is not an accepted file type. "
                    f"Accepted: {', '.join(sorted(_KIND))}."))

    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / name
    # Streamed in bounded chunks and stopped AT the ceiling — reading the whole
    # upload to measure it would already have paid the cost the cap exists to
    # avoid. A partial file is removed rather than left looking like a real one.
    written = 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(_CHUNK):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB "
                                "limit (set MAX_UPLOAD_MB to change it)."))
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    return {"ok": True, "filename": dest.name, "size": dest.stat().st_size,
            "kind": _file_kind(dest.name), "status": "uploaded"}


@router.get("/api/uploads")
def list_uploads():
    UPLOAD_DIR.mkdir(exist_ok=True)
    files = []
    for p in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            files.append({"filename": p.name, "size": p.stat().st_size,
                          "kind": _file_kind(p.name), "status": "uploaded"})
    return {"count": len(files), "files": files}
