"""Requirement Understanding — the LLM IS the NLP.

Turns a natural-language request into a typed, category-agnostic
QueryUnderstanding (intent + equipment category + given-data parameters).
Uses the LLM in JSON mode, with a regex/keyword fallback when the LLM is
unavailable or too slow. No classical NLP library is needed.
"""
import json
import re

import httpx

from . import config
from .catalog import known_categories
from .classify import CONFIDENT, classify_equipment
from .schema import QueryUnderstanding

# --- regex/keyword fallback (fast, no LLM) ---------------------------------

_DIM_PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|meter|metre)?\s*[x×*]\s*(\d+(?:\.\d+)?)", re.I)
# three-dimension envelope, e.g. "8 x 4 x 3.5 m" -> L x W x H
_DIM_TRIPLE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:m|meter|metre)?\s*[x×*]\s*"
    r"(\d+(?:\.\d+)?)\s*(?:m|meter|metre)?\s*[x×*]\s*(\d+(?:\.\d+)?)", re.I)
_BOOTH_TYPE = re.compile(r"\b(?:(dry|wet)\s+)?(side|down|cross)[\s-]?draft\b", re.I)
_THROUGHPUT = re.compile(
    r"(\d+)\s*(?:components?|parts?|pieces?|jobs?|units?)\s*(?:per|/|a)\s*"
    r"(shift|hour|hr|day|week|month)", re.I)
_CFM = re.compile(r"(\d+(?:\.\d+)?)\s*cfm", re.I)
_CMH = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cmh|m3/?h|m³/?h)", re.I)
_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.I)
_HP = re.compile(r"(\d+(?:\.\d+)?)\s*hp", re.I)
_QTY = re.compile(r"(?:qty\s*[:\-]?\s*|(\d+)\s*(?:nos|no\.?|units?))", re.I)


def _dims_to_metres(dims: list[float], q: str, end: int) -> list[float]:
    """Normalise an L x W (x H) dimension group to metres.

    Booth/oven dimensions feed engineering rules that assume metres. A user may
    give them in mm ("1500 x 1200 x 1000 mm"), which without conversion produces
    absurd results (a 1500 m booth -> ~1.9 billion m3/h airflow). Convert when
    the group is explicitly suffixed 'mm', or when a value is far too large to be
    a booth in metres (no real booth is >= 100 m, so treat those as mm)."""
    explicit_mm = q[end:end + 4].lstrip().lower().startswith("mm")
    if explicit_mm or max(dims) >= 100:
        return [round(d / 1000.0, 3) for d in dims]
    return dims


# The user may state the JOB / workpiece envelope rather than the booth itself.
# When they do, derive the booth internal size instead of sizing the booth AS
# the part (which produced a tiny booth whose airflow disagreed with the blower).
_JOB_SIZE_CTX = re.compile(
    r"\b(?:job\s*size|work[\s-]?piece|component\s*size|part\s*size|product\s*size|"
    r"max(?:imum)?\s*(?:job|part|component|workpiece)|size\s*of\s*(?:job|part|component))\b",
    re.I)
_BOOTH_LIKE = {"paint_booth", "blast_booth"}


def _fmt_dims(dims: list[float]) -> str:
    return " x ".join(f"{d:g}" for d in dims) + " m"


def _job_to_booth(dims: list[float]) -> list[float]:
    """Booth internal size from the job envelope: add working clearance around the
    part (ATS practice ~1 m each side; minimum 2.5 m clear height)."""
    out = [round(dims[0] + 2.0, 2), round(dims[1] + 2.0, 2)]
    if len(dims) >= 3:
        out.append(round(max(dims[2] + 1.0, 2.5), 2))
    return out

_CATEGORY_KEYWORDS = {
    "wet_scrubber": ("scrubber", "wet scrubber", "demister", "spray nozzle"),
    "paint_booth": ("paint booth", "booth", "powder coat", "spray booth"),
}
_PAINTS = ["powder", "liquid", "solvent", "water-based", "water based"]


