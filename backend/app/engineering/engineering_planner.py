"""Engineering spec-generation engine — the formula / calc / material core.

This is where a requirement becomes a set of technical values, each with a
traceable ORIGIN and REASON. It owns the actual engineering computation:
  - rule-engine track: compute fields from formulas + standards,
  - case-based track: interpolate between bracketing offers, scale from the
    nearest design, snap to standard sizes, or reuse by historical consensus,
always tagging every value with how it was derived (rule / interpolated /
scaled / consistent / reused / given). `analysis.py` orchestrates matching,
confidence and presentation around this; the numbers are made HERE.

Deliberately depends only on catalog + spec_schema (no import of analysis), so
the dependency runs one way: analysis -> engineering_planner.
"""
from ..observability import trace as _obs
from ..catalog import label_for, origin_label
from ..spec_schema import (ATS, CONSENSUS, INTERPOLATED, REUSE, REUSE_KEPT,
                           SCALED)


# --- value primitives (shared with analysis, defined here as the lower layer) -

def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


# Sub-keys of a composite field are raw record keys ("blower_motor_hp"), so a
# plain .capitalize() printed "Moc" and "Inner size m". These are read by an
# engineer on a specification table, so the unit is bracketed and the trade
# acronyms keep their casing.
_ACRONYMS = {"moc", "hp", "cfm", "cmh", "kw", "rpm", "lpg", "plc", "hmi", "vfd",
             "ms", "ss", "gi", "id", "od", "ip", "ach", "lux", "nflp", "flp"}
_UNIT_SUFFIX = {"m": "m", "mm": "mm", "cm": "cm", "kg": "kg", "hp": "HP",
                "c": "deg C", "cmh": "m3/h", "cfm": "CFM", "kw": "kW",
                "min": "min", "hr": "hr", "l": "litre", "pct": "%"}


def _sub_label(key: str) -> str:
    parts = str(key).split("_")
    unit = ""
    # A trailing unit token becomes a bracketed unit, not a dangling word.
    if len(parts) > 1 and parts[-1].lower() in _UNIT_SUFFIX:
        unit = _UNIT_SUFFIX[parts.pop().lower()]
    words = [p.upper() if p.lower() in _ACRONYMS else p for p in parts]
    text = " ".join(words)
    text = text[:1].upper() + text[1:] if text else text
    return f"{text} ({unit})" if unit else text


def _fmt(v):
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{round(v, 2):g}"        # 1.0346... -> 1.03, never raw float noise
    # A composite field (a powder-coating plant records its booth / oven /
    # recovery module as a nested object) must NOT fall through to str(): that
    # printed a raw Python dict repr — braces, quotes and all — straight into
    # the customer-facing specification table and the drawing legend. Flatten it
    # into readable engineering text instead. No value is dropped or reworded;
    # only the punctuation between them changes.
    if isinstance(v, dict):
        return "; ".join(f"{_sub_label(k)}: {_fmt(sv)}"
                         for k, sv in v.items() if sv not in (None, "", []))
    if isinstance(v, (list, tuple)):
        return ", ".join(_fmt(x) for x in v if x not in (None, "", []))
    return str(v)


def _given(o):
    return o["record"].get("given_data", {}) if o else {}


def _tech(o):
    return o["record"].get("technical_details", {}) if o else {}


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return str(a).strip().lower() == str(b).strip().lower()


# --- spec generation with source + reason ----------------------------------

def _item(label, value, origin, source, reason):
    item = {"label": label, "value": _fmt(value), "origin": origin,
            "origin_label": origin_label(origin), "source": source, "reason": reason}
    # Keep the ORIGINAL sub-values of a composite field alongside the flattened
    # display string. The GA drawing needs the plant's real module sizes
    # (booth `inner_size_m`, oven `inner_size_m`, conveyor `track_length_m`) and
    # re-parsing them back out of prose would be a second, drifting parser.
    # Display and geometry therefore read the SAME resolved values.
    if isinstance(value, dict):
        item["parts"] = {str(k): value[k] for k in value}
    return item


def _short_std(s):
    return str(s).split("(")[0].strip()


def generate_spec(profile, category, params, chosen, offers, policy=ATS):
    with _obs.span("rules.apply", "rules") as _s:
        out = _generate_spec_inner(profile, category, params, chosen, offers, policy)
        try:
            rules = sum(1 for i in (out[0] if isinstance(out, tuple) else out)
                        if str(i.get("origin")) in ("rule", "standard", "advisory"))
            _s.detail(rules=rules, category=category)
            _obs.count("rule_count", rules)
        except Exception:
            pass
        return out


def _generate_spec_inner(profile, category, params, chosen, offers, policy=ATS):
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
                # Keep the value's own provenance when it carries one (advisory /
                # standard / customer_decision from the client's standards
                # package); only default to "rule" for a plain calculation.
                origin = v.origin if v.origin in ("advisory", "standard",
                                                  "customer_decision") else "rule"
                verb = {"advisory": "Recommended", "standard": "Per standard"}.get(origin, "Calculated")
                items.append(_item(v.label, v.value, origin, _short_std(rule.standard),
                                   f"{verb}: {rule.formula} ({rule.standard})."))
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
