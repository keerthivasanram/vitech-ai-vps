"""Chroma vector store access — shared by ingestion and retrieval so both
sides use the exact same embedding function (ONNX all-MiniLM-L6-v2, local)."""
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


def reload_collection():
    """Drop ChromaDB's in-process system cache so a long-running server picks up
    documents ingested by a SEPARATE process (the stale-query-index gotcha:
    count() reads fresh from disk, but the in-memory HNSW segment does not
    refresh until the cache is cleared). Call this after an ingest instead of
    restarting the backend. Returns a freshly-opened collection."""
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
