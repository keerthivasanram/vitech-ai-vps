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


_DIM_WORDS = {
    "length_m": r"length|long",
    "width_m": r"width|wide",
    "height_m": r"height|high|tall",
}
_UNIT = r"(mm|cm|m\b|met(?:er|re)s?)"

# TWO phrasings: value-first ("3.9 m long") and label-first ("Length: 0.9 m").
_LABELLED_DIM_SUFFIX = {
    key: re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}?\s*(?:{words})\b", re.I)
    for key, words in _DIM_WORDS.items()
}
_LABELLED_DIM_PREFIX = {
    key: re.compile(rf"\b(?:{words})\b\s*[:=-]?\s*(\d+(?:\.\d+)?)\s*{_UNIT}?", re.I)
    for key, words in _DIM_WORDS.items()
}

# Which phrasing the text uses has to be decided ONCE for the whole string,
# because each pattern happily mis-reads the other's layout:
#   label-first patterns on "3.9 m long 4 m wide 8.3 m high" find "long", scan
#   forward and take the NEXT dimension's number -> length 4.0, width 8.3, no
#   height, silently wrong;
#   value-first patterns on "length 900mm width 920mm" match "900mm width" and
#   read length's value as the width.
# Whichever layout appears FIRST in the string is the one the writer is using.
_ANY_DIM_WORD = "|".join(_DIM_WORDS.values())
_VALUE_FIRST = re.compile(rf"(\d+(?:\.\d+)?)\s*{_UNIT}?\s*(?:{_ANY_DIM_WORD})\b", re.I)
_LABEL_FIRST = re.compile(rf"\b(?:{_ANY_DIM_WORD})\b\s*[:=-]?\s*\d", re.I)


def _labelled_dims(q: str, min_labels: int = 2) -> dict:
    """Dimensions written as labels rather than a product: "Length: 0.9 meters,
    Width: 0.92 m, Height: 2" or "0.9 m long, 0.92 m wide, 2 m high". Returns
    metres. Only accepted when at least TWO labels are present, so a stray
    "height 3" in prose cannot masquerade as a dimensioned requirement.

    `min_labels=1` is used ONLY for the text after a correction phrase, where a
    single dimension is the whole point ("make it 8 m long") and the surrounding
    prose that the two-label guard protects against is not present.
    """
    vf, lf = _VALUE_FIRST.search(q), _LABEL_FIRST.search(q)
    value_first = bool(vf) and (not lf or vf.start() < lf.start())
    primary = _LABELLED_DIM_SUFFIX if value_first else _LABELLED_DIM_PREFIX
    fallback = _LABELLED_DIM_PREFIX if value_first else _LABELLED_DIM_SUFFIX

    out: dict = {}
    for key in _DIM_WORDS:
        m = primary[key].search(q) or fallback[key].search(q)
        if not m:
            continue
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit.startswith("mm"):
            val /= 1000.0
        elif unit.startswith("cm"):
            val /= 100.0
        out[key] = val
    return out if len(out) >= min_labels else {}


def _fallback(question: str) -> QueryUnderstanding:
    q = question.lower()
    u = QueryUnderstanding(source="regex")
    u.category = _detect_category(q)
    params: dict = {}

    job_ctx = bool(_JOB_SIZE_CTX.search(q)) and u.category in _BOOTH_LIKE

    # LABELLED dimensions ("Length: 0.9 meters, Width: 0.92 m, Height: 2") — the
    # form people paste from a data sheet or a mail. Checked BEFORE the "A x B x C"
    # patterns because the two never co-occur, and this parser is deterministic:
    # `_exact_dimension_hit` relies on it (not on the LLM), so a shape it cannot
    # read makes a dimension lookup answer "no match" and then fall through to a
    # relevance search that returns unrelated projects.
    labelled = _labelled_dims(q)
    if labelled:
        params.update(labelled)
    elif (m := _DIM_TRIPLE.search(q)):
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


# The three overall-size axes, resolved together or not at all: a triple is only
# trustworthy as a set, because its meaning is positional.
_DIM_AXES = ("length_m", "width_m", "height_m")


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
        fb_params = _normalize_params(fb.parameters)
        for k, v in fb_params.items():
            params.setdefault(k, v)
        # ...EXCEPT the dimension triple, where the REGEX is authoritative when
        # it read a complete one. Axis assignment is precisely what the model
        # gets wrong: asked for "overhead conveyor 60 m track 3m x 1m x 4m" it
        # returned 60 x 3 x 1 — it took the TRACK LENGTH as the length, shifted
        # the stated triple along, and silently dropped the 4 m height. The
        # regex reads "A x B x C" positionally from what the customer actually
        # wrote, so on a complete triple it cannot be improved on, and a wrong
        # envelope draws a wrong GA (golden rule #2).
        if all(k in fb_params for k in _DIM_AXES):
            for k in _DIM_AXES:
                params[k] = fb_params[k]
    # A stated correction wins over the value it corrects — applied BEFORE the
    # unit fill so a corrected airflow recomputes its partner unit.
    _apply_correction(question, params)
    _fill_air_volume_units(params)
    u.parameters = params
    return u


