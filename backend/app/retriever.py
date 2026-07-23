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


def structured_project_hits(question: str) -> list[dict[str, Any]]:
    """Deterministic lookup by equipment type + structured attributes (dimensions,
    airflow) for questions that name NO client — e.g. '0.9 x 0.92 x 2 water wall
    paint booth'. Filters offers to the confidently-classified equipment category
    and ranks by how closely the given numeric attributes match each offer's
    given_data. An EXACT attribute match is returned alone (one confident result);
    otherwise the nearest few. This is the metadata-first ranking that keeps a
    dimension query from doing a broad keyword sweep.
    """
    from .classify import CONFIDENT, classify_equipment
    from .understand import _fallback                 # deterministic parse (no LLM)

    cat, score = classify_equipment(question)
    if not cat or score < CONFIDENT:
        return []
    params = {k: v for k, v in _fallback(question).parameters.items()
              if isinstance(v, (int, float))}

    col = get_collection()
    if col.count() == 0:
        return []
    res = col.get(include=["documents", "metadatas"])
    cat_offers = []                                   # (doc, rec) for this category
    for doc, meta in zip(res["documents"], res["metadatas"]):
        raw = meta.get("_raw")
        if not raw:
            continue
        rec = json.loads(raw)
        if rec.get("type", "offer") == "offer" and rec.get("category") == cat:
            cat_offers.append((doc, rec))
    if not cat_offers:
        return []

    # Equipment named but no dimensions to match on (e.g. "hot air oven" or a spec
    # like "U-type 6.5L" that isn't a parseable size): return the category's
    # projects so "have we done a hot air oven / which clients" lists the real
    # clients — never claim we have none when we plainly have offers in this type.
    if not params:
        return [_make_hit(rec, doc, score=0.6) for doc, rec in cat_offers]

    scored = []
    for doc, rec in cat_offers:
        gd = rec.get("given_data", {}) or {}
        keys = [k for k in params if isinstance(gd.get(k), (int, float))]
        if not keys:
            continue
        diffs = [abs(params[k] - gd[k]) / max(abs(gd[k]), 1e-9) for k in keys]
        avg = sum(diffs) / len(diffs)
        # exact only when EVERY numeric attribute the user gave was compared and matched
        exact = len(keys) == len(params) and all(d < 0.02 for d in diffs)
        scored.append((exact, max(0.0, 1 - avg), len(keys), rec, doc))

    # params given but none comparable to this category's data -> still show the
    # category's projects rather than claim we have none.
    if not scored:
        return [_make_hit(rec, doc, score=0.6) for doc, rec in cat_offers]
    # exact matches first, then by closeness, then by how many attributes matched
    scored.sort(key=lambda p: (not p[0], -p[1], -p[2]))
    exacts = [t for t in scored if t[0]]
    chosen = exacts[:1] if exacts else scored[:5]     # one confident hit, else nearest few
    return [_make_hit(rec, doc, score=round(sv, 3)) for _ex, sv, _n, rec, doc in chosen]


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
