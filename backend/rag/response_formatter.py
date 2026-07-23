"""Response formatter — assembles retrieved chunks into a grounded context
block for the LLM (and a compact citations list for the UI).

Keeps a hard character budget so a broad query can't overflow the prompt of a
small local model, and tags each excerpt with its citation number so the model
can reference sources by [n] in its answer.
"""
from __future__ import annotations

from . import citations as _cit

_DEFAULT_BUDGET = 3500


def format_context(hits: list[dict], *, char_budget: int = _DEFAULT_BUDGET) -> dict:
    """Return {context, citations, used} — a numbered, budget-bounded context
    string plus the structured citations that back it."""
    cites = _cit.build(hits)
    # map source_file -> citation number so each excerpt is tagged consistently
    num = {c["source_file"]: c["n"] for c in cites}
    lines: list[str] = []
    used = 0
    included = 0
    for h in hits:
        n = num.get(h.get("source_file"), "?")
        head = f"[{n}] {h.get('source_file') or 'document'}"
        if h.get("section"):
            head += f" - {h['section']}"
        excerpt = (h.get("text") or "").strip()
        block = f"{head}\n{excerpt}"
        if used + len(block) > char_budget and included:
            break
        lines.append(block)
        used += len(block)
        included += 1
    return {
        "context": "\n\n".join(lines),
        "citations": cites[:included] if included else cites,
        "used": included,
    }
