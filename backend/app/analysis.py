"""Engineering Reasoning Engine (category-agnostic, explainable).

For a new requirement it:
  1. picks the equipment category and candidate historical offers,
  2. scores the engineering match (dimension / process / driver / overall),
     NOT raw embedding similarity,
  3. GENERATES each technical value with a traceable SOURCE and REASON
     (historical offer id, engineering standard, or calculation) — never a
     vague invented justification,
  4. compares the alternative offers, lists assumptions/missing inputs, and
     reports a numeric confidence with a criteria checklist.

The LLM only narrates this; all reasoning is deterministic and verifiable.
"""
import re
from typing import Any, Optional

from collections import Counter

from .catalog import (DECISION_ORIGIN_ORDER, DECISION_TYPES, get_profile,
                      label_for, origin_label)
from .ledger import build_ledger
from .schema import QueryUnderstanding
from .spec_schema import (ATS, CONSENSUS, INTERPOLATED, REUSE, REUSE_KEPT,
                          SCALED)
from .validate import cross_validate, validate

_STRUCTURED = {"specification", "quotation"}


def _required(profile) -> list:
    """The REQUIRED inputs to size this equipment (falls back to expected_inputs
    for older profiles). Optional inputs are not counted against completeness and
    are never demanded from the user."""
    if not profile:
        return []
    return profile.get("required_inputs") or profile.get("expected_inputs", [])


def requirement_completeness(profile, params: dict) -> tuple[float, list[str]]:
    """How much of the REQUIRED input set the user supplied.
    Returns (0..1 score, list of missing REQUIRED input labels)."""
    req = _required(profile)
    if not req:
        return (1.0 if params else 0.0), []
    provided = [k for k, _ in req if k in params]
    missing = [label for k, label in req if k not in params]
    return len(provided) / len(req), missing


def essential_present(profile, params: dict) -> bool:
    """Is the primary sizing input present (airflow for a scrubber, length+width
    for a booth)? Without it nothing can be computed, so we must consult first."""
    if not profile:
        return bool(params)
    driver = profile.get("scale_driver")
    if driver:
        return driver in params
    dims = profile.get("dimension_keys", [])
    if dims:
        return all(d in params for d in dims[:2])
    return bool(params)


def requirement_only(u: QueryUnderstanding) -> dict[str, Any]:
    """Knowledge-mode spec: the LLM designs from its own engineering knowledge,
    so we do NOT match/scale stored offers (that mismatches with sparse data).
    We just echo the requirement; the spec itself is written by the model."""
    category = u.category
    profile = get_profile(category)
    params = dict(u.parameters)
    return {
        "intent": u.intent,
        "category": category,
        "category_label": profile["label"] if profile else (category or "Equipment"),
        "understanding": u.model_dump(),
        "spec_mode": "knowledge",
        "given_data": _given_echo(category, params, None),
        "technical_details": [],          # written by the LLM as prose, not a table
        "similar_offers": [],
        "exact_match": None, "nearest_match": None, "match": None,
        "confidence_label": None, "confidence_pct": None,
    }