# --- corrections -----------------------------------------------------------
# "change it to", "now", "make it" ... — everything AFTER one of these phrases
# supersedes the same parameter stated before it.
_CORRECTION_RE = re.compile(
    r"\b(?:changed?\s+(?:it\s+|them\s+|the\s+\w+\s+)?to|changed?\s+to|"
    r"revised?\s+to|updated?\s+to|correct(?:ed|ion)?\s+to|"
    r"increase[d]?\s+(?:it\s+)?to|reduce[d]?\s+(?:it\s+)?to|"
    r"make\s+it|should\s+be|set\s+(?:it\s+)?to|now)\b", re.I)

# Correcting one unit of a paired quantity must invalidate the other, or the
# spec would carry the NEW cfm beside the OLD m3/h and quietly disagree with
# itself. The dropped partner is recomputed by `_fill_air_volume_units`.
_UNIT_PARTNERS = {"air_volume_cfm": "air_volume_cmh",
                  "air_volume_cmh": "air_volume_cfm"}


# "change the height to 6 m" / "make the length 8m" / "set the airflow to 9000 cmh"
# — here the FIELD NAME sits inside the correction phrase and only a bare number
# follows it, so re-reading the tail alone finds a value with nothing to attach
# it to. This pattern keeps the two together.
_FIELD_CORRECTION_RE = re.compile(
    r"\b(?:chang(?:e|ed)|revis(?:e|ed)|updat(?:e|ed)|set|increase[d]?|reduce[d]?|make)\s+"
    r"(?:it\s+|the\s+)?(length|width|height|depth|dia|diameter|airflow|air\s*volume)\s*"
    r"(?:to|=|:|of)?\s*([\d.]+)\s*(mm|cm|m|cfm|cmh|m3/h)?\b", re.I)

_DIM_FIELD_KEYS = {"length": "length_m", "width": "width_m",
                   "height": "height_m", "depth": "width_m"}


def _field_corrections(text: str) -> dict:
    """Corrections that NAME the field they change, e.g. "change the height to 6m"."""
    out: dict = {}
    for m in _FIELD_CORRECTION_RE.finditer(text):
        field = re.sub(r"\s+", "", m.group(1).lower())
        value = float(m.group(2))
        unit = (m.group(3) or "").lower()
        if field in _DIM_FIELD_KEYS:
            metres = value / 1000.0 if unit == "mm" else value / 100.0 if unit == "cm" else value
            out[_DIM_FIELD_KEYS[field]] = metres
        elif field in ("dia", "diameter"):
            # A tower diameter is quoted in mm in every Vitech record; only an
            # explicit m/cm changes that.
            out["tower_diameter_mm"] = (value * 1000.0 if unit == "m"
                                        else value * 10.0 if unit == "cm" else value)
        else:                                   # airflow / air volume
            key = "air_volume_cmh" if unit in ("cmh", "m3/h") else "air_volume_cfm"
            out[key] = value
    return out


def _apply_correction(question: str, params: dict) -> None:
    """Let a stated correction override the value it corrects.

    Corrections arrive as ONE restated requirement, because the agent folds the
    follow-up into the original before calling a tool — "paint booth 5m x 3m x
    4m changed to 6m x 3m x 4m". Every extractor here uses `.search()`, which
    takes the FIRST match, so the correction was silently discarded and the
    drawing came back unchanged: the user saw their correction ignored.

    Fixed deterministically rather than by prompting, because a prompt cannot
    make an 8B model reliably rewrite a requirement, and the same phrasing must
    always give the same drawing. Only text following a correction phrase is
    re-read, so an ordinary requirement is parsed exactly as before.
    """
    named = _field_corrections(question)
    matches = list(_CORRECTION_RE.finditer(question))
    if not matches and not named:
        return

    if matches:
        # The ORIGINAL requirement is re-read on its own. Parsing the whole
        # sentence lets the correction's wording win the parser's own
        # either/or choices — "5m x 3m x 4m ... now 7m long 4m wide" matched the
        # labelled-dimension branch on the tail and never reached the triple, so
        # the height silently vanished from the requirement altogether.
        head = question[:matches[0].start()].strip(" ,.:;-")
        if head:
            for key, value in _normalize_params(_fallback(head).parameters).items():
                params.setdefault(key, value)

    tail = question[matches[-1].end():].strip(" ,.:;-") if matches else ""
    corrected = _normalize_params(_fallback(tail).parameters) if tail else {}
    if tail:
        # "make it 8 m long" names ONE dimension, which the general parser
        # rejects on purpose. After a correction phrase that guard is inverted:
        # a single dimension is exactly what a correction usually is.
        for key, value in _labelled_dims(tail.lower(), min_labels=1).items():
            corrected.setdefault(key, value)
    # A field-named correction is the most explicit form there is, so it wins.
    corrected.update(named)
    for key, value in corrected.items():
        params[key] = value
        partner = _UNIT_PARTNERS.get(key)
        if partner and partner not in corrected:
            params.pop(partner, None)


# 1 CFM = 1.699 m3/h (CMH). Keep both so the airflow driver is always present
# and units are never confused (1500 CMH must not be read as 1500 CFM).
_CFM_PER_CMH = 1.699


def _fill_air_volume_units(params: dict) -> None:
    cfm, cmh = params.get("air_volume_cfm"), params.get("air_volume_cmh")
    if isinstance(cfm, (int, float)) and not isinstance(cmh, (int, float)):
        params["air_volume_cmh"] = round(cfm * _CFM_PER_CMH)
    elif isinstance(cmh, (int, float)) and not isinstance(cfm, (int, float)):
        params["air_volume_cfm"] = round(cmh / _CFM_PER_CMH)
