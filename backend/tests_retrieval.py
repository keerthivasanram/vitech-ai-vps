"""Deterministic tests for the retrieval engine sub-services.

Model-free and corpus-free: they exercise the reranker, chunk selector,
permission filter, citation builder, response formatter and cache directly, so
a refactor can't silently break grounding. Run:  .venv/bin/python tests_retrieval.py
"""
import sys

from app import config
from rag import cache, chunk_selector, citations, permissions, reranker
from rag import response_formatter as rf

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'OK ' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


# --- reranker: lexical signal rescues a relevant low-vector hit --------------
hits = [
    {"id": "a", "source_file": "a.pdf", "text": "general safety and housekeeping notes", "score": 0.90},
    {"id": "b", "source_file": "b.pdf", "text": "dry filter paint booth face velocity 0.5 m/s across the open face", "score": 0.70},
    {"id": "c", "source_file": "c.pdf", "text": "conveyor chain lubrication schedule", "score": 0.60},
]
ranked = reranker.rerank("what face velocity for a dry filter paint booth", hits, 3)
check("reranker promotes the lexically-matching hit to #1", ranked[0]["id"] == "b")
check("reranker annotates dense_rank / rerank_score", "rerank_score" in ranked[0] and "dense_rank" in ranked[0])

# metadata boost: exact equipment_type match nudges a tie
mh = [
    {"id": "x", "source_file": "x.pdf", "text": "booth airflow design", "score": 0.80, "equipment_type": "dust_collector"},
    {"id": "y", "source_file": "y.pdf", "text": "booth airflow design", "score": 0.80, "equipment_type": "paint_booth"},
]
mr = reranker.rerank("booth airflow design", mh, 2, filters={"equipment_type": "paint_booth"})
check("reranker meta-boost favours the matching equipment_type", mr[0]["id"] == "y")

# --- chunk selector: dedup + per-doc cap -------------------------------------
dup = [
    {"id": "1", "source_file": "same.pdf", "text": "identical chunk text here"},
    {"id": "2", "source_file": "same.pdf", "text": "identical chunk text here"},  # dup
    {"id": "3", "source_file": "same.pdf", "text": "second distinct chunk from same"},
    {"id": "4", "source_file": "same.pdf", "text": "third distinct chunk from same"},
    {"id": "5", "source_file": "other.pdf", "text": "a chunk from another document"},
]
sel = chunk_selector.select(dup, top_k=10, max_per_doc=2)
check("chunk selector drops the near-duplicate", len(sel) == 3)
check("chunk selector caps per source document", sum(1 for h in sel if h["source_file"] == "same.pdf") == 2)
check("chunk selector keeps the other document", any(h["source_file"] == "other.pdf" for h in sel))

# --- permissions: default allow-all, restricted category gates ---------------
p_default = permissions.DEFAULT_PRINCIPAL
docs = [{"id": "d1", "doc_category": "offer"}, {"id": "d2", "doc_category": "internal_costing"}]
check("permissions allow-all when nothing restricted", len(permissions.filter_hits(docs, p_default)) == 2)

_saved = config.RESTRICTED_DOC_CATEGORIES
config.RESTRICTED_DOC_CATEGORIES = {"internal_costing"}
try:
    viewer = permissions.Principal(role="viewer")
    admin = permissions.Principal(role="admin")
    check("permissions hide restricted category from non-privileged role",
          [h["id"] for h in permissions.filter_hits(docs, viewer)] == ["d1"])
    check("permissions show restricted category to privileged role",
          len(permissions.filter_hits(docs, admin)) == 2)
finally:
    config.RESTRICTED_DOC_CATEGORIES = _saved

# --- citations: one per source, ranked, numbered -----------------------------
chits = [
    {"source_file": "s1.pdf", "section": "3", "page": 4, "score": 0.6},
    {"source_file": "s1.pdf", "section": "3", "page": 4, "score": 0.9},   # same doc, better
    {"source_file": "s2.pdf", "section": None, "page": None, "score": 0.7},
]
cites = citations.build(chits)
check("citations collapse to one per source document", len(cites) == 2)
check("citations rank by best chunk score", cites[0]["source_file"] == "s1.pdf" and cites[0]["n"] == 1)
check("citation label renders", citations.label(cites[0]).startswith("[1] s1.pdf"))

# --- response formatter: numbered context within budget ----------------------
ctx = rf.format_context([
    {"source_file": "s1.pdf", "section": "Design", "text": "alpha " * 50, "score": 0.9},
    {"source_file": "s2.pdf", "section": None, "text": "beta " * 50, "score": 0.5},
], char_budget=120)
check("formatter respects the char budget (drops overflow)", ctx["used"] == 1)
check("formatter tags excerpts with [n]", ctx["context"].startswith("[1] s1.pdf"))

# --- cache: round-trip + version invalidation --------------------------------
q, filt, k = "cache probe", {"equipment_type": "paint_booth"}, 5
payload = [{"id": "z", "source_file": "z.pdf", "text": "cached", "score": 0.5}]
cache.put(q, filt, k, payload)
check("cache returns what was stored", cache.get(q, filt, k) == payload)
cache.bump_version()
check("cache miss after version bump (invalidation)", cache.get(q, filt, k) is None)

print()
if _fail:
    print(f"{_fail} RETRIEVAL TEST(S) FAILED")
    sys.exit(1)
print("ALL RETRIEVAL TESTS PASS")