def analyze(question: str, hits: list[dict[str, Any]], u: QueryUnderstanding,
            policy=ATS) -> dict[str, Any]:
    category = u.category or _infer_category(hits)
    profile = get_profile(category)
    params = dict(u.parameters)

    offers = [h for h in hits if h["record"].get("type") == "offer"
              and (category is None or h["record"].get("category") == category)]
    if not offers:
        offers = [h for h in hits if h["record"].get("type") == "offer"]

    offers = _rank_by_given(offers, params)
    exact = _exact_offer(offers, params)
    nearest = offers[0] if offers else None
    chosen = exact or nearest

    structured = u.intent in _STRUCTURED
    match = _match_breakdown(params, chosen, profile) if (structured and chosen) else None
    technical, rules_list = ([], [])
    if structured:
        technical, rules_list = _generate_spec(profile, category, params, chosen, offers, policy)

    assumptions, missing = _assumptions_and_missing(profile, params, offers) if structured else ([], [])
    validation = ((validate(category, params) + cross_validate(category, params, chosen, technical))
                  if structured else [])
    confidence, conf_label, criteria, conf_factors, conf_notes = _confidence(
        match, technical, profile, params, missing, len(offers), validation)
    similar = _similar(offers[:5], params, profile)
    knowledge_used, knowledge_contribution = _knowledge(technical, rules_list, offers)
    decision_origin = _decision_origin(knowledge_used.get("breakdown", {}))
    comp_score, comp_missing = requirement_completeness(profile, params)

    return {
        "intent": u.intent,
        "category": category,
        "category_label": profile["label"] if profile else (category or "Equipment"),
        "understanding": u.model_dump(),
        "given_data": _given_echo(category, params, chosen),
        "similar_offers": similar,
        "exact_match": exact["id"] if exact else None,
        "nearest_match": nearest["id"] if nearest else None,
        "match": match,                       # dimension/process/driver/historical/overall (%)
        "rules": rules_list,
        "technical_details": technical,       # each: label,value,origin,origin_label,source,reason
        "ledger": build_ledger(technical),    # traceable audit trail of every value
        "knowledge_used": knowledge_used,     # counts of offers/rules/standards/components
        "knowledge_contribution": knowledge_contribution,  # % per source
        "decision_origin": decision_origin,   # canonical [{type,count}] table
        "validation": validation,             # engineering sanity checks {level,message}
        "completeness": round(comp_score * 100),
        "completeness_missing": comp_missing,
        "assumptions": assumptions,           # missing inputs filled by historical consensus
        "missing_inputs": missing,            # inputs with no consensus to assume
        "criteria": criteria,
        "confidence": confidence,             # 0..1
        "confidence_pct": round(confidence * 100),
        "confidence_label": conf_label,
        "confidence_factors": conf_factors,   # how the confidence was derived
        "confidence_notes": conf_notes,       # why it was reduced
        "justification": _justify(u, exact, nearest, category, match),
        "sources": [h["id"] for h in hits[:5]],
        "source_files": [h["record"].get("source_file") for h in hits[:5]
                         if h["record"].get("source_file")],
    }


# --- small helpers ---------------------------------------------------------

def _infer_category(hits):
    for h in hits:
        if h["record"].get("type") == "offer" and h["record"].get("category"):
            return h["record"]["category"]
    return None


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def _fmt(v):
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{round(v, 2):g}"        # 1.0346... -> 1.03, never raw float noise
    return str(v)


def _given(o):
    return o["record"].get("given_data", {}) if o else {}


def _tech(o):
    return o["record"].get("technical_details", {}) if o else {}


def _field_score(p, o):
    if isinstance(o, (int, float)) and isinstance(p, (int, float)):
        if o == 0:
            return 1.0 if p == 0 else 0.0
        return max(0.0, 1 - abs(p - o) / abs(o))
    # fuzzy string match: equal / substring / token overlap
    sp = re.sub(r"[-_]+", " ", str(p).lower()).strip()
    so = re.sub(r"[-_]+", " ", str(o).lower()).strip()
    if sp == so or sp in so or so in sp:
        return 1.0
    ts, to = set(sp.split()), set(so.split())
    return len(ts & to) / len(ts | to) if (ts and to) else 0.0


def _avg_match(params, gd, keys):
    scores = [_field_score(params[k], gd[k]) for k in keys if k in params and k in gd]
    return sum(scores) / len(scores) if scores else None


# --- ranking / matching ----------------------------------------------------

def _rank_by_given(offers, params):
    numeric = {k: v for k, v in params.items() if isinstance(v, (int, float))}
    if not numeric or not offers:
        return offers

    def dist(h):
        gd = _given(h)
        tot, n = 0.0, 0
        for k, v in numeric.items():
            ov = _num(gd.get(k))
            if ov is None:
                continue
            tot += abs(v - ov) / max(abs(ov), 1.0)
            n += 1
        return tot / n if n else float("inf")

    return sorted(offers, key=dist)


