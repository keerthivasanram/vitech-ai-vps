"""Metadata-filtered semantic search over ingested documents.

The whole point of the rich metadata is this: the Engineering Agent narrows
the candidate set with a hard metadata filter (equipment type, customer,
project, doc category, revision, section) BEFORE the vector similarity runs, so
a "wet scrubber tower height" query can be restricted to wet-scrubber technical
specifications and never drifts into paint-booth terms. That is far more
accurate than similarity alone.

Chroma 0.5.x where syntax: one condition is a bare dict; two+ must be wrapped
in {"$and": [...]}. Both are handled by _build_where.
"""
from __future__ import annotations

import json
from typing import Any

from app import config

from . import cache, chunk_selector, permissions, reranker
from .embedding import get_collection

DOC_TYPE = "document"

# fields that can be used as pre-search equality filters
FILTER_KEYS = ("customer", "project", "equipment_type", "doc_category",
               "revision", "offer_number", "date", "section", "kind", "page")


def _build_where(filters: dict[str, Any]) -> dict[str, Any]:
    conds: list[dict[str, Any]] = [{"type": DOC_TYPE}]
    for key in FILTER_KEYS:
        value = filters.get(key)
        if value is not None:
            conds.append({key: value})
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _to_hits(result: dict) -> list[dict[str, Any]]:
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = result["distances"][0]
    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        raw = meta.get("_raw")
        record = json.loads(raw) if raw else {}
        hits.append({
            "id": record.get("id", meta.get("id", "?")),
            "title": record.get("title", "Document"),
            "source_file": record.get("source_file"),
            "customer": record.get("customer"),
            "equipment_type": record.get("equipment_type"),
            "section": record.get("section"),
            "page": record.get("page"),
            "kind": record.get("kind", "text"),
            "text": doc,
            "score": round(1 - dist, 3),
        })
    return hits


def _candidate_search(collection, question, filters, count, broaden):
    """Vector search that OVER-FETCHES a candidate pool (for the reranker),
    keeping the original graceful-broaden fallback so a too-specific filter
    degrades to fewer constraints rather than to zero results."""
    n = min(max(config.RETRIEVE_CANDIDATES, 1), count)

    def _run(where):
        res = collection.query(
            query_texts=[question], n_results=n, where=where,
            include=["documents", "metadatas", "distances"],
        )
        return _to_hits(res) if res["documents"] and res["documents"][0] else []

    hits = _run(_build_where(filters))
    if hits or not broaden or not any(filters.get(k) is not None for k in FILTER_KEYS):
        return hits
    if filters.get("equipment_type"):     # broaden 1: keep only equipment_type
        hits = _run(_build_where({"equipment_type": filters["equipment_type"]}))
        if hits:
            return hits
    return _run({"type": DOC_TYPE})        # broaden 2: documents only


def retrieve_documents(question: str, top_k: int = 6, *,
                       filters: dict[str, Any] | None = None,
                       broaden: bool = True,
                       principal=None) -> list[dict[str, Any]]:
    """Top-k document chunks for `question`, through the full retrieval pipeline:

        cache -> vector over-fetch (+ broaden) -> permission filter
              -> hybrid rerank -> chunk selection -> cache

    Backward-compatible: same signature/return shape as before, plus an optional
    `principal` for access control. Each returned hit is a dict with id/title/
    source_file/section/page/text/score (rerank adds rerank_score).
    """
    filters = dict(filters or {})
    cached = cache.get(question, filters, top_k)
    if cached is not None:
        return cached

    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    candidates = _candidate_search(collection, question, filters, count, broaden)
    principal = principal or permissions.DEFAULT_PRINCIPAL
    candidates = permissions.filter_hits(candidates, principal)
    reranked = reranker.rerank(question, candidates, len(candidates), filters=filters)
    hits = chunk_selector.select(reranked, top_k)

    cache.put(question, filters, top_k, hits)
    return hits


def available_filters() -> dict[str, list[Any]]:
    """Distinct values present for each filterable field across all ingested
    documents — lets the agent/UI show valid customers, equipment types, etc.
    (and lets the agent pick a filter that actually matches something)."""
    collection = get_collection()
    if collection.count() == 0:
        return {}
    res = collection.get(where={"type": DOC_TYPE}, include=["metadatas"])
    facets: dict[str, set] = {k: set() for k in FILTER_KEYS}
    for meta in res["metadatas"]:
        for key in FILTER_KEYS:
            if meta.get(key) is not None:
                facets[key].add(meta[key])
    return {k: sorted(v) for k, v in facets.items() if v}
