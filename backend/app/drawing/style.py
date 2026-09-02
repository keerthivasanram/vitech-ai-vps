"""The drafting standard, in one place.

WHY THIS EXISTS. Line weights used to be chosen at the call site, from four
physical constants (`LW_THICK`, `LW_MED`, `LW_THIN`, `LW_HATCH`) applied 160
times across four modules. A caller therefore said HOW THICK a line should be
and never WHAT IT WAS, so the same 0.30 mm served a duct wall, a door leaf and a
panel seam — three different things in drafting terms — and nothing stopped the
next glyph from picking a fifth weight. Typography was worse: nine different
font sizes appeared inline as bare numbers with no names and no hierarchy.

So a line is now declared by its ROLE. `PRIMARY_OUTLINE` is the machine's
envelope wherever it is drawn; if the house standard for an envelope changes, it
changes here and every one of the fourteen equipment glyphs inherits it.

    canvas.add(Line(x1, y1, x2, y2, *PRIMARY_OUTLINE))
    canvas.add(Rect(x, y, w, h, *SECONDARY_OUTLINE))
    canvas.add(Circle(cx, cy, r, INTERNAL_DETAIL.layer, INTERNAL_DETAIL.width))

A `Pen` is ordered (layer, width, dash) to match the tail of `Line` and `Rect`,
which is what makes `*PEN` read cleanly. `Circle` takes no dash, so it names the
two fields it wants.

THE WEIGHT LADDER is ISO 128's ratio, not four arbitrary numbers. A reader tells
a cut edge from a component from a dimension by RELATIVE weight, so the ladder
is roughly 4 : 2 : 1.2 : 0.9 : 0.6. An earlier set ran 0.5 / 0.35 / 0.18, where
the top two are barely a pixel apart at sheet scale — every sheet came out
visually flat and the envelope never read as the envelope.

NOTHING HERE INVENTS ENGINEERING. This module decides how a line LOOKS. What is
drawn, and at what size, comes from the spec engine via `views.py`.
"""
from typing import NamedTuple, Optional

# --- layers -----------------------------------------------------------------
# The studio renders one <g> per layer and toggles its visibility, so which
# layer a line belongs to is part of the drafting standard, not an afterthought.
L_BORDER = "border"
L_OUTLINE = "outline"
L_COMPONENT = "component"
L_DIM = "dimension"
L_TEXT = "text"
L_TITLE = "title"
L_HIDDEN = "hidden"
L_CENTRE = "centre"

LAYER_ORDER = [L_BORDER, L_OUTLINE, L_HIDDEN, L_CENTRE, L_COMPONENT,
               L_DIM, L_TEXT, L_TITLE]
LAYER_LABELS = {
    L_BORDER: "Sheet border",
    L_OUTLINE: "Equipment outline",
    L_HIDDEN: "Hidden detail",
    L_CENTRE: "Centre lines",
    L_COMPONENT: "Components",
    L_DIM: "Dimensions",
    L_TEXT: "Notes & labels",
    L_TITLE: "Title block",
}

# --- dash patterns ----------------------------------------------------------
DASH_HIDDEN = "2,1.5"
DASH_CENTRE = "6,1.5,1.5,1.5"


class Pen(NamedTuple):
    """One drafting line role. Ordered to splat into `Line(...)`/`Rect(...)`."""
    layer: str
    width: float
    dash: Optional[str] = None


# --- the weight ladder ------------------------------------------------------
# Named so a glyph can reason about relative weight without hard-coding a value.
W_HEAVY = 0.60      # envelope, sheet border, cut edges
W_MEDIUM = 0.30     # panels, ducts, doors, filter banks, major internals
W_LIGHT = 0.18      # internal component detail, secondary geometry
W_FINE = 0.13       # dimensions, extension lines, leaders, centre lines
W_HAIR = 0.09       # hatching — always lighter than whatever it sits behind


# --- HEAVY: what the machine IS --------------------------------------------
BORDER = Pen(L_BORDER, W_HEAVY)
PRIMARY_OUTLINE = Pen(L_OUTLINE, W_HEAVY)
FLOOR_LINE = Pen(L_OUTLINE, W_HEAVY)