def _exact_offer(offers, params):
    numeric = {k: v for k, v in params.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    for h in offers:
        gd = _given(h)
        present = [k for k in numeric if _num(gd.get(k)) is not None]
        if present and all(_num(gd.get(k)) == numeric[k] for k in present):
            return h
    return None


def _match_breakdown(params, chosen, profile):
    """Engineering match (not embedding similarity)."""
    gd = _given(chosen)
    dim_keys = profile.get("dimension_keys", []) if profile else []
    proc_keys = profile.get("process_keys", []) if profile else []
    driver = profile.get("scale_driver") if profile else None

    dimension = _avg_match(params, gd, dim_keys)
    process = _avg_match(params, gd, proc_keys)
    driver_score = (_field_score(params[driver], gd[driver])
                    if driver and driver in params and driver in gd else None)
    historical = chosen["score"]

    eng_parts = [x for x in (dimension, process, driver_score) if x is not None]
    eng = sum(eng_parts) / len(eng_parts) if eng_parts else historical
    overall = 0.85 * eng + 0.15 * historical

    def pct(x):
        return None if x is None else round(x * 100)

    return {
        "dimension": pct(dimension),
        "process": pct(process),
        "driver": pct(driver_score),
        "driver_label": profile.get("driver_label", "Driver") if profile else "Driver",
        "historical": pct(historical),
        "overall": pct(overall),
        "_eng": eng,
    }


# --- spec generation with source + reason ----------------------------------

def _item(label, value, origin, source, reason):
    return {"label": label, "value": _fmt(value), "origin": origin,
            "origin_label": origin_label(origin), "source": source, "reason": reason}


def _short_std(s):
    return str(s).split("(")[0].strip()


def _generate_spec(profile, category, params, chosen, offers, policy=ATS):
    base = _tech(chosen)
    cid = chosen["id"] if chosen else None
    items, rules_list = [], []

    # Track A — rule engine (true knowledge): compute from formulas + standards.
    if profile and profile.get("rules"):
        computed = profile["rules"](params)
        rules_list = [r.model_dump() for r in computed.rules]
        rules_by_name = {r.name: r for r in computed.rules}
        for v in computed.values:
            rule = _match_rule(v.label, rules_by_name)
            if rule:
                items.append(_item(v.label, v.value, "rule", _short_std(rule.standard),
                                   f"Calculated: {rule.formula} ({rule.standard})."))
            else:
                items.append(_item(v.label, v.value, "given", "requirement",
                                   "Derived from the client requirement."))
        covered = set(profile.get("rule_covers", []))
        for k, val in base.items():
            if k in covered:
                continue
            if not policy.can_author(REUSE_KEPT):   # history may not author under this policy
                continue
            items.append(_item(label_for(category, k), val, "kept", cid,
                               f"Reused from historical offer {cid}."))
        return items, rules_list

    # Track B — case-based reasoning: interpolate / scale / reuse with traceable reasons.
    driver = profile.get("scale_driver") if profile else None
    unit = profile.get("diff_unit", "value") if profile else "value"
    driver_label = (profile.get("driver_label", "driver") if profile else "driver").lower()
    ratio = _ratio(params, chosen, driver)
    exact_driver = ratio is not None and abs(ratio - 1.0) < 0.02
    scalable = set(profile["scalable"]) if profile else set()
    from_given = profile["from_given"] if profile else {}
    target_to_given = {t: g for g, t in from_given.items()}
    req_d = params.get(driver) if driver else None
    off_d = _given(chosen).get(driver) if driver else None

    # Field-level engineering rules: compute these fields from formulas (origin
    # "rule") instead of scaling them from the nearest offer. Calibrated to the
    # historical data, so rule and history agree — but now it's traceable physics.
    field_rules = profile.get("field_rules") if profile else None
    rule_map = field_rules(params) if field_rules else {}
    rules_list = []
    for rk, rc in rule_map.items():
        snapped, _ = _snap(profile, rk, rc["value"])
        rules_list.append({"name": label_for(category, rk), "value": _fmt(snapped),
                           "formula": rc["formula"], "standard": rc["standard"]})

    n_offers = len(offers)
    for k, val in base.items():
        # REQUIREMENT IS AUTHORITATIVE: if the client provided this field
        # (directly, or via a from_given alias), use THEIR value — never a
        # historical one. Historical offers fill gaps, they don't overwrite.
        if k in params and not isinstance(params[k], dict):
            items.append(_item(label_for(category, k), params[k], "given", "requirement",
                               "Client requirement (authoritative)."))
            continue
        gkey = target_to_given.get(k)
        if gkey and gkey in params:
            items.append(_item(label_for(category, k), params[gkey], "given", "requirement",
                               "Client requirement (authoritative)."))
            continue

        # ENGINEERING RULE: compute this field from a formula + standard, snapped
        # to a standard size. Takes priority over scaling/reuse, but never over a
        # client requirement (handled above).
        if k in rule_map:
            rc = rule_map[k]
            snapped, note = _snap(profile, k, rc["value"])
            reason = f"{rc['formula']} ({rc['standard']}){note}."
            items.append(_item(label_for(category, k), snapped, "rule",
                               _short_std(rc["standard"]), reason))
            continue

        # Scalable numeric -> synthesize from MULTIPLE projects (interpolate), else scale.
        # Result is snapped to a standard size where one is defined.
        if k in scalable and isinstance(val, (int, float)) and not exact_driver and req_d is not None:
            interp = _interpolate(k, req_d, offers, driver) if policy.can_author(INTERPOLATED) else None
            if interp:
                v, lo, hi, lo_v, hi_v, lo_d, hi_d = interp
                u = driver.rsplit("_", 1)[-1].upper()  # CFM
                snapped, note = _snap(profile, k, v)
                it = _item(label_for(category, k), snapped, "interpolated", f"{lo} + {hi}",
                           f"Linear interpolation: {lo} ({_fmt(lo_d)} {u} -> {_fmt(lo_v)}) and "
                           f"{hi} ({_fmt(hi_d)} {u} -> {_fmt(hi_v)}); requested {_fmt(req_d)} {u}{note}.")
                items.append(it)
                continue
            if ratio is not None and policy.can_author(SCALED):
                raw = _scale(val, ratio)
                snapped, note = _snap(profile, k, raw)
                if note:    # a standard engineering size was selected
                    reason = (f"Calculated {_fmt(raw)} for the requested {driver_label}; "
                              f"selected the nearest ATS standard ({_fmt(snapped)}).")
                else:
                    reason = (f"Scaled from nearest design {cid} to match the requested "
                              f"{driver_label} ({_fmt(req_d)} vs {_fmt(off_d)}).")
                items.append(_item(label_for(category, k), snapped, "scaled", cid, reason))
                continue

        # Categorical / fixed values: is this a company standard (shared across projects)?
        support = _support_count(k, val, offers)
        consensus_ok = support >= 2 and support >= (n_offers + 1) // 2
        if consensus_ok and policy.can_author(CONSENSUS):
            it = _item(label_for(category, k), val, "consistent", "company standard",
                       f"Observed in {support} of {n_offers} comparable projects (historical consensus).")
            it["support"] = f"{support}/{n_offers}"
            items.append(it)
        elif policy.can_author(REUSE):
            reason = (f"Reused from nearest design {cid} (exact {driver_label} match)."
                      if exact_driver else f"Reused from nearest design {cid}.")
            items.append(_item(label_for(category, k), val, "reused", cid, reason))
    return items, rules_list


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return str(a).strip().lower() == str(b).strip().lower()


def _support_count(field, value, offers):
    return sum(1 for o in offers if _tech(o).get(field) is not None and _same(_tech(o)[field], value))


def _interpolate(field, req_d, offers, driver):
    """Synthesize a value from the two historical offers that bracket the
    requirement on the driver (e.g. tank 300 L between 250 L and 340 L)."""
    pts = []
    for o in offers:
        dv, tv = _num(_given(o).get(driver)), _num(_tech(o).get(field))
        if dv is not None and tv is not None:
            pts.append((dv, tv, o["id"]))
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])
    lower = upper = None
    for dv, tv, oid in pts:
        if dv <= req_d:
            lower = (dv, tv, oid)
        if dv >= req_d and upper is None:
            upper = (dv, tv, oid)
    if not lower or not upper or lower[0] == upper[0]:
        return None
    frac = (req_d - lower[0]) / (upper[0] - lower[0])
    raw = lower[1] + frac * (upper[1] - lower[1])
    whole = float(lower[1]).is_integer() and float(upper[1]).is_integer()
    val = max(1, int(raw + 0.5)) if whole else round(raw, 1)
    # (value, lower_id, upper_id, lower_val, upper_val, lower_driver, upper_driver)
    return (val, lower[2], upper[2], lower[1], upper[1], lower[0], upper[0])


