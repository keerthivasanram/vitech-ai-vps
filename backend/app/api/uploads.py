"""File uploads (the extraction pipeline is a later phase)."""
from fastapi import APIRouter
from .. import config
from fastapi import File
from fastapi import UploadFile
from pathlib import Path
import shutil

router = APIRouter()


# --- file uploads (extraction pipeline is the next phase) -------------------
UPLOAD_DIR = config.BASE_DIR / "uploads"
_KIND = {"pdf": "PDF document", "dxf": "CAD (DXF)", "dwg": "CAD (DWG)",
         "png": "Image", "jpg": "Image", "jpeg": "Image",
         "xlsx": "Spreadsheet", "docx": "Document"}


def _file_kind(name: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return _KIND.get(ext, (ext.upper() + " file") if ext else "File")


@router.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)):
    """Store an uploaded offer/CAD file. Automatic extraction is a later phase —
    for now the file is saved and queued."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / Path(file.filename).name       # strip any path components
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
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
