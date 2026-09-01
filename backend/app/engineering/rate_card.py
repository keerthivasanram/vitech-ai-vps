"""Vitech's REAL rate card, from the client's costed bill of materials.

Source: client cost sheet "VITECH ENVIRO SYTEMS PVT LTD", Paint Spray Booth,
dated 24.07.2026 (received 2026-08-01). Until now the cost-plus pricing model
ran on the `SEED_*` industry defaults in `pricing_intelligence`, which CLAUDE.md
flags as the standing CLIENT ACTION: "the SEED_* rates are industry defaults —
replace with the real rate card". These are those numbers.

WHAT IS AND IS NOT VERIFIED
The rates below are read directly off the sheet and are internally consistent
across all five steel lines (material ₹/kg and labour ₹/kg both fall into two
clean bands by product form). They are trustworthy.

The sheet's own TOTAL is NOT reproducible from the lines visible in the supplied
image: the visible lines sum to ₹5,68,534 against a stated ₹6,49,264, a gap of
₹80,730, because the BOM's first row is cut off. So this module deliberately
does NOT claim to rebuild that total — `booth_bom_total()` is not offered.
Ask the client for the complete sheet to close the gap.
"""
from typing import NamedTuple, Optional

# --- Steel, ₹/kg -----------------------------------------------------------
# Two bands, exactly as the sheet prices them: flat product (sheet, plate) and
# rolled sections (square tube, channel, flat, mesh). Labour is a separate ₹/kg
# on the same weight — the sheet costs raw material and fabrication separately.
SHEET_MATERIAL_RATE = 85.0      # MS sheet & plate
SECTION_MATERIAL_RATE = 75.0    # MS square tube, channel, flat, wire mesh
SHEET_LABOUR_RATE = 45.0        # fabrication of flat product
SECTION_LABOUR_RATE = 50.0      # fabrication of sections

# --- Finishing -------------------------------------------------------------
PAINTING_RATE_PER_SQFT = 35.0   # booth painting, ₹/sq.ft (1134 sq.ft on the sheet)

# --- Rotating plant --------------------------------------------------------
# The sheet's motor is a 10 HP CG NFLP flange IE2 at ₹35,000, i.e. ₹3,500/HP —
# materially below the ₹4,500/HP industry seed it replaces.
MOTOR_RATE_PER_HP = 3500.0
# The matching blower (CLP-4" WC, 10 HP, 9000 CFM, direct drive) is ₹65,000.
# Priced per MACHINE, not per HP: a catalogue blower's price tracks its frame,
# and blower_service already picks the exact model.
BLOWER_PRICE_BY_MODEL = {
    "CLP-4-10-9000": 65000.0,
}

# --- Named bought-out items, ₹ per unit ------------------------------------
# Verbatim from the sheet. Each entry is (unit price, unit of issue, spec).
class BoughtOut(NamedTuple):
    price: float
    unit: str
    spec: str


BOUGHT_OUT_RATES: dict[str, BoughtOut] = {
    "led_light":            BoughtOut(9500.0, "no", "NFLP 90 W, ~800 lux"),
    "silicone_sealant":     BoughtOut(350.0, "no", "101-300 ml"),
    "bolt_m8x20":           BoughtOut(8.0, "no", "GI bolt, nut & 2 washers M8 x 20L"),
    "bolt_m8x25":           BoughtOut(10.0, "no", "GI bolt, nut & 2 washers M8 x 25L"),
    "bolt_m8x60":           BoughtOut(15.0, "no", "GI bolt, nut & 2 washers M8 x 60L"),
    "bolt_m10x50":          BoughtOut(20.0, "no", "GI bolt, nut & 2 washers M10 x 50L"),
    "rubber_gasket":        BoughtOut(2500.0, "no", "blower gasket"),
    "paint_arrest_filter":  BoughtOut(350.0, "sq.m", "paint arresting paper filter"),
    "air_inlet_filter":     BoughtOut(950.0, "no", "air inlet filter box 610 x 610 x 30"),
    "view_glass":           BoughtOut(3000.0, "no", "450 x 450 x 5 with rubber beading"),
    "top_track":            BoughtOut(3000.0, "no", "dia 20 MS rod & 75 x 6 MS flat, 6 m"),
    "top_roller":           BoughtOut(1000.0, "no", "door top roller"),
    "bottom_track":         BoughtOut(7500.0, "no", "standard 3 m length"),
    "bottom_wheel":         BoughtOut(1000.0, "no", "door bottom wheel"),
    "door_handle":          BoughtOut(900.0, "set", "door handle set"),
    "black_handle":         BoughtOut(250.0, "no", "120-P"),
    "sliding_door_kit":     BoughtOut(10000.0, "set", "manual sliding door, 2000 x 2350 double leaf"),
    "control_panel_10hp":   BoughtOut(95000.0, "lot", "10 HP blower ON/OFF + 4 LED, star-delta"),
    "field_wiring_10hp":    BoughtOut(115000.0, "lot", "field wiring for the above"),
    "gi_duct":              BoughtOut(3500.0, "sq.m", "GI exhaust duct 600 x 600"),
    "duct_support":         BoughtOut(150.0, "kg", "MS duct support"),
}


def steel_cost(weight_kg: float, form: str = "sheet") -> tuple[float, float]:
    """Material and labour cost for fabricated mild steel: `(material, labour)`.

    `form` is "sheet" for flat product (sheet/plate) or "section" for rolled
    sections — the sheet prices the two bands differently in both columns.
    """
    if form == "section":
        return weight_kg * SECTION_MATERIAL_RATE, weight_kg * SECTION_LABOUR_RATE
    return weight_kg * SHEET_MATERIAL_RATE, weight_kg * SHEET_LABOUR_RATE


def motor_cost(hp: float) -> float:
    """Motor cost at the client's own ₹/HP."""
    return float(hp) * MOTOR_RATE_PER_HP


def blower_cost(model: str) -> Optional[float]:
    """Catalogue price for a blower model, or None when the client has not
    priced that model yet — the caller must not extrapolate one."""
    return BLOWER_PRICE_BY_MODEL.get((model or "").strip().upper())


def bought_out_cost(item: str, qty: float = 1.0) -> Optional[float]:
    """Extended cost of a named bought-out item, or None if it is not on the
    client's rate card."""
    row = BOUGHT_OUT_RATES.get(item)
    return None if row is None else row.price * qty
