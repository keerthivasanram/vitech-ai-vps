"""Day 3: similarity search over the engineering knowledge base.

The LLM never searches the DB directly. This retriever finds the relevant
engineering records first, and they become the grounding context.
"""
import json
import re
from typing import Any

from . import config
from .store import get_collection

# generic words that don't identify a specific client/equipment
_STOP = {"pvt", "ltd", "private", "limited", "systems", "system", "india", "the",
         "and", "engineering", "machinery", "industrial", "enviro", "co", "company",
         "gears", "offer", "for"}

# "which clients / list all projects / how many offers / what's in the database"
_OVERVIEW = re.compile(
    r"\b(which|what|list|show|name|how many|all)\b.{0,40}"
    r"\b(client|clients|customer|customers|project|projects|offer|offers|order|"
    r"orders|record|records|database|stored|catalog|catalogue|have|do we)\b",
    re.I,
)


def is_overview(question: str) -> bool:
    """True for enumeration/overview questions ('which clients are stored?') that
    should see the WHOLE knowledge base, not a semantic top-k (their wording
    rarely matches any single record well)."""
    return bool(_OVERVIEW.search(question))


# Phrases that say "build this FROM our existing data", not "design it fresh".
# An EXPLICIT instruction to consult the stored data. A spec is built from the
# database ONLY when the user clearly says so ("refer db", "from the database",
# "use our records"). Merely naming a client or saying "based on our offer" does
# NOT count — by default the assistant designs from its own engineering knowledge.
_REFER_DB = re.compile(
    r"\b("
    r"refer\s+(to\s+)?(the\s+)?(db|database|records?|knowledge\s?base|history|data)|"
    r"(from|using|use|check|consult|search|analyse|analyze|look\s+(up|in))\s+"
    r"(the\s+|our\s+)?(db|database|records?|knowledge\s?base)|"
    r"\bdatabase\b|\brefer\s+db\b|"
    r"our\s+records|our\s+stored\s+data|stored\s+(offers?|records?|data)"
    r")\b", re.I)


def _names_stored_client(question: str) -> bool:
    """True only when the question names a stored CLIENT or a specific offer ID
    (e.g. 'C2C', 'Kobelco', 'OFF-C2C-WS-172') — NOT the equipment type. Equipment
    words like 'wet scrubber' appear in every offer title and must not count as a
    reference to existing data."""
    q = question.lower()
    if re.search(r"\boff-[a-z0-9][a-z0-9-]+", q):     # explicit offer id
        return True
    col = get_collection()
    if col.count() == 0:
        return False
    for meta in col.get(include=["metadatas"])["metadatas"]:
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        # client identity only — skip vendor (always us) and title (equipment words)
        names = str(rec.get("client", "")).lower()
        tokens = {t for t in re.split(r"[\s,./_-]+", names)
                  if len(t) >= 3 and t not in _STOP}
        if any(re.search(rf"\b{re.escape(t)}\b", q) for t in tokens):
            return True
    return False


def references_existing_data(question: str) -> bool:
    """DB mode for a SPEC is enabled ONLY by an explicit database reference
    ('refer db', 'from the database', 'use our records'). Naming a client or
    saying 'based on our offer' is NOT enough — by default the assistant designs
    the spec from its own engineering knowledge, not the stored data."""
    return bool(_REFER_DB.search(question or ""))


def is_data_lookup(question: str) -> bool:
    """True for a DIRECT lookup of stored records — an overview ('which clients
    are stored?') or a named client/offer ('what did C2C order?'). Used to gate
    the self-verify pass. Deliberately strict: a general concept question that
    merely mentions 'wet scrubber' is NOT a data lookup (equipment words appear
    in every offer title) and must keep its general engineering knowledge."""
    return is_overview(question) or _names_stored_client(question)


# analytical: aggregate/compute over the stored records
_ANALYTICAL = re.compile(
    r"\b(how many|how much|total|sum|average|avg|mean|count|number of|"
    r"most|least|highest|lowest|largest|smallest|biggest|cheapest|"
    r"expensive|maximum|minimum|max|min|per (category|client|type)|"
    r"across (all|the|our)|breakdown|statistics|stats)\b", re.I)

