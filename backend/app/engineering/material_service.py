"""Material / filtration selection by process.

Which construction material and filtration a design uses is a materials-
engineering decision keyed on the process (paint chemistry, dust type, gas
composition). The client supplies the authoritative selection matrix; this is
the current ATS default for paint processes.
"""

# paint process -> {construction material, overspray filtration type}
PROCESS_RULES = {
    "powder":  {"material": "GI",    "filter_type": "dry"},
    "liquid":  {"material": "SS304", "filter_type": "water-wash"},
    "solvent": {"material": "SS304", "filter_type": "water-wash"},
    "water-based": {"material": "GI", "filter_type": "dry"},
}

_DEFAULT_PROCESS = "powder"


def select_paint_process(paint_type) -> dict:
    """Material + filtration for a paint process, defaulting to powder when the
    process is unknown/unspecified (the safe, most common ATS case)."""
    paint = (paint_type or _DEFAULT_PROCESS).lower()
    return PROCESS_RULES.get(paint, PROCESS_RULES[_DEFAULT_PROCESS])