# Map the many ways an LLM/user names a field to our canonical schema keys.
_PARAM_ALIASES = {
    "diameter": "tower_diameter_mm", "diameter_mm": "tower_diameter_mm",
    "blower_diameter": "tower_diameter_mm", "blower_diameter_mm": "tower_diameter_mm",
    "tower_diameter": "tower_diameter_mm", "tower_dia": "tower_diameter_mm",
    "quantity": "qty", "nos": "qty", "units": "qty", "no_of_units": "qty", "number": "qty",
    "temperature": "operating_temp", "operating_temperature": "operating_temp", "temp": "operating_temp",
    "max_operating_temp": "operating_temp", "max_operating_temp_c": "operating_temp",
    "max_oven_temp": "operating_temp", "max_oven_temperature": "operating_temp",
    "oven_temp": "operating_temp", "operating_temp_c": "operating_temp", "max_temp": "operating_temp",
    # oven job/hook load -> the offer's given key, so a matching oven ranks first
    "job_weight": "job_weight_kg", "hook_load": "job_weight_kg", "hook_load_kg": "job_weight_kg",
    "max_hook_load": "job_weight_kg", "max_hook_load_kg": "job_weight_kg", "load_per_hook_kg": "job_weight_kg",
    "fuel": "heating_mode", "fuel_type": "heating_mode",
    "pressure": "operating_pressure",
    "airflow": "air_volume_cfm", "air_volume": "air_volume_cfm", "cfm": "air_volume_cfm",
    "flow_cfm": "air_volume_cfm", "air_flow_cfm": "air_volume_cfm",
    "cmh": "air_volume_cmh", "flow_cmh": "air_volume_cmh", "air_volume_cmh3": "air_volume_cmh",
    "length": "length_m", "width": "width_m", "height": "height_m",
    "paint": "paint_type", "process": "paint_type",
    "mounting": "blower_mounting", "drive": "blower_mounting", "blower": "blower_mounting",
}


def _normalize_params(params: dict) -> dict:
    out: dict = {}
    for k, v in (params or {}).items():
        if v in (None, ""):
            continue
        key = str(k).lower().strip()
        key = _PARAM_ALIASES.get(key, key)
        if key not in out:
            out[key] = v
    return out


def _detect_category(q: str) -> str | None:
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(k in q for k in kws):
            return cat
    return None


# --- multi-turn memory: resolve follow-ups against the previous question -----

_ANAPHORA = re.compile(
    r"\b(it|its|it's|that|this|they|them|those|these|the same|same one|"
    r"the other|another|the former|the latter|previous|above|both|either|"
    r"the one|that one|this one|the second|the third)\b", re.I)

# follow-up phrasings that carry no subject of their own
_FOLLOWUP_START = re.compile(r"^\s*(what about|how about|and |also |what else|then\b)", re.I)


def _last_user_question(history) -> str | None:
    for h in reversed(history or []):
        if h.get("role") == "user" and h.get("content"):
            return str(h["content"])
    return None


_INTERROGATIVE = re.compile(
    r"^\s*(what|how|why|who|which|where|when|is|are|do|does|can|could|"
    r"define|explain|convert|calculate|list|show|tell|give)\b", re.I)


def _is_followup(q: str) -> bool:
    # an anaphor ('compare it with the other') or a continuation opener
    # ('what about the oven?') is a follow-up; a bare 1-3 word fragment is too,
    # unless it's a standalone question ('what is CFM').
    if _ANAPHORA.search(q) or _FOLLOWUP_START.search(q):
        return True
    return len(q.split()) <= 3 and not _INTERROGATIVE.search(q)


def contextualize(question: str, history) -> str:
    """For pronoun-y or continuation follow-ups ('what about the oven?',
    'compare it with the other'), prepend the previous question so retrieval and
    entity lookup resolve what 'it / that / the other' refers to. Returns a
    search string used only for retrieval — the LLM still gets the real history.
    A complete standalone question is returned unchanged."""
    q = (question or "").strip()
    if not _is_followup(q):
        return q
    prev = _last_user_question(history)
    return f"{prev} {q}" if prev else q