# comparison: put two or more things side by side
_COMPARISON = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference between|differences|"
    r"which is (better|bigger|larger|cheaper|more)|side by side|"
    r"how does .+ (compare|differ))\b", re.I)


def is_analytical(question: str) -> bool:
    return bool(_ANALYTICAL.search(question or ""))


def is_comparison(question: str) -> bool:
    return bool(_COMPARISON.search(question or ""))


def has_offers(category: str | None) -> bool:
    """True if the knowledge base holds at least one offer of this category —
    used to decide whether a Quotation is even possible for it."""
    col = get_collection()
    if not category or col.count() == 0:
        return False
    try:
        res = col.get(where={"category": category}, limit=1, include=[])
        return bool(res.get("ids"))
    except Exception:
        return False


def all_hits() -> list[dict[str, Any]]:
    """Every stored offer as a hit — for overview/enumeration answers."""
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.get(include=["documents", "metadatas"])
    out = []
    for doc, meta in zip(res["documents"], res["metadatas"]):
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        out.append({"id": rec.get("id"), "title": rec.get("title", rec.get("id")),
                    "type": rec.get("type", "offer"), "text": doc, "record": rec,
                    "score": 0.9})
    return out


def _make_hit(rec: dict, doc: str, score: float = 0.95) -> dict[str, Any]:
    return {"id": rec.get("id"), "title": rec.get("title", rec.get("id")),
            "type": rec.get("type", "offer"), "text": doc, "record": rec,
            "score": score}


def entity_hits(question: str) -> list[dict[str, Any]]:
    """Direct lookup by CLIENT IDENTITY or an explicit offer id — NOT the title.

    Matches on the client name and offer id only, with word-boundary matching.
    Equipment words ('paint', 'booth', 'scrubber') appear in many offer TITLES,
    so title-token matching used to make '0.9 x 0.92 x 2 water wall paint booth'
    return every paint/booth/conveyor offer (Armstrong, Eco Chimneys, ...). A
    client lookup must key on WHO, not the equipment; dimension/equipment queries
    are handled deterministically by `structured_project_hits`.
    """
    q = question.lower()
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.get(include=["documents", "metadatas"])
    hits = []
    for doc, meta in zip(res["documents"], res["metadatas"]):
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        oid = str(rec.get("id", "")).lower()
        if oid and oid in q:                          # explicit offer id = exact hit
            hits.append(_make_hit(rec, doc))
            continue
        names = str(rec.get("client", "")).lower()    # client identity ONLY
        tokens = {t for t in re.split(r"[\s,./_-]+", names) if len(t) >= 3 and t not in _STOP}
        if any(re.search(rf"\b{re.escape(t)}\b", q) for t in tokens):
            hits.append(_make_hit(rec, doc))
    return hits


# Relevance search knobs. Fuse dense (vector) + lexical (query-term overlap),
# then keep only the cluster near the top score so we return the few genuinely
# relevant projects — never a whole-category dump (which would not scale to
# thousands of files).
_REL_POOL = 15        # vector candidates to consider
_REL_TOP_K = 6        # max projects returned
_REL_DENSE_W = 0.55
_REL_LEXICAL_W = 0.45
_REL_GAP = 0.15       # keep hits within this of the top fused score
_REL_FLOOR = 0.28     # absolute minimum fused score to be considered relevant


def _content_terms(text: str) -> set[str]:
    return {t for t in re.split(r"[\s,./_-]+", (text or "").lower())
            if len(t) >= 3 and t not in _STOP}


def _exact_dimension_hit(question: str) -> list[dict[str, Any]]:
    """If the question gives an equipment type + dimensions that match ONE offer
    exactly, return just that offer (the confident single result, e.g. the Yonex
    0.9x0.92x2 booth). Exact matches only — near matches go through relevance."""
    from .classify import CONFIDENT, classify_equipment
    from .understand import _fallback                 # deterministic parse (no LLM)

    cat, score = classify_equipment(question)
    if not cat or score < CONFIDENT:
        return []
    params = {k: v for k, v in _fallback(question).parameters.items()
              if isinstance(v, (int, float))}
    if not params:
        return []
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.get(include=["documents", "metadatas"])
    for doc, meta in zip(res["documents"], res["metadatas"]):
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        if rec.get("type", "offer") != "offer" or rec.get("category") != cat:
            continue
        gd = rec.get("given_data", {}) or {}
        keys = [k for k in params if isinstance(gd.get(k), (int, float))]
        if keys and len(keys) == len(params) and all(
                abs(params[k] - gd[k]) / max(abs(gd[k]), 1e-9) < 0.02 for k in keys):
            return [_make_hit(rec, doc, score=0.99)]
    return []


