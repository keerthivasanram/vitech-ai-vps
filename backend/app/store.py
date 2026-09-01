"""Chroma vector store access — shared by ingestion and retrieval so both
sides use the exact same embedding function (ONNX all-MiniLM-L6-v2, local)."""
import json
import threading

import chromadb
from chromadb.utils import embedding_functions

from . import config

# Local ONNX MiniLM-L6-v2. No PyTorch, no network at query time after first run.
_embedding_fn = embedding_functions.DefaultEmbeddingFunction()


def get_client() -> chromadb.ClientAPI:
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def get_collection(reset: bool = False):
    client = get_client()
    if reset:
        try:
            client.delete_collection(config.COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=_embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


# --- parsed offer records ---------------------------------------------------
# Eight call sites (analytics, pricing, retriever, the data views, the package
# support helpers) each pulled EVERY metadata row and `json.loads`-ed `_raw` on
# EVERY request. Invisible at 33 offers; at the "thousands of extracted
# documents" the README targets it is the dominant cost of nearly every
# endpoint, and it is the same work repeated several times within a single
# request. Parsed once here instead.
#
# CALLERS MUST TREAT THE RESULT AS READ-ONLY — it is the shared cache, not a
# copy. Every current caller builds new dicts from it rather than mutating it.
# INVALIDATION IS EXPLICIT, and measured rather than assumed. The first version
# checked `col.count()` on every call to detect an out-of-process write. That
# check turned out to cost ~20 ms against ~6 ms for the whole scan-and-parse it
# was guarding, so the "cache" was three times SLOWER than no cache at all at
# the current corpus size. It is dropped: writers invalidate instead.
#
# An ingest by a SEPARATE process (the `rag.ingest` CLI) therefore does not
# invalidate this automatically — but that was already true of ChromaDB's own
# query index, which is exactly why `POST /api/admin/reload-index` exists and
# why the runbook already requires calling it after an out-of-process ingest.
# `reload_collection()` clears this cache too, so that one documented step
# remains the single answer.
_records_lock = threading.Lock()
_records_cache: list | None = None


def offer_records() -> list[dict]:
    """Every stored OFFER, parsed from its `_raw` metadata. Cached.

    THE `type == "offer"` FILTER IS LOad-BEARING. `rag.ingest` writes ingested
    documents into this same collection under `type="document"` - deliberately,
    so retrieval can search both - and its own contract is that doing so "never
    touches the ATS spec engine, which only reasons over type=offer". Those
    chunks carry a `_raw` of their own, so without this filter every
    offer-derived view silently counts them: after the first real ingest
    `list_projects` reported 211 offers instead of 33, and the pricing and
    analytics layers were reading document chunks as historical projects.
    Found by driving the live agent, not by any test - hence the one below it.
    """
    global _records_cache
    cached = _records_cache
    if cached is not None:
        return cached
    records: list[dict] = []
    col = get_collection()
    if col.count():
        for meta in col.get(include=["metadatas"])["metadatas"]:
            raw = meta.get("_raw")
            if not raw or meta.get("type") != "offer":
                continue
            try:
                records.append(json.loads(raw))
            except (TypeError, ValueError):
                continue          # a malformed record must not break every read
    with _records_lock:
        _records_cache = records
    return records


def invalidate_records() -> None:
    """Drop the parsed-record cache. Called after any write to the collection."""
    global _records_cache
    with _records_lock:
        _records_cache = None


def reload_collection():
    """Drop ChromaDB's in-process system cache so a long-running server picks up
    documents ingested by a SEPARATE process (the stale-query-index gotcha:
    count() reads fresh from disk, but the in-memory HNSW segment does not
    refresh until the cache is cleared). Call this after an ingest instead of
    restarting the backend. Returns a freshly-opened collection."""
    invalidate_records()
    for path in (
        "chromadb.api.shared_system_client:SharedSystemClient",
        "chromadb.api.client:SharedSystemClient",
    ):
        mod, _, cls = path.partition(":")
        try:
            import importlib
            getattr(importlib.import_module(mod), cls).clear_system_cache()
            break
        except Exception:
            continue
    return get_collection()
