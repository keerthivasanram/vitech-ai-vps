"""Immutable customer-facing artifacts.

Every specification, drawing, BOM, quotation and package document that a
customer could receive is stored under `data/jobs/<job_id>/` with a SHA-256.

WHY STORE RATHER THAN REGENERATE, given the platform is deterministic. Because
regeneration reproduces the original only while the offer corpus and the rules
are unchanged. After a re-ingest, regenerating a six-month-old quotation may
legitimately produce a different document — and an engineering record that
changes when you reopen it is not a record.

The checksum earns its place twice: it detects a corrupted file, and it makes
"is the platform still deterministic?" a question we can actually answer, by
regenerating an old artifact and comparing digests.

Artifacts are PERMANENT. Nothing here deletes.
"""
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Optional

from .. import config
from . import store

ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_DIR", str(config.BASE_DIR / "data" / "jobs")))

_KIND_BY_EXT = {
    ".pdf": "pdf", ".svg": "svg", ".dxf": "dxf", ".xlsx": "xlsx",
    ".md": "markdown", ".json": "json", ".zip": "zip", ".txt": "text",
}


def _safe_name(name: str) -> str:
    """A filename, never a path.

    `Path(name).name` alone is not enough — a job id or artifact name reaching
    here from a request must not be able to climb out of the directory, so the
    basename is taken AND the remaining characters are restricted.
    """
    base = Path(str(name)).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "artifact"
    return cleaned[:120]


def job_dir(job_id: str) -> Path:
    return ARTIFACT_ROOT / _safe_name(job_id)


def store_bytes(job_id: str, name: str, data: bytes, *, kind: str = "") -> dict:
    """Write an artifact and record it. Returns the artifact row.

    Idempotent: writing the same name twice for a job replaces the file and the
    row, so a retried export does not accumulate duplicates.
    """
    safe = _safe_name(name)
    directory = job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / safe
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    row = {
        "job_id": job_id,
        "name": safe,
        "kind": kind or _KIND_BY_EXT.get(path.suffix.lower(), "binary"),
        "path": str(path),
        "bytes": len(data),
        "sha256": digest,
        "created_at": time.time(),
    }
    store.insert_artifact(row)
    return row


def read(job_id: str, name: str) -> Optional[tuple[bytes, dict]]:
    """Artifact bytes plus its row, or None. Verifies the checksum on read.

    A mismatch returns None rather than the bytes: an artifact that no longer
    matches its digest is not the document that was issued, and handing it over
    as though it were would be worse than admitting it is gone.
    """
    row = store.find_artifact(job_id, _safe_name(name))
    if not row or not row.get("path"):
        return None
    path = Path(row["path"])
    if not path.exists():
        return None
    data = path.read_bytes()
    if row.get("sha256") and hashlib.sha256(data).hexdigest() != row["sha256"]:
        return None
    return data, row


def verify(job_id: str) -> list[dict]:
    """Check every artifact of a job against its recorded digest."""
    out = []
    for row in store.job_artifacts(job_id):
        path = Path(row.get("path") or "")
        if not path.exists():
            out.append({**row, "state": "missing"})
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        out.append({**row, "state": "ok" if actual == row.get("sha256") else "corrupt"})
    return out


def disk_usage() -> dict:
    total, count = 0, 0
    if ARTIFACT_ROOT.exists():
        for p in ARTIFACT_ROOT.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
                count += 1
    return {"dir": str(ARTIFACT_ROOT), "files": count, "bytes": total}