def _relevant_offer_hits(question: str, top_k: int = _REL_TOP_K) -> list[dict[str, Any]]:
    """Content-relevance search over the OFFERS: semantic vector similarity fused
    with query-term overlap, then a gap cut so only the projects near the top
    score are returned. This is what finds 'Armstrong' for 'paint booth conveyor
    improvement' (its content matches, though its CATEGORY is conveyor, not paint
    booth) and it scales — top-k relevance, never a category dump."""
    col = get_collection()
    n = col.count()
    if n == 0:
        return []
    res = col.query(query_texts=[question], n_results=min(_REL_POOL, n),
                    where={"type": "offer"},
                    include=["documents", "metadatas", "distances"])
    if not res["documents"] or not res["documents"][0]:
        return []
    q_terms = _content_terms(question)
    cands = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        dense = 1 - dist                              # cosine similarity
        d_terms = _content_terms(doc)
        lex = (len(q_terms & d_terms) / len(q_terms)) if q_terms else 0.0
        fused = _REL_DENSE_W * dense + _REL_LEXICAL_W * lex
        cands.append((fused, dense, rec, doc))
    if not cands:
        return []
    cands.sort(key=lambda p: -p[0])
    top = cands[0][0]
    threshold = max(top - _REL_GAP, _REL_FLOOR)
    kept = [c for c in cands if c[0] >= threshold][:top_k]
    return [_make_hit(rec, doc, score=round(dense, 3)) for _f, dense, rec, doc in kept]


def structured_project_hits(question: str) -> list[dict[str, Any]]:
    """No-client project lookup: an exact equipment+dimension match returns that
    one project; otherwise a content-relevance search over the offers returns the
    few most relevant. Ranks by what the project IS, and scales to a large corpus
    because it never enumerates a whole category."""
    exact = _exact_dimension_hit(question)
    if exact:
        return exact
    return _relevant_offer_hits(question)


def project_hits(question: str) -> list[dict[str, Any]]:
    """The lookup a client/project question should use: a named client/offer-id
    match first (WHO), else a deterministic equipment+attribute match (WHAT).
    This ordering is what makes the FIRST answer the right one."""
    named = entity_hits(question)
    if named:
        return named
    return structured_project_hits(question)


def retrieve(question: str, top_k: int | None = None,
             where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Semantic search, optionally restricted to a metadata filter (e.g.
    {"category": "wet_scrubber"} so a scrubber query never returns booths).
    Falls back to an unfiltered search if the filter yields nothing."""
    top_k = top_k or config.TOP_K
    collection = get_collection()

    count = collection.count()
    if count == 0:
        return []

    def _query(flt):
        return collection.query(
            query_texts=[question],
            n_results=min(top_k, count),
            where=flt or None,
            include=["documents", "metadatas", "distances"],
        )

    result = _query(where)
    if where and not result["documents"][0]:
        result = _query(None)  # nothing matched the filter — broaden

    hits: list[dict[str, Any]] = []
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = result["distances"][0]
    for doc, meta, dist in zip(docs, metas, dists):
        raw = meta.get("_raw")
        record = json.loads(raw) if raw else {}
        hits.append({
            "id": record.get("id", "?"),
            "title": record.get("title", record.get("id", "Document")),
            "type": record.get("type", "document"),
            "text": doc,
            "record": record,
            "score": round(1 - dist, 3),  # cosine distance -> similarity
        })
    return hits


def summarize_retrieval(hits: list[dict[str, Any]]) -> list[str]:
    """Human-friendly 'Retrieved N ...' lines for the assistant UI."""
    counts: dict[str, int] = {}
    for h in hits:
        counts[h["type"]] = counts.get(h["type"], 0) + 1
    label = {
        "product": "engineering documents",
        "bom": "bills of material",
        "quotation": "previous quotations",
        "spec": "design standards",
        "document": "documents",
    }
    return [f"Retrieved {n} {label.get(t, t)}" for t, n in counts.items()]
