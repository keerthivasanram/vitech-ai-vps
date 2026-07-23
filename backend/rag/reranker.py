"""Reranker — reorders vector candidates by true relevance, not just cosine.

Vector similarity alone ranks by embedding proximity, which drifts on short
queries and shared boilerplate. We fuse two independent signals with Reciprocal
Rank Fusion (RRF), plus a small exact-metadata boost:

  * dense rank   — the vector similarity order (from Chroma)
  * lexical rank — BM25-lite term overlap between the query and the chunk text
  * meta boost   — the chunk's equipment_type / customer exactly matches a filter

RRF is robust and parameter-light (no per-corpus tuning), and being model-free
it runs offline with zero extra latency. The interface (`rerank(query, hits, k)`)
is exactly what a cross-encoder would expose, so a BGE reranker can drop in later
by swapping the scoring — the pipeline around it does not change.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from app import config

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _bm25_lite_scores(query: str, hits: list[dict]) -> list[float]:
    """BM25-style lexical score of each hit's text against the query, using the
    candidate set itself as the document frequency corpus (small, self-contained).
    """
    q_terms = set(_tokens(query))
    if not q_terms:
        return [0.0] * len(hits)
    docs = [_tokens(h.get("text", "")) for h in hits]
    n = len(docs) or 1
    df = Counter()
    for d in docs:
        for t in set(d):
            if t in q_terms:
                df[t] += 1
    avgdl = (sum(len(d) for d in docs) / n) or 1.0
    k1, b = 1.5, 0.75
    scores = []
    for d in docs:
        tf = Counter(d)
        dl = len(d) or 1
        s = 0.0
        for t in q_terms:
            if not tf.get(t):
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def _rank_map(order: list[int]) -> dict[int, int]:
    """indices in ranked order -> 1-based rank."""
    return {idx: r + 1 for r, idx in enumerate(order)}


def rerank(query: str, hits: list[dict], top_k: int,
           filters: dict | None = None) -> list[dict]:
    """Return the top_k hits reordered by fused relevance. Each returned hit
    carries a `rerank_score` and its contributing ranks for transparency."""
    if not hits:
        return []
    if not config.RERANK_ENABLED or len(hits) == 1:
        return hits[:top_k]

    filters = filters or {}
    idxs = list(range(len(hits)))

    # dense order = the order Chroma already returned (by descending score)
    dense_order = sorted(idxs, key=lambda i: -(hits[i].get("score") or 0.0))
    dense_rank = _rank_map(dense_order)

    lex = _bm25_lite_scores(query, hits)
    lexical_order = sorted(idxs, key=lambda i: -lex[i])
    lexical_rank = _rank_map(lexical_order)
    lex_max = max(lex) or 1.0             # normalise magnitude to [0,1]

    k = config.RERANK_RRF_K
    fused = []
    for i in idxs:
        rrf = (config.RERANK_DENSE_W / (k + dense_rank[i])
               + config.RERANK_LEXICAL_W / (k + lexical_rank[i]))
        rrf += config.RERANK_LEXICAL_MAG_W * (lex[i] / lex_max)
        boost = 0.0
        for mk in ("equipment_type", "customer"):
            fv = filters.get(mk)
            if fv is not None and hits[i].get(mk) == fv:
                boost += config.RERANK_META_BOOST
        fused.append((i, rrf + boost))

    fused.sort(key=lambda p: -p[1])
    out = []
    for i, sc in fused[:top_k]:
        h = dict(hits[i])
        h["rerank_score"] = round(sc, 6)
        h["dense_rank"] = dense_rank[i]
        h["lexical_rank"] = lexical_rank[i]
        out.append(h)
    return out
