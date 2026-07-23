"""Production document ingestion: loader -> chunker -> rich metadata -> Chroma.

For every file it:
  1. extracts structure-preserving blocks (pages, tables, prose),
  2. resolves metadata from three layers (explicit > body text > filename),
  3. chunks by section (tables kept whole), tagging each chunk with
     customer / project / equipment_type / doc_category / revision /
     offer_number / date / page / section, so the Engineering Agent can
     FILTER on any of them before semantic search,
  4. upserts into the SAME Chroma collection the offer records live in, under
     type="document" — additive, never touching the ATS spec engine (which
     only reasons over type="offer"),
  5. returns an IngestReport per file flagging every low-confidence field, so
     an engineer reviews before the data is trusted (human-in-the-loop).

Usage:
    cd backend
    python -m rag.ingest <file-or-dir> [--customer X] [--equipment-type wet_scrubber]
                                       [--project P] [--doc-category offer]
                                       [--manifest overrides.json] [--reset]
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import loader, metadata as md
from .chunker import chunk_blocks
from .embedding import get_collection

DOC_TYPE = "document"

# Metadata fields promoted to top-level Chroma metadata for $and filtering.
FILTERABLE = ("customer", "project", "equipment_type", "doc_category",
              "revision", "offer_number", "date")


@dataclass
class FileReport:
    source_file: str
    fields: dict[str, Any]
    field_source: dict[str, str]
    chunks: int = 0
    tables: int = 0
    pages: int | None = None
    sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _title(fields: dict[str, Any], filename_meta: dict[str, Any], stem: str) -> str:
    # ASCII only (CLAUDE.md gotcha: no em-dashes in text bound for PDF/console).
    parts = [fields.get("customer"),
             filename_meta.get("equipment_text") or fields.get("equipment_type")]
    label = " - ".join(p for p in parts if p)
    return label or stem


def _resolve_metadata(path: Path, full_text: str,
                      explicit: dict[str, Any]) -> tuple[dict, dict, dict]:
    filename_meta = md.parse_filename(path.name)
    body_meta = md.extract_body_metadata(full_text)
    merged = md.merge_metadata(explicit=explicit, body=body_meta, filename=filename_meta)
    field_source = merged.pop("_meta_source", {})
    return merged, field_source, filename_meta


def _warnings(fields: dict[str, Any], field_source: dict[str, str]) -> list[str]:
    warns = []
    for key in ("customer", "equipment_type", "date"):
        if not fields.get(key):
            warns.append(f"{key} unresolved")
        elif field_source.get(key) == "filename":
            warns.append(f"{key} from filename only (verify)")
    if fields.get("date_raw") and not fields.get("date"):
        warns.append(f"date '{fields['date_raw']}' could not be normalised")
    return warns


def _chunk_record(chunk, fields: dict[str, Any], title: str,
                  source_file: str, idx: int, total: int) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "id": f"doc-{Path(source_file).stem}-{idx}",
        "type": DOC_TYPE,
        "title": title,
        "source_file": source_file,
        "chunk_index": idx,
        "chunk_count": total,
        "kind": chunk.kind,
        "text": chunk.text,
    }
    if chunk.page is not None:
        rec["page"] = chunk.page
    if chunk.section:
        rec["section"] = chunk.section
    for key in FILTERABLE:
        if fields.get(key):
            rec[key] = fields[key]
    return rec


def _flatten_metadata(record: dict[str, Any]) -> dict[str, Any]:
    meta = {"_raw": json.dumps(record, ensure_ascii=False)}
    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)) and value != "":
            meta[key] = value
    return meta


def ingest_file(path: Path, *, explicit: dict[str, Any] | None = None,
                collection=None) -> tuple[int, FileReport]:
    collection = collection or get_collection()
    blocks = loader.load_blocks(path)
    full_text = "\n".join(b.text for b in blocks)

    fields, field_source, filename_meta = _resolve_metadata(path, full_text, explicit or {})
    title = _title(fields, filename_meta, path.stem)
    chunks = chunk_blocks(blocks)

    ids, docs, metas = [], [], []
    sections: list[str] = []
    tables = 0
    pages: set[int] = set()
    for i, chunk in enumerate(chunks):
        rec = _chunk_record(chunk, fields, title, path.name, i, len(chunks))
        ids.append(rec["id"])
        docs.append(rec["text"])
        metas.append(_flatten_metadata(rec))
        if chunk.kind == "table":
            tables += 1
        if chunk.section and chunk.section not in sections:
            sections.append(chunk.section)
        if chunk.page is not None:
            pages.add(chunk.page)

    if ids:
        collection.upsert(ids=ids, documents=docs, metadatas=metas)

    report = FileReport(
        source_file=path.name,
        fields={k: v for k, v in fields.items() if not k.startswith("_") and k != "date_raw"},
        field_source=field_source,
        chunks=len(chunks),
        tables=tables,
        pages=max(pages) if pages else None,
        sections=sections,
        warnings=_warnings(fields, field_source),
    )
    return len(chunks), report


def ingest_documents(source: Path, *, explicit: dict[str, Any] | None = None,
                     manifest: dict[str, dict] | None = None,
                     reset: bool = False) -> tuple[int, list[FileReport]]:
    """Ingest a file or a directory. `explicit` applies to every file;
    `manifest` (source_file -> overrides) refines per file and wins over it."""
    collection = get_collection(reset=reset)
    manifest = manifest or {}

    total = 0
    reports: list[FileReport] = []
    for path in loader.iter_source_files(source):
        overrides = {**(explicit or {}), **manifest.get(path.name, {})}
        n, report = ingest_file(path, explicit=overrides, collection=collection)
        total += n
        reports.append(report)
    # Invalidate the (Redis-shared, cross-process) retrieval cache so a running
    # server won't serve pre-ingest results. Note: the server's in-memory query
    # index must still be refreshed via POST /api/admin/reload-index (or a
    # restart) — see store.reload_collection().
    try:
        from .cache import bump_version
        bump_version()
    except Exception:
        pass
    return total, reports


def _print_reports(reports: list[FileReport]) -> None:
    print(f"\n=== Ingest report — {len(reports)} file(s) ===")
    for r in reports:
        print(f"\n{r.source_file}")
        print(f"   chunks={r.chunks}  tables={r.tables}  pages={r.pages or '-'}  "
              f"sections={r.sections or '-'}")
        meta_line = ", ".join(
            f"{k}={r.fields[k]!r}[{r.field_source.get(k, '?')}]"
            for k in FILTERABLE if r.fields.get(k))
        print(f"   metadata: {meta_line or '(none resolved)'}")
        if r.warnings:
            print(f"   ! review: {'; '.join(r.warnings)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="file or directory of documents")
    parser.add_argument("--customer")
    parser.add_argument("--project")
    parser.add_argument("--equipment-type", dest="equipment_type")
    parser.add_argument("--doc-category", dest="doc_category")
    parser.add_argument("--revision")
    parser.add_argument("--offer-number", dest="offer_number")
    parser.add_argument("--date")
    parser.add_argument("--manifest", type=Path,
                        help="JSON: {source_filename: {field: value, ...}} per-file overrides")
    parser.add_argument("--reset", action="store_true",
                        help="wipe the WHOLE collection first (also removes offers — rarely wanted)")
    args = parser.parse_args()

    explicit = {k: v for k, v in {
        "customer": args.customer, "project": args.project,
        "equipment_type": args.equipment_type, "doc_category": args.doc_category,
        "revision": args.revision, "offer_number": args.offer_number, "date": args.date,
    }.items() if v}
    manifest = json.loads(args.manifest.read_text()) if args.manifest else None

    total, reports = ingest_documents(args.source, explicit=explicit,
                                      manifest=manifest, reset=args.reset)
    _print_reports(reports)
    print(f"\nIngested {total} chunks from {args.source}")