def _fallback(question: str) -> QueryUnderstanding:
    q = question.lower()
    u = QueryUnderstanding(source="regex")
    u.category = _detect_category(q)
    params: dict = {}

    job_ctx = bool(_JOB_SIZE_CTX.search(q)) and u.category in _BOOTH_LIKE
    if (m := _DIM_TRIPLE.search(q)):
        dims = _dims_to_metres([float(m.group(1)), float(m.group(2)), float(m.group(3))], q, m.end())
        if job_ctx:
            params["job_size"] = _fmt_dims(dims)
            dims = _job_to_booth(dims)
        params["length_m"], params["width_m"], params["height_m"] = dims
    elif (m := _DIM_PAIR.search(q)):
        dims = _dims_to_metres([float(m.group(1)), float(m.group(2))], q, m.end())
        if job_ctx:
            params["job_size"] = _fmt_dims(dims)
            dims = _job_to_booth(dims)
        params["length_m"], params["width_m"] = dims[0], dims[1]
    if (c := _CFM.search(q)):
        params["air_volume_cfm"] = float(c.group(1))
    if (c := _CMH.search(q)):
        params["air_volume_cmh"] = float(c.group(1))
    # Only read a bare "NNN mm" as a tower/blower diameter when the text actually
    # talks about a tower or diameter. Without this guard the mm suffix on a booth
    # dimension triple ("1500 x 1200 x 1000 mm") was mis-captured as a tower
    # diameter on categories (e.g. paint_booth) that have no tower at all.
    if (c := _MM.search(q)) and re.search(r"tower|diameter|\bdia\b", q):
        params["tower_diameter_mm"] = float(c.group(1))
    if (c := _HP.search(q)):
        params["pump_capacity_hp"] = float(c.group(1))
    # Quantity may be written number-first ("4 nos / 4 units / 4 pcs / 4 sets")
    # or keyword-first ("quantity 4 / qty: 4 / qty of 4"). Recognise both - a
    # quote passed as "quantity 4" must not silently fall back to qty 1, which
    # printed a 1-unit total for a 4-unit order.
    qmatch = re.search(
        r"(\d+)\s*(?:nos?\.?|units?|pcs?\.?|sets?|numbers?|off)\b"
        r"|(?:qty|quantity)\s*(?:of\s+|[:\-]\s*)?(\d+)", q)
    if qmatch:
        params["qty"] = int(qmatch.group(1) or qmatch.group(2))
    for p in _PAINTS:
        if p in q:
            params["paint_type"] = p.replace(" ", "-")
            break
    else:
        # Application methods that imply a WET/liquid paint process (not powder).
        # "Air spray painting" is a liquid application; without this it was left
        # unrecognised and the spec kept asking for an already-stated paint process.
        if re.search(r"air[\s-]?spray|wet paint|conventional spray|\benamel\b", q):
            params["paint_type"] = "liquid"
    if "ambient" in q:
        params["operating_temp"] = "ambient"
    mt = re.search(r"operating temperature[:\s]+([a-z]+)", q)
    if mt:
        params["operating_temp"] = mt.group(1)
    if "direct drive" in q or "direct-drive" in q:
        params["blower_mounting"] = "direct drive"
    if (b := _BOOTH_TYPE.search(q)):
        params["booth_type"] = b.group(0).strip().lower()
    if re.search(r"\bmanual\b", q):
        params["painting_method"] = "manual"
    elif re.search(r"\bautomatic\b|\bautomated\b|\bauto\b", q):
        params["painting_method"] = "automatic"
    if (t := _THROUGHPUT.search(q)):
        params["throughput"] = f"{t.group(1)} per {t.group(2).lower()}"
    u.parameters = params

    # explicit "build me a spec" verbs, and question/conversion words
    spec_words = ("generate", "design", "build", "make", "create", "prepare",
                  "size up", "spec", "specification", "quotation", "quote")
    general_q = ("convert", "calculate", "what is", "what's", "how do", "how does",
                 "why", "explain")

    if "compare" in q or "difference" in q:
        u.intent = "comparison"
    elif any(w in q for w in ("price", "cost")) or "quotation" in q:
        u.intent = "quotation"
    elif any(w in q for w in general_q) and not any(w in q for w in spec_words):
        u.intent = "concept" if any(w in q for w in ("what", "how", "why", "explain")) else "general"
    elif any(w in q for w in ("show all", "list all", "larger than", "greater than")):
        u.intent = "search"
    elif params:
        u.intent = "specification"
    else:
        u.intent = "general"
    if u.intent in ("concept", "comparison", "general") and not u.topic:
        u.topic = question.strip()
    return u