_SOURCE_LABELS = {"requirement": "Client requirement", "company standard": "Company standard practice"}


def _knowledge(technical, rules_list, offers):
    """Knowledge reasoning summary: sources used, decision-type breakdown, and
    per-source contribution %."""
    standards = {r["standard"] for r in rules_list}
    for o in offers:
        s = _tech(o).get("standard")
        if s:
            standards.add(s)

    breakdown: dict[str, int] = {}
    for it in technical:
        dtype = DECISION_TYPES.get(it["origin"], "Reused")
        breakdown[dtype] = breakdown.get(dtype, 0) + 1

    used = {
        "historical_projects": len(offers),
        "rules": len(rules_list),
        "standards": len(standards),
        "components_compared": sum(len(_tech(o)) for o in offers),
        "decisions": len(technical),
        "breakdown": breakdown,   # {Calculated, Inferred, Standard, Reused, Given}
    }

    contrib: dict[str, int] = {}
    for it in technical:
        for tok in str(it["source"]).split("+"):
            tok = tok.strip()
            if not tok:
                continue
            name = _SOURCE_LABELS.get(tok, tok)
            contrib[name] = contrib.get(name, 0) + 1
    total = sum(contrib.values()) or 1
    contribution = sorted(
        [{"source": s, "pct": round(c / total * 100)} for s, c in contrib.items()],
        key=lambda x: -x["pct"])
    return used, contribution


