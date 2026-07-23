"""Chunk selection — turns a ranked candidate list into the final evidence set.

After reranking we still want to (a) drop near-duplicate chunks so the same
sentence from two revisions isn't shown twice, and (b) cap how many chunks come
from any single source document, so one long file can't crowd out the rest of
the corpus. Order from the reranker is preserved otherwise.
"""
from __future__ import annotations

import re

from app import config

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def select(hits: list[dict], top_k: int,
           max_per_doc: int | None = None) -> list[dict]:
    """Dedup near-identical chunks and cap per source document, preserving the
    incoming (reranked) order, until top_k are chosen."""
    if not hits:
        return []
    cap = config.SELECT_MAX_PER_DOC if max_per_doc is None else max_per_doc
    seen_text: set[str] = set()
    per_doc: dict[str, int] = {}
    out: list[dict] = []
    for h in hits:
        sig = _norm(h.get("text", ""))[:400]
        if sig and sig in seen_text:
            continue
        src = h.get("source_file") or h.get("id") or "?"
        if cap and per_doc.get(src, 0) >= cap:
            continue
        seen_text.add(sig)
        per_doc[src] = per_doc.get(src, 0) + 1
        out.append(h)
        if len(out) >= top_k:
            break
    return out
