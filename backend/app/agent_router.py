"""Agent router — the request-shaping brain that sits in front of the resolver.

Decides, per question: which policy (Consulting knowledge-mode vs ATS data-mode),
what to retrieve and how to scope it, and assembles the analysis + response
metadata. This is the code the next-phase architecture calls `agent_router.py`;
it was extracted verbatim from `main.py` so the two `/api/query*` endpoints and
the Flowise `generate_specification` tool share one routing path.

Numbers still come only from the deterministic resolver/pricing — this module
routes and scopes, it never invents a value (golden rule #2).
"""
from __future__ import annotations

from . import config
from .analysis import essential_present, requirement_completeness
from .catalog import get_profile
from .quotation import build_quotation
from .resolver import ATS, CONSULTING, resolve
from .retriever import (all_hits, entity_hits, has_offers, is_analytical,
                        is_comparison, is_data_lookup, is_overview,
                        references_existing_data, retrieve, summarize_retrieval)
from .understand import contextualize, understand


def prepare(question: str, top_k: int | None, history=None):
    """Shared pipeline: UNDERSTAND -> retrieve -> ANALYZE. Returns (hits, analysis,
    grounded). Used by both the streaming and non-streaming endpoints."""
    u = understand(question)
    structured = u.intent in ("specification", "quotation")

    # HYBRID ROUTING (the flagship): for a spec, decide by REQUIREMENT
    # COMPLETENESS, not by a manual mode switch —
    #   * essential sizing input present AND >= HYBRID_THRESHOLD of inputs given
    #     (or the user explicitly said "refer db")  -> Quotation Engineer
    #     (history + engineering rules + validation), and
    #   * otherwise -> Consulting Engineer (ask for the missing inputs, no guess).
    completeness, missing_inputs = 1.0, []
    use_data = False
    if structured:
        profile = get_profile(u.category)
        completeness, missing_inputs = requirement_completeness(profile, u.parameters)
        essential = essential_present(profile, u.parameters)
        refer_db = references_existing_data(question)
        # Quotation is only possible if the category is BUILDABLE — it has
        # engineering rules or at least one stored offer. Otherwise (e.g. an oven
        # with no rules and no history yet) we consult conceptually instead of
        # hitting a dead end.
        # ADAPTABLE = we can actually ENGINEER/scale this category (it has rules,
        # field rules, or a sizing driver with scalable fields). A category with
        # only historical offers but no adaptation logic would merely COPY the
        # nearest project — so we do NOT auto-build it from data. Instead we reason
        # from engineering knowledge (Consulting), treating stored offers as
        # reference evidence, and only build from data when the user explicitly
        # asks ("refer db").
        adaptable = bool(profile and (
            profile.get("rules") or profile.get("field_rules")
            or (profile.get("scale_driver") and profile.get("scalable"))))
        # CASE-BASED = no closed-form rules, but we DO reuse the nearest matching
        # historical design deterministically (e.g. ovens). Distinct from adaptable
        # (which SCALES) — case-based REUSES. Build from data whenever the category
        # has offers and the user gave something to match on, so the model never has
        # to invent an oven's dimensions/heating/insulation from an empty spec.
        case_based = bool(profile and profile.get("case_based"))
        buildable = adaptable or has_offers(u.category)
        wants_quote = u.intent == "quotation"
        use_data = buildable and (
            refer_db
            or (adaptable and essential and completeness >= config.HYBRID_THRESHOLD)
            or (case_based and has_offers(u.category) and bool(u.parameters))
            or (wants_quote and essential))

    # Multi-turn memory: resolve a short/pronoun follow-up ("compare it with the
    # other") against the previous question so retrieval finds the right records.
    search_q = question if structured else contextualize(question, history)

    where = {"category": u.category} if (u.category and use_data) else None
    hits = retrieve(search_q, top_k, where=where)

    mode = None
    data_lookup = False
    if not structured:
        analytical = is_analytical(search_q)
        comparison = (u.intent == "comparison") or is_comparison(search_q)
        named = entity_hits(search_q)
        # Grounding set:
        #  - comparison of NAMED clients -> just those records; else the whole KB;
        #  - a SPECIFIC named client/offer (even if worded like an overview, e.g.
        #    "what did C2C order") -> ONLY that client's records, so the model
        #    isn't handed the whole corpus and can't blend unrelated clients;
        #  - analytics / overview enumeration -> the WHOLE KB;
        #  - otherwise the semantic hits already suffice.
        scoped = False
        if comparison:
            extra = named if len(named) >= 2 else all_hits()
        elif named and not analytical:
            extra, scoped = named, True
        elif analytical or is_overview(search_q):
            extra = all_hits()
        else:
            extra = named
        if extra:
            if scoped:                          # replace: don't dilute with neighbours
                hits = extra
            else:
                seen = {h["id"] for h in extra}
                hits = extra + [h for h in hits if h["id"] not in seen]
        mode = "analytical" if analytical else "comparison" if comparison else None
        # Verify only plain direct lookups — NOT computed analytics/comparisons
        # (their result isn't a literal stored fact, and verify could mangle the
        # table). Those rely on full-data grounding + low temperature instead.
        data_lookup = is_data_lookup(search_q) and mode is None

    # One resolver, two policies (the ONLY place the product split lives):
    #   Consulting Engineer  -> knowledge policy (ask for missing inputs, no guess)
    #   ATS Engineering Expert -> data policy (history + rules + validation)
    if structured and not use_data:
        analysis = resolve(question, hits, u, CONSULTING)
        analysis["completeness"] = round(completeness * 100)
        analysis["completeness_missing"] = missing_inputs
    else:
        analysis = resolve(question, hits, u, ATS)
        if structured:
            analysis["spec_mode"] = "data"
            # Quotation Agent: layer a budgetary quote on top of the data-mode spec
            # (deterministic price + scope + terms). Additive — the spec is unchanged.
            if u.intent == "quotation":
                quote = build_quotation(analysis, dict(u.parameters))
                if quote:
                    analysis["quotation"] = quote

    relevant = [h for h in hits if h["score"] >= config.RELEVANCE_THRESHOLD]
    grounded = use_data if structured else bool(relevant or mode or data_lookup)
    analysis["grounded"] = grounded
    analysis["data_lookup"] = data_lookup           # gates the self-verify pass
    analysis["mode"] = mode                         # analytical / comparison / None
    if mode:
        analysis["intent"] = mode                   # nicer badge + tailored prompt
    return hits, analysis, grounded


def build_meta(question, sid, hits, analysis, grounded):
    sources = [
        {"id": h["id"], "title": h["title"], "type": h["type"],
         "score": h["score"], "source_file": h["record"].get("source_file")}
        for h in hits
    ]
    # Only cite documents that actually influenced the result:
    #  - data-mode spec -> just the offer it was built from;
    #  - knowledge-mode spec -> none (designed from general knowledge).
    sm = analysis.get("spec_mode")
    if sm == "knowledge":
        sources = []
    elif sm == "data":
        chosen = analysis.get("exact_match") or analysis.get("nearest_match")
        sources = [s for s in sources if s["id"] == chosen] or sources[:1]

    return {
        "session_id": sid,
        "question": question,
        "intent": analysis["intent"],
        "category": analysis["category"],
        "category_label": analysis["category_label"],
        "confidence": analysis.get("confidence_label"),
        "grounded": grounded,
        "retrieval_steps": summarize_retrieval(hits),
        "analysis": analysis,
        "quotation": analysis.get("quotation"),   # budgetary quote (quotation intent)
        "sources": sources,
    }