def _match_rule(value_label, rules_by_name):
    if value_label in rules_by_name:
        return rules_by_name[value_label]
    for name, rule in rules_by_name.items():
        a, b = name.lower(), value_label.lower()
        if a in b or b in a:
            return rule
    return None


def _ratio(params, chosen, driver):
    if not (driver and chosen):
        return None
    pv, ov = _num(params.get(driver)), _num(_given(chosen).get(driver))
    if pv is None or not ov:
        return None
    return pv / ov


def _scale(val, ratio):
    scaled = val * ratio
    if isinstance(val, int):
        return max(1, int(scaled + 0.5))
    return round(scaled, 1)


def _snap(profile, field, value):
    """Snap a calculated value to a standard engineering size. Returns
    (snapped_value, note) where note explains the calculated->standard step."""
    if not profile:
        return value, ""
    stds = (profile.get("standard_sizes") or {}).get(field)
    if stds:
        nearest = min(stds, key=lambda s: abs(s - value))
        if abs(nearest - value) > 1e-9:
            return nearest, f"; calculated {_fmt(value)}, selected nearest standard {_fmt(nearest)}"
        return nearest, ""
    rt = (profile.get("round_to") or {}).get(field)
    if rt:
        snapped = round(value / rt) * rt
        snapped = int(snapped) if float(snapped).is_integer() else round(snapped, 2)
        return snapped, ""
    return value, ""


# --- similar offers with difference ----------------------------------------

def _driver_metric(gd, profile):
    dk = profile.get("scale_driver") if profile else None
    if dk and isinstance(gd.get(dk), (int, float)):
        return gd[dk]
    if isinstance(gd.get("length_m"), (int, float)) and isinstance(gd.get("width_m"), (int, float)):
        return gd["length_m"] * gd["width_m"]
    return None


def _similar(offers, params, profile):
    unit = profile.get("diff_unit", "value") if profile else "value"
    req_m = _driver_metric(params, profile)
    out = []
    for h in offers:
        gd = _given(h)
        om = _driver_metric(gd, profile)
        if req_m and om:
            d = (om - req_m) / req_m
            if abs(d) < 0.02:
                diff = f"Exact {unit}"
            elif abs(d - 1.0) < 0.12:
                diff = f"~2x {unit}"
            elif abs(d + 0.5) < 0.08:
                diff = f"~half {unit}"
            else:
                diff = f"{'+' if d >= 0 else ''}{round(d * 100)}% {unit}"
        else:
            diff = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in list(gd.items())[:2])
        out.append({
            "id": h["id"], "title": h["record"].get("title", h["id"]),
            "source_file": h["record"].get("source_file"),
            "score": h["score"], "summary": ", ".join(
                f"{k.replace('_', ' ')} {v}" for k, v in list(gd.items())[:3]),
            "difference": diff,
        })
    return out


# --- confidence + criteria + missing inputs --------------------------------

def _assumptions_and_missing(profile, params, offers):
    """Split unprovided inputs into ASSUMPTIONS (historical consensus exists) and
    MISSING (no basis to assume)."""
    assumptions, missing = [], []
    if not profile:
        return assumptions, missing
    n = len(offers)
    for key, label in profile.get("expected_inputs", []):
        if key in params:
            continue
        vals = [_given(o).get(key) for o in offers if _given(o).get(key) not in (None, "")]
        if vals:
            val, cnt = Counter(str(v) for v in vals).most_common(1)[0]
            if cnt >= 2 and cnt / n >= 0.6:   # strong historical consensus only
                pct = round(cnt / n * 100)
                assumptions.append({
                    "label": label, "value": val,
                    "reason": f"Assumed {val}; used in {cnt} of {n} comparable projects ({pct}%)."})
                continue
        missing.append(label)
    return assumptions, missing


