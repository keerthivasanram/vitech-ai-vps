"""Citation builder — turns retrieved chunks into structured, de-duplicated
source references the agent can show ("per DOC-x, section y").

One citation per distinct source document (best-scoring chunk wins), numbered in
relevance order, so a grounded answer can point at exactly where each claim came
from instead of a vague "our records".
"""
from __future__ import annotations


def build(hits: list[dict]) -> list[dict]:
    """[{n, source_file, section, page, equipment_type, score}] — one per
    distinct source document, ranked by best chunk score."""
    best: dict[str, dict] = {}
    for h in hits:
        src = h.get("source_file") or h.get("id") or "?"
        cur = best.get(src)
        if cur is None or (h.get("score") or 0) > (cur.get("score") or 0):
            best[src] = h
    ranked = sorted(best.values(), key=lambda h: -(h.get("score") or 0.0))
    out = []
    for n, h in enumerate(ranked, 1):
        out.append({
            "n": n,
            "source_file": h.get("source_file"),
            "section": h.get("section"),
            "page": h.get("page"),
            "equipment_type": h.get("equipment_type"),
            "score": h.get("score"),
        })
    return out


def label(citation: dict) -> str:
    """Human-readable citation, e.g. '[1] STD-PB-001, section 3 (p.4)'."""
    parts = [f"[{citation['n']}]", citation.get("source_file") or "document"]
    if citation.get("section"):
        parts.append(f"- {citation['section']}")
    if citation.get("page") is not None:
        parts.append(f"(p.{citation['page']})")
    return " ".join(str(p) for p in parts)
