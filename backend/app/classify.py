"""Deterministic equipment classifier.

Decide the equipment DOMAIN before any generation, so the correct knowledge pack
and engineering rules are loaded. This is deliberately NOT left to the LLM — a
misclassification (a scrubber treated as a booth) is the worst kind of error, so
it is decided by scored keyword signals with a clear confidence.
"""
import re

# (regex, weight) — specific multi-word phrases score higher than bare words.
_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "wet_scrubber": [
        (r"wet\s*scrubber", 3), (r"\bscrubber\b", 2),
        (r"spray\s*tower|packed\s*tower|absorption\s*tower", 2),
        (r"demister|mist\s*eliminator", 2), (r"gas\s*cleaning|fume\s*scrubb", 1),
    ],
    "paint_booth": [
        (r"paint\s*booth", 3), (r"powder\s*coat\w*", 3), (r"spray\s*booth", 3),
        (r"coating\s*booth", 2), (r"painting\s*booth", 2), (r"\bbooth\b", 1),
    ],
    "hot_air_oven": [
        (r"hot\s*air\s*oven", 3),
        (r"curing\s*oven|baking\s*oven|batch\s*oven|conveyor\s*oven|paint\s*oven", 3),
        (r"\boven\b", 2), (r"\bcuring\b|\bbaking\b", 1),
    ],
    "dust_collector": [
        (r"dust\s*collector", 3), (r"bag\s*filter|pulse[\s-]*jet", 2),
        (r"cartridge\s*(dust\s*)?collector", 2), (r"\bcyclone\b", 1),
        (r"\bdust\b", 1),
    ],
    "powder_coating_plant": [
        (r"powder\s*coating\s*(plant|line)", 3), (r"powder\s*coating", 2),
    ],
    "fume_extraction": [
        (r"fume\s*extract\w*|fume\s*exhaust", 3), (r"welding\s*fume", 3),
        (r"\bfume\b", 1),
    ],
    "pretreatment_plant": [
        (r"pre[\s-]*treatment|\bpt\s*plant\b", 3), (r"phosphating|nano\s*coat", 3),
        (r"degreas\w*|dip\s*tank", 1),
    ],
    "blast_booth": [
        (r"blast\s*(booth|room)|grit\s*blast|shot\s*blast", 3),
        (r"abrasive\s*blast\w*", 3), (r"\bblasting\b", 1),
    ],
    "conveyor": [
        (r"overhead\s*conveyor|i[\s-]*beam\s*conveyor|power(ed)?\s*conveyor", 3),
        (r"push[\s-]*pull\s*conveyor|monorail", 2), (r"\bconveyor\b", 1),
    ],
}

CONFIDENT = 2   # a score >= this is a confident, authoritative classification


def classify_equipment(question: str) -> tuple[str | None, int]:
    """Return (category, score). score 0 = unknown; >= CONFIDENT = authoritative."""
    q = (question or "").lower()
    best, best_score = None, 0
    for cat, signals in _SIGNALS.items():
        score = sum(w for pat, w in signals if re.search(pat, q))
        if score > best_score:
            best, best_score = cat, score
    return best, best_score