_CONF_WEIGHTS = {"completeness": 0.30, "historical": 0.30, "rules": 0.25, "validation": 0.15}


def _confidence(match, technical, profile, params, missing, n_offers, validation):
    """Meaningful, multi-factor confidence — the user can see WHY. Overall is a
    weighted blend of four independent factors, each shown separately:
      completeness  — share of expected inputs provided
      historical    — how much comparable project evidence exists
      rule coverage — share of decisions backed by a rule/requirement/consensus
      validation    — engineering sanity checks that passed
    Returns (conf, label, criteria, factors, notes)."""
    required = _required(profile)
    total_exp = len(required) or 1
    provided = sum(1 for k, _ in required if k in params)
    completeness = provided / total_exp

    historical = min(1.0, n_offers / 3.0)

    total_dec = len(technical) or 1
    backed = sum(1 for it in technical if it["origin"] not in ("reused", "kept"))
    rule_coverage = backed / total_dec

    n_val = len(validation or [])
    warns = sum(1 for c in (validation or []) if c.get("level") == "warn")
    validation_score = 1.0 if not warns else max(0.0, 1 - warns / max(1, n_val))

    w = _CONF_WEIGHTS
    conf = round(w["completeness"] * completeness + w["historical"] * historical
                 + w["rules"] * rule_coverage + w["validation"] * validation_score, 2)
    label = "High" if conf >= 0.8 else "Medium" if conf >= 0.6 else "Low"

    notes = []
    if n_offers < 3:
        plural = "s" if n_offers != 1 else ""
        notes.append(f"Limited evidence - only {n_offers} historical project{plural} in this category.")
    if missing:
        notes.append("Missing inputs: " + ", ".join(missing) + ".")
    if warns:
        notes.append(f"{warns} engineering check(s) flagged - see Engineering checks.")

    factors = [
        {"label": "Requirement completeness", "value": f"{round(completeness * 100)}% ({provided}/{total_exp} inputs)"},
        {"label": "Historical evidence", "value": f"{round(historical * 100)}% ({n_offers} project(s))"},
        {"label": "Rule coverage", "value": f"{round(rule_coverage * 100)}% ({backed}/{total_dec} decisions)"},
        {"label": "Validation", "value": f"{round(validation_score * 100)}%"},
    ]
    return conf, label, [], factors, notes


def _decision_origin(breakdown):
    rows, seen = [], set()
    for t in DECISION_ORIGIN_ORDER:
        rows.append({"type": t, "count": breakdown.get(t, 0)})
        seen.add(t)
    for t, c in breakdown.items():
        if t not in seen:
            rows.append({"type": t, "count": c})
    return rows


def _given_echo(category, params, chosen):
    src = params if params else _given(chosen)
    # When booth dimensions were DERIVED from a job envelope, the client did not
    # give length/width/height — show the job size they gave; the booth size
    # appears in the technical section as a computed value. Internal ("_") keys
    # are never echoed.
    skip = {"length_m", "width_m", "height_m"} if "job_size" in src else set()
    return [{"label": label_for(category, k), "value": _fmt(v)}
            for k, v in src.items() if not k.startswith("_") and k not in skip]


def _justify(u, exact, nearest, category, match):
    if u.intent in ("concept", "comparison", "general"):
        return f"Conceptual question on '{u.topic or 'engineering'}' — answered from the documents."
    if not nearest:
        return "No close historical offer was found for this requirement."
    pct = match["overall"] if match else None
    who = exact["id"] if exact else nearest["id"]
    qualifier = (f"a {pct}% engineering match" if pct is not None else "the closest design")
    if exact:
        return (f"Built from historical offer {who} ({qualifier}). Reused values are taken "
                f"directly from that offer; computed values follow the cited engineering rules.")
    return (f"Built from the closest historical offer {who} ({qualifier}). Values that scale "
            f"with the requirement were scaled from it; component choices were reused; "
            f"each value cites its source.")
