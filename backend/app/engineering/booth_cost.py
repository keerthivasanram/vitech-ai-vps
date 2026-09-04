"""Works cost of a paint booth, built the way Vitech build it.

WHY THIS EXISTS AND WHY IT COULD NOT BE WRITTEN BEFORE. The pricing model has
always carried a cost-plus estimate, but it could never be CHECKED: the client's
costed booth sheet arrived with its first row cropped, so the visible lines came
to Rs 5,68,534 against a stated Rs 6,49,264 and Rs 80,730 was unexplained. That
row was recovered - MS 18 SWG sheet, 621 kg, RM 52,785 + labour 27,945 = 80,730 -
and the total now reconciles exactly. This module is what that recovery unlocked:
a cost build-up that can be validated against Vitech's own figure rather than
merely looking plausible.

WHAT IS COMPUTED AND WHAT IS QUOTED. Every quantity here comes from the client's
own formulas (panel module, structure lengths, painting area) and every rate from
their own rate card. Nothing is scaled, interpolated or averaged. Three lines
reproduce their worked booth to the rupee:

    MS sheet   621 kg  x Rs 130/kg          = Rs 80,730
    Structure  446 kg  (126 + 308 + 12)
    Painting   1134 sq.ft x Rs 35/sq.ft     = Rs 39,690

THE HONEST-GAP CONTRACT APPLIES TO MONEY TOO, and matters more here than
anywhere else. A line is priced only where the client's own rate card reaches
it; everything else is listed with the cost left OPEN and a reason. The total
therefore declares itself PARTIAL. That is deliberate: a confident grand total
assembled over gaps is the most dangerous number this platform could print,
because it looks exactly like a quotation. The uncosted list is itself the
answer to "what else do we need from Vitech".

NOT A QUOTATION. This is works cost - what the machine costs to build. Margin,
discount and the fixed adders are a separate commercial decision (the `Combine`
sheet's x1.40 / x1.26 per-line multipliers), and selecting the multiplier is
still open with the client as DQ-7.
"""
from typing import NamedTuple, Optional

from . import rate_card as rc
from .calculation_engine import count_ceil
from .paint_shop_service import PANEL_SHEET_KG, booth_panel_count

# --- structure, from the client's own length formulas (sheet 5b) -----------
# Stock is issued in 6 m lengths, so metres are rounded UP to whole lengths
# before weighing - that is how the sheet costs it, and it is why a booth 100 mm
# longer can cost a whole extra length of channel.
STOCK_LENGTH_M = 6.0
SQ_TUBE_KG_PER_LENGTH = 21.0      # 40 x 40 x 3
CHANNEL_KG_PER_LENGTH = 44.0
FLAT_KG_PER_LENGTH = 12.0         # 40 x 6
FLAT_METRES = 6.0                 # fixed on the sheet, not derived

# Fabricated flat product that is NOT enclosure panelling.
BLOWER_MOUNTING_PLATE_KG = 150.0
FILTER_FRAME_KG_EACH = 50.0       # 14 swg
FILTER_FRAME_NOS = 2

# Painting (sheet 5c). 3.25 m2 per panel, 10.76 sq.ft per m2.
PANEL_PAINT_M2 = 3.25
SQFT_PER_M2 = 10.76
# A structural length presents four faces of a nominal 0.25 m girth.
STRUCTURE_PAINT_GIRTH_M = 0.25
STRUCTURE_PAINT_FACES = 4


class Line(NamedTuple):
    """One cost line. `cost` is None when the rate card does not reach it."""
    item: str
    detail: str
    quantity: str
    cost: Optional[float]
    basis: str


