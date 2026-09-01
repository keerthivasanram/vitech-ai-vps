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


# --- Stock-section weights -------------------------------------------------
# Source: the client's own workbook `Cyclone recovery & Cartridge filter
# unit.xlsx` (delivered 2026-09-01), transcribed in
# docs/client-calculation-sheets.md §6. Vitech buys steel in standard lengths
# and sheets and costs it per piece, so a weight is a property of the STOCK
# ITEM, not something derived from a density and a volume.
#
# This is the missing rule behind the standing note that "MS structure is listed
# even though no rule computes its weight yet": a structure whose lengths are
# known can now be weighed, and therefore costed, from the client's own table.
#
# DQ-4, HALF RESOLVED by reading the workbooks themselves (2026-09-01). The
# square-tube "conflict" was not one: the booth sheet's tube is 40 x 40 x 3 at
# 21 kg and the cyclone sheet's is 40 x 40 x 2 at 18 kg — two different sections,
# both correct, and the earlier transcription simply lost the thickness. Both are
# on the table below, keyed by thickness so they can never be confused again.
#
# ONE ROW IS STILL WITHHELD. MS flat 40 x 6 x 6000 is 12 kg in the booth sheet
# and 16 kg in the cyclone sheet for the SAME nominal section — and 12 kg is what
# the steel weighs (40 x 6 mm x 6 m x 7850 = 11.3 kg), so the 16 cannot simply be
# adopted. Picking one would silently decide which of the client's own documents
# is right, and the error lands in a costed BOM. It stays in
# `STOCK_WEIGHT_DISPUTED` so the question is visible in code, and no caller can
# read it by accident.
STOCK_WEIGHT_STANDARD = "Vitech stock table (kg per standard length / sheet)"

STOCK_WEIGHTS_KG = {
    "ms_sheet_16swg_1250x2500x1.6": 40.0,
    "ms_sheet_14swg_1250x2500x2.0": 50.0,
    "ms_plate_1250x2500x6": 150.0,
    "ms_angle_65x65x6_6000": 36.0,
    "ms_angle_40x40x6_6000": 24.0,
    "ms_channel_75x40_6000": 44.0,
    "ms_square_tube_40x40x2_6000": 18.0,   # cyclone sheet
    "ms_square_tube_40x40x3_6000": 21.0,   # booth sheet — 3 mm wall, not a conflict
}

# Under query (DQ-4) — deliberately NOT part of STOCK_WEIGHTS_KG.
STOCK_WEIGHT_DISPUTED = {
    "ms_flat_40x6_6000": (16.0, 12.0),   # (cyclone sheet, booth sheet)
}

# The standard purchase length these section weights are quoted against.
STOCK_LENGTH_M = 6.0


def stock_weight_kg(item: str):
    """Weight of one standard length / sheet of `item`, or None.

    None means "not answerable from the client's data" — either the item is not
    on their table, or their two workbooks disagree about it (DQ-4). A caller
    must report that as an open item, never substitute a computed weight."""
    return STOCK_WEIGHTS_KG.get(item)


def stock_lengths_required(total_length_m: float) -> int:
    """Whole standard lengths needed to cover a run, per the sheets' own
    `ROUNDUP(metres / 6, 0)`. You buy the length, not the metre."""
    import math
    return max(1, int(math.ceil(float(total_length_m) / STOCK_LENGTH_M - 1e-9)))


def section_weight_kg(item: str, total_length_m: float):
    """Weight of the standard lengths needed to cover `total_length_m`, or None
    when the item's weight is unknown or under query."""
    per = stock_weight_kg(item)
    if per is None:
        return None
    return stock_lengths_required(total_length_m) * per
