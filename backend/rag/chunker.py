"""Chunk structure-preserving Blocks into retrievable, metadata-tagged Chunks.

Rules that make retrieval accurate:
  * a TABLE block is never split — its rows stay together as one chunk, so a
    spec/price table is retrieved whole, not as dangling half-rows;
  * prose is split on SECTION boundaries first, then windowed by words, so a
    chunk never straddles "technical specification" and "terms & conditions";
  * every chunk carries its page number and section for pre-search filtering.
"""
from __future__ import annotations

from dataclasses import dataclass

from .loader import Block
from .sections import detect_section

DEFAULT_CHUNK_SIZE = 220   # words per prose chunk
DEFAULT_OVERLAP = 40       # words shared with the previous chunk (context continuity)


@dataclass
class Chunk:
    text: str
    page: int | None = None
    section: str | None = None
    kind: str = "text"        # "text" | "table"


def _window_words(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    out, start, step = [], 0, chunk_size - overlap
    while start < len(words):
        piece = " ".join(words[start:start + chunk_size]).strip()
        if piece:
            out.append(piece)
        start += step
    return out


def chunk_blocks(blocks: list[Block], chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap: int = DEFAULT_OVERLAP) -> list[Chunk]:
    """Turn loader Blocks into Chunks. Section state carries across blocks
    (a heading on page 1 governs the prose that follows on page 2)."""
    chunks: list[Chunk] = []
    current_section: str | None = None

    for block in blocks:
        if block.kind == "table":
            # atomic — but a table heading directly above it already set the
            # section, so inherit the current one.
            chunks.append(Chunk(text=block.text, page=block.page,
                                section=current_section, kind="table"))
            continue

        # prose: label each line with the section active at that line, letting
        # headings update the running section, then group into same-section runs.
        runs: list[tuple[str | None, list[str]]] = []
        for line in block.text.split("\n"):
            found = detect_section(line)
            if found:
                current_section = found
            if runs and runs[-1][0] == current_section:
                runs[-1][1].append(line)
            else:
                runs.append((current_section, [line]))

        for section, lines in runs:
            text = " ".join(ln.strip() for ln in lines if ln.strip())
            for piece in _window_words(text, chunk_size, overlap):
                chunks.append(Chunk(text=piece, page=block.page,
                                    section=section, kind="text"))
    return chunks


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Plain-text convenience wrapper (no page/section/table structure)."""
    return _window_words(text, chunk_size, overlap)