def structure_weight(length_m: float, width_m: float, height_m: float) -> dict:
    """Structural steel from the client's length formulas.

    Reproduces their worked booth exactly: 36 m of square tube -> 6 lengths ->
    126 kg, 40 m of channel -> 7 lengths -> 308 kg, 6 m of flat -> 12 kg.
    """
    out_l = length_m + 0.10
    out_w = width_m + 0.75
    out_h = height_m + 0.15

    sq_m = count_ceil(out_l * 3 + out_w * 2 + 1.0 * 4 + 1.5 * 4 + 2.45 * 4)
    ch_m = count_ceil(out_l * 3 + out_w * 2 + out_h * 8 + 1.0 * 4)
    fl_m = FLAT_METRES

    sq_nos = count_ceil(sq_m / STOCK_LENGTH_M)
    ch_nos = count_ceil(ch_m / STOCK_LENGTH_M)
    fl_nos = count_ceil(fl_m / STOCK_LENGTH_M)

    return {
        "square_tube": {"metres": sq_m, "lengths": sq_nos,
                        "kg": sq_nos * SQ_TUBE_KG_PER_LENGTH},
        "channel": {"metres": ch_m, "lengths": ch_nos,
                    "kg": ch_nos * CHANNEL_KG_PER_LENGTH},
        "flat": {"metres": fl_m, "lengths": fl_nos,
                 "kg": fl_nos * FLAT_KG_PER_LENGTH},
        "total_kg": (sq_nos * SQ_TUBE_KG_PER_LENGTH + ch_nos * CHANNEL_KG_PER_LENGTH
                     + fl_nos * FLAT_KG_PER_LENGTH),
        "total_lengths": sq_nos + ch_nos + fl_nos,
    }


def painting_area_sqft(panel_nos: int, structure_lengths: int) -> dict:
    """Painted area, panels and structure separately (sheet 5c).

    NOTE the filter-frame count differs from the one in the PANEL count, and
    that is not a transcription slip: the panel schedule counts four frame
    PIECES (top and bottom of each frame), the painting schedule counts the two
    FRAMES. Using four here gives 1,204 sq.ft against the sheet's 1,134 - which
    is how the distinction was found.
    """
    plate_nos = 1                                   # blower mounting plate
    panel_paint = count_ceil((plate_nos + panel_nos + FILTER_FRAME_NOS)
                             * PANEL_PAINT_M2 * SQFT_PER_M2)
    structure_paint = (structure_lengths * STOCK_LENGTH_M
                       * STRUCTURE_PAINT_GIRTH_M * STRUCTURE_PAINT_FACES)
    return {"panel_sqft": panel_paint,
            "structure_sqft": structure_paint,
            "total_sqft": panel_paint + structure_paint}


