"""Day 1-2 of the plan, built to scale: extracted JSON -> embeddings -> Chroma.

Records are read and written in BATCHES, and the source can be a single JSON
file or a whole directory of files. This is what lets ingestion handle
thousands of CAD/PDF extractions — there is no "500 file" ceiling. The limit
is disk + your vector DB, not the code.
"""
import json
from pathlib import Path
from typing import Any, Callable, Iterator

from . import config
from .store import get_collection

# Fields that are bookkeeping rather than engineering content.
_SKIP_KEYS = {"id", "title", "source_file"}

ProgressCb = Callable[[int, int], None]


def _flatten_pairs(value: Any, prefix: str = "") -> list[str]:
    """Recursively flatten nested dicts into 'label: value' strings."""
    pairs: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if v in (None, "", [], {}):
                continue
            label = (f"{prefix} " if prefix else "") + k.replace("_", " ")
            if isinstance(v, dict):
                pairs.extend(_flatten_pairs(v, label))
            else:
                pairs.append(f"{label}: {v}")
    return pairs


def build_embedding_text(record: dict[str, Any]) -> str:
    """Flatten a record into the natural-language text we embed. The category
    and given_data (the requirement) are foregrounded so a new requirement
    matches historical requirements; technical_details follow."""
    title = record.get("title") or record.get("id", "Document")
    parts = [str(title)]
    if record.get("category"):
        parts.append(f"category: {record['category']}")
    # given_data first, then technical_details, then any other top-level fields
    for key in ("given_data", "technical_details"):
        if isinstance(record.get(key), dict):
            parts.extend(_flatten_pairs(record[key]))
    for key, value in record.items():
        if key in _SKIP_KEYS or key in ("given_data", "technical_details", "category", "type") \
                or value in (None, "", []) or isinstance(value, dict):
            continue
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return ". ".join(parts)


def _flatten_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata must be scalar. Keep top-level scalars (incl. `category`
    and `source_file` for filtering/provenance); stash the full original record
    under _raw so the reasoning layer can use the nested sections."""
    meta: dict[str, Any] = {"_raw": json.dumps(record, ensure_ascii=False)}
    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)):
            meta[key] = value
    return meta


def iter_records(source: Path) -> Iterator[dict[str, Any]]:
    """Yield records from a single JSON file or a directory of JSON files.
    Streams file-by-file so memory stays flat regardless of corpus size."""
    if source.is_dir():
        for path in sorted(source.glob("*.json")):
            yield from _records_from_file(path)
    else:
        yield from _records_from_file(source)


def _records_from_file(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        yield from data
    elif isinstance(data, dict):
        yield data
    else:
        raise ValueError(f"{path}: expected a JSON object or array of objects.")


def _batched(iterable: Iterator[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def ingest_source(
    source: Path | None = None,
    *,
    reset: bool = True,
    batch_size: int | None = None,
    progress: ProgressCb | None = None,
) -> int:
    """Embed + upsert every record from `source` in batches. Returns count.

    `upsert` (not `add`) makes re-ingestion idempotent: feeding the same files
    again updates rather than duplicates, so incremental runs are safe.
    """
    source = source or config.DATA_SOURCE
    batch_size = batch_size or config.BATCH_SIZE
    collection = get_collection(reset=reset)

    processed = 0
    seen = 0  # for stable auto-ids
    for batch in _batched(iter_records(source), batch_size):
        ids, documents, metadatas = [], [], []
        for record in batch:
            rid = str(record.get("id") or f"doc-{seen}")
            seen += 1
            ids.append(rid)
            documents.append(build_embedding_text(record))
            metadatas.append(_flatten_metadata(record))
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        processed += len(batch)
        if progress:
            progress(processed, processed)  # total unknown while streaming
    return processed


# Backwards-compatible alias used elsewhere.
def ingest() -> int:
    return ingest_source()


if __name__ == "__main__":
    import time

    start = time.time()
    n = ingest_source(progress=lambda done, _: print(f"  ...{done} embedded", end="\r"))
    print(f"\nIngested {n} records from {config.DATA_SOURCE} "
          f"in {time.time() - start:.1f}s "
          f"(batch_size={config.BATCH_SIZE}) -> {config.CHROMA_DIR}")
