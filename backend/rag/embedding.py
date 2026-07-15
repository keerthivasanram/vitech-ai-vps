"""Embedding access for the RAG pipeline.

Deliberately reuses the SAME embedding function and collection as
app/store.py (ONNX all-MiniLM-L6-v2) rather than standing up a second one —
per the project's #1 retrieval gotcha, writing and reading a Chroma
collection with different embedding models silently breaks retrieval.
"""
from app.store import get_client, get_collection

__all__ = ["get_client", "get_collection", "embed_texts"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Direct access to the embedding vectors (e.g. for offline similarity
    checks) — normal ingest/retrieve goes through the Chroma collection,
    which embeds automatically."""
    collection = get_collection()
    return collection._embedding_function(texts)