def works_cost(length_m: float, width_m: float, height_m: float, *,
               blower_model: str = "", motor_hp: float = 0.0,
               filter_area_m2: float = 0.0, light_nos: int = 0) -> dict:
    """The booth's works cost as a list of lines, priced where the rate card reaches.

    Returns `lines`, the `priced_total`, and `open_items` - the lines the client
    has given no rate for. The total is explicitly PARTIAL; see the module note.
    """
    panels = booth_panel_count(length_m, width_m, height_m)
    panel_nos = panels["panels"]
    panel_kg = panel_nos * PANEL_SHEET_KG
    structure = structure_weight(length_m, width_m, height_m)
    paint = painting_area_sqft(panel_nos, structure["total_lengths"])

    lines: list[Line] = []

    # --- fabricated steel ---------------------------------------------------
    mat, lab = rc.steel_cost(panel_kg, "sheet")
    lines.append(Line(
        "Enclosure panels", f"{panel_nos} panels x {PANEL_SHEET_KG:g} kg",
        f"{panel_kg:g} kg", mat + lab,
        f"MS sheet Rs {rc.SHEET_MATERIAL_RATE:g}/kg + Rs {rc.SHEET_LABOUR_RATE:g}/kg fabrication"))

    plate_kg = BLOWER_MOUNTING_PLATE_KG + FILTER_FRAME_KG_EACH * FILTER_FRAME_NOS
    mat, lab = rc.steel_cost(plate_kg, "sheet")
    lines.append(Line(
        "Blower plate and filter frames",
        f"plate {BLOWER_MOUNTING_PLATE_KG:g} kg + {FILTER_FRAME_NOS} frames "
        f"x {FILTER_FRAME_KG_EACH:g} kg",
        f"{plate_kg:g} kg", mat + lab, "MS sheet rate"))

    mat, lab = rc.steel_cost(structure["total_kg"], "section")
    lines.append(Line(
        "MS structure",
        f"square tube {structure['square_tube']['kg']:g} kg, "
        f"channel {structure['channel']['kg']:g} kg, "
        f"flat {structure['flat']['kg']:g} kg",
        f"{structure['total_kg']:g} kg", mat + lab,
        f"MS section Rs {rc.SECTION_MATERIAL_RATE:g}/kg + "
        f"Rs {rc.SECTION_LABOUR_RATE:g}/kg fabrication"))

    lines.append(Line(
        "Painting", f"panels {paint['panel_sqft']:g} + structure {paint['structure_sqft']:g} sq.ft",
        f"{paint['total_sqft']:g} sq.ft",
        paint["total_sqft"] * rc.PAINTING_RATE_PER_SQFT,
        f"Rs {rc.PAINTING_RATE_PER_SQFT:g}/sq.ft"))

    # --- bought-out items ---------------------------------------------------
    # Priced ONLY at the client's own unit prices. A model they have not priced
    # is listed and left open rather than scaled from one they have: the sheet
    # prices exactly one blower, and inventing the rest is how a quotation goes
    # wrong quietly.
    if blower_model:
        price = rc.blower_cost(blower_model)
        lines.append(Line(
            "Exhaust blower", blower_model, "1 no", price,
            "client unit price" if price is not None
            else "NOT PRICED - the client's sheet prices only CLP-4-10-9000"))
    if motor_hp:
        lines.append(Line(
            "Blower motor", f"{motor_hp:g} HP", "1 no", rc.motor_cost(motor_hp),
            f"Rs {rc.MOTOR_RATE_PER_HP:g}/HP"))

    for key, qty, label in (("control_panel_10hp", 1, "Control panel"),
                            ("field_wiring_10hp", 1, "Field wiring"),
                            ("sliding_door_kit", 1, "Manual sliding door"),
                            ("view_glass", 1, "View glass panel"),
                            ("air_inlet_filter", 1, "Air inlet filter box"),
                            ("rubber_gasket", 1, "Blower gasket")):
        item = rc.BOUGHT_OUT_RATES.get(key)
        if item:
            lines.append(Line(label, item.spec, f"{qty} {item.unit}",
                              item.price * qty, "client unit price"))

    if filter_area_m2:
        f = rc.BOUGHT_OUT_RATES["paint_arrest_filter"]
        lines.append(Line("Paint arresting filters", f.spec,
                          f"{filter_area_m2:g} sq.m", f.price * filter_area_m2,
                          "client unit price"))
    if light_nos:
        f = rc.BOUGHT_OUT_RATES["led_light"]
        lines.append(Line(
            "Light fittings", f.spec, f"{light_nos} nos", f.price * light_nos,
            "client unit price - NOTE their rate is for a 90 W fitting; the "
            "specification's 40 W fitting is not separately priced"))

    # --- what the client has NOT priced -------------------------------------
    # Named explicitly. These are the gaps that stop this being a quotation, and
    # naming them is more useful than a total that hides them.
    open_items = [
        "Activated carbon chamber - no rate supplied",
        "Dry scrubber - specification itself is To Be Determined",
        "Fire detection and suppression - no rate supplied",
        "Ducting beyond the booth - priced separately on the client's own sheet",
        "Erection and commissioning - a fixed adder on the client's Combine sheet",
        "Freight and insurance - customer scope on the client's sheet",
    ]

    priced = [ln for ln in lines if ln.cost is not None]
    unpriced = [ln for ln in lines if ln.cost is None]
    total = sum(ln.cost or 0.0 for ln in priced)

    return {
        "lines": [ln._asdict() for ln in lines],
        "priced_total": round(total, 2),
        "priced_line_count": len(priced),
        "unpriced_lines": [ln.item for ln in unpriced],
        "open_items": open_items,
        "quantities": {
            "panels": panel_nos,
            "panel_weight_kg": panel_kg,
            "structure_kg": structure["total_kg"],
            "plate_and_frames_kg": plate_kg,
            "steel_total_kg": panel_kg + plate_kg + structure["total_kg"],
            "painting_sqft": paint["total_sqft"],
        },
        "structure": structure,
        "painting": paint,
        # Stated, never implied: this is not a quotation and not a complete cost.
        "is_partial": True,
        "basis": ("Works cost only, from the client's own formulas and rate card. "
                  "Margin, discount and the fixed adders are a separate commercial "
                  "decision and are NOT included."),
    }