# --- MEDIUM: major components ----------------------------------------------
SECONDARY_OUTLINE = Pen(L_COMPONENT, W_MEDIUM)
PANEL_SEAM = Pen(L_COMPONENT, W_LIGHT)
DUCT = Pen(L_COMPONENT, W_MEDIUM)
DOOR = Pen(L_COMPONENT, W_MEDIUM)
EQUIPMENT = Pen(L_COMPONENT, W_MEDIUM)

# --- LIGHT: detail inside a component --------------------------------------
INTERNAL_DETAIL = Pen(L_COMPONENT, W_LIGHT)
SYMBOL_DETAIL = Pen(L_COMPONENT, W_LIGHT)

# --- FINE: the drawing ABOUT the drawing -----------------------------------
CENTRE_LINE = Pen(L_CENTRE, W_FINE, DASH_CENTRE)
HIDDEN_LINE = Pen(L_HIDDEN, W_LIGHT, DASH_HIDDEN)
DIMENSION_LINE = Pen(L_DIM, W_FINE)
EXTENSION_LINE = Pen(L_DIM, W_FINE)
LEADER_LINE = Pen(L_COMPONENT, W_FINE)
BALLOON = Pen(L_COMPONENT, W_FINE)
TABLE_RULE = Pen(L_TEXT, W_FINE)
TITLE_FRAME = Pen(L_TITLE, W_HEAVY)
TITLE_RULE = Pen(L_TITLE, W_MEDIUM)
TITLE_DIVIDER = Pen(L_TITLE, W_FINE)

# --- HAIR: material graphics ------------------------------------------------
HATCH_LINE = Pen(L_COMPONENT, W_HAIR)

# --- AIRFLOW: deliberately NOT a geometry weight ---------------------------
# Flow is not part of the machine, so it must not read as part of it. A long
# dash at a light weight separates it from every solid outline at a glance,
# which is what lets an arrow cross a view without being mistaken for a duct.
DASH_AIRFLOW = "4,1.6"
AIRFLOW_LINE = Pen(L_COMPONENT, W_LIGHT, DASH_AIRFLOW)


# --- typography -------------------------------------------------------------
# One scale, in sheet mm, replacing nine inline numbers. Sizes are drafting
# sizes: an engineering sheet is dense and readable, not a web page. The
# smallest is 1.9 mm because below that a schedule stops printing legibly at A3.
T_SHEET_TITLE = 4.2      # the sheet's own title, top-left
T_VIEW_TITLE = 3.0       # PLAN / FRONT ELEVATION / SIDE ELEVATION
T_SECTION = 2.9          # LEGEND / DESIGN DATA / ITEM LIST / NOTES
T_TITLE_MAIN = 3.6       # company name in the title block
T_BODY = 2.4             # table values, notes
T_SMALL = 2.3            # schedule rows, balloon digits
T_DIM = 2.2              # dimension text
T_TINY = 1.9             # title-block field captions, dense sub-labels
T_CAPTION = 2.1          # in-view captions (FLOOR LEVEL, CROSS DRAFT)

# Balloon geometry, so every glyph draws the same circle.
BALLOON_R = 3.2
LEADER_DOT_R = 0.5


# --- dimension hierarchy ----------------------------------------------------
# Parallel dimension lines are allocated to LANES at fixed offsets from the
# feature, so two dimensions on the same side of a view can never land on top
# of each other. The ladder is the drafting convention: the overall dimension
# sits closest to the object and each further level steps out.
#
#     OVERALL          -> lane 1, nearest the view
#     MAJOR SETTING    -> lane 2
#     COMPONENT        -> lane 3
#
# WHAT MAY OCCUPY A LANE IS AN ENGINEERING QUESTION, not a drafting one. Only a
# dimension the spec engine actually resolved may be drawn; component POSITIONS
# are indicative while Vitech supply no setting-out rules, so they get no
# dimension at all rather than a plausible-looking one.
DIM_LANE_OVERALL = 7.0
DIM_LANE_MAJOR = 15.0
DIM_LANE_COMPONENT = 23.0