# --- LLM understanding (JSON mode) -----------------------------------------

def _system() -> str:
    cats = ", ".join(known_categories())
    return (
        "You extract structured intent and entities from an engineer's request "
        "about industrial equipment. Respond with ONLY a JSON object with keys: "
        "intent (one of specification, comparison, concept, search, quotation, "
        "general — use 'general' for open/general questions or conversation that "
        "do not ask to build a company spec), "
        f"category (one of [{cats}] or null), "
        "parameters (object of the given-data values the user supplied — use "
        "EXACTLY these snake_case keys: air_volume_cfm, air_volume_cmh, "
        "tower_diameter_mm, operating_temp, operating_pressure, blower_mounting, "
        "qty, length_m, width_m, height_m, paint_type, booth_type, "
        "painting_method, throughput; numbers as numbers, omit "
        "unknowns), and topic (short "
        "string for concept/comparison questions, else null). Infer values from "
        "phrases like '800 cfm', '750 mm tower', '4 nos', '12 meters long'.\n"
        "Use 'specification' ONLY when the user explicitly asks to generate, "
        "design, build, size, or quote a piece of equipment. Unit conversions, "
        "definitions, explanations, and how/why/what questions are NOT "
        "specifications. Examples: 'generate a wet scrubber spec for 800 cfm' -> "
        "specification; 'convert 800 cfm to cmh' -> general; 'how does a scrubber "
        "work' -> concept; 'centrifugal vs axial fan' -> comparison."
    )


def _llm_understand(question: str) -> QueryUnderstanding | None:
    try:
        resp = httpx.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _system()},
                    {"role": "user", "content": question},
                ],
                "stream": False,
                "format": "json",
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"temperature": 0, "num_predict": config.UNDERSTAND_NUM_PREDICT},
            },
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["message"]["content"])
        params = data.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        # coerce numeric-looking strings
        for k, v in list(params.items()):
            if isinstance(v, str):
                nums = re.findall(r"[\d.]+", v)
                if nums:
                    params[k] = float(nums[0]) if "." in nums[0] else int(nums[0])
        cat = data.get("category")
        if cat not in known_categories():
            cat = None
        return QueryUnderstanding(
            intent=data.get("intent") or "specification",
            category=cat,
            parameters=params,
            topic=data.get("topic"),
            source="llm",
        )
    except Exception:
        return None


def understand(question: str) -> QueryUnderstanding:
    fb = _fallback(question)
    # Fast path: a clear spec request (known equipment category + numeric inputs)
    # is already fully parsed by regex, so skip the LLM call (~10s on CPU) — the
    # model adds nothing here and only slows the response.
    clear_spec = (fb.intent == "specification" and fb.category and fb.parameters)

    u = None
    if config.USE_LLM_UNDERSTANDING and not clear_spec:
        u = _llm_understand(question)
    if u is None:
        u = fb
    # Deterministic equipment classification is AUTHORITATIVE when confident —
    # never let the model treat a scrubber as a booth. Falls back to a weak
    # signal or the model's guess only when classification is uncertain.
    cat, score = classify_equipment(question)
    if score >= CONFIDENT:
        u.category = cat
    elif not u.category:
        u.category = cat or _detect_category(question.lower())
    params = _normalize_params(u.parameters)
    # regex backfill: fill any given-data fields the LLM missed (LLM values win)
    if u.source == "llm":
        for k, v in _normalize_params(fb.parameters).items():
            params.setdefault(k, v)
    _fill_air_volume_units(params)
    u.parameters = params
    return u


# 1 CFM = 1.699 m3/h (CMH). Keep both so the airflow driver is always present
# and units are never confused (1500 CMH must not be read as 1500 CFM).
_CFM_PER_CMH = 1.699


def _fill_air_volume_units(params: dict) -> None:
    cfm, cmh = params.get("air_volume_cfm"), params.get("air_volume_cmh")
    if isinstance(cfm, (int, float)) and not isinstance(cmh, (int, float)):
        params["air_volume_cmh"] = round(cfm * _CFM_PER_CMH)
    elif isinstance(cmh, (int, float)) and not isinstance(cfm, (int, float)):
        params["air_volume_cfm"] = round(cmh / _CFM_PER_CMH)
