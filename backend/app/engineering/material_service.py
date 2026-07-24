"""Material / filtration selection by process + booth design.

Which construction material and filtration a design uses is a materials-
engineering decision. For a paint booth it is keyed on BOTH the paint chemistry
AND the booth design: filtration type is not a pure function of the paint.

Vitech builds DRY-filter booths (paper filter + MS construction) as the standard
for liquid/solvent paint — 13 of the 14 historical paint-booth offers are dry.
Only an explicitly water-wash / water-wall booth (e.g. OFF-YONEX-PB-367) uses a
water curtain with SS304 wetted parts. So for a liquid-family process the choice
is driven by the booth type and defaults to dry; otherwise the computed
filtration/material would contradict the reused historical (dry) booth.

The client supplies the authoritative selection matrix; this is the current ATS
default, calibrated against the real offers.
"""

# Process-fixed rules (filtration is inherent to the chemistry here).
PROCESS_RULES = {
    "powder":      {"material": "GI", "filter_type": "dry"},
    "water-based": {"material": "GI", "filter_type": "dry"},
}

# Liquid-family processes: Vitech builds these dry-filter / MS by default, and
# water-wash / SS304 only when the booth is explicitly a water-wash type.
_LIQUID_PROCESSES = {"liquid", "solvent", "pu", "enamel", "epoxy"}
_LIQUID_DRY = {"material": "MS", "filter_type": "dry"}
_WATER_WASH = {"material": "SS304", "filter_type": "water-wash"}

# Booth-type phrases that mark a water-wash / water-curtain design. "wet " covers
# the parsed "wet cross/side/down draft"; the rest cover water-wall wording.
_WATER_WASH_MARKERS = (
    "water wall", "water-wall", "water wash", "water-wash",
    "water curtain", "wet ",
)

_DEFAULT_PROCESS = "powder"


def _is_water_wash(booth_type) -> bool:
    b = (booth_type or "").lower()
    return any(m in b for m in _WATER_WASH_MARKERS)


def select_paint_process(paint_type, booth_type=None) -> dict:
    """Construction material + overspray filtration for a paint booth.

    For a liquid-family process the filtration is a booth-design choice: dry
    (Vitech's default, matching the historical offers) unless the booth is
    explicitly a water-wash / water-wall type. Powder / water-based keep their
    process-fixed rule. Defaults to powder when the process is unknown."""
    paint = (paint_type or _DEFAULT_PROCESS).lower()
    if paint in _LIQUID_PROCESSES:
        return dict(_WATER_WASH if _is_water_wash(booth_type) else _LIQUID_DRY)
    return dict(PROCESS_RULES.get(paint, PROCESS_RULES[_DEFAULT_PROCESS]))
