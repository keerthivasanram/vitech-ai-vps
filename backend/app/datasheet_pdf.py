"""Generate Vitech enquiry DATA SHEETS as PDFs (fpdf2, no system deps).

These reproduce the client's own requirement-capture forms — "DATA SHEET FOR
PAINTING PLANT", "... POWDER COATING PLANT", "... DUST COLLECTION EQUIPMENT" —
on the official letterhead, so the sales engineer can hand a customer the same
document the company already uses.

The forms are declared as data (`FORMS`) and rendered by a single generic
walker, so adding an equipment type is a schema entry, not new drawing code.

A form can be emitted blank (the normal enquiry hand-out) or PREFILLED from a
requirement: `prefill` maps a field/choice label to a value. Prefilled values
are printed verbatim and ticked options are marked — nothing is inferred or
invented here, the caller supplies only what it actually knows (golden rule #2).
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from . import vitech_letterhead as lh

TEXT = (15, 23, 42)
GREY = lh.GREY
LINE = (150, 158, 170)
HILITE = (255, 242, 158)      # the highlighter used on the client's filled sheets

_lat = lh.lat

LABEL_W = 62.0
BOX = 3.6


class _DSPDF(FPDF):
    def header(self):
        lh.draw_header(self)
        lh.draw_side_banner(self)

    def footer(self):
        lh.draw_footer(self)


# --------------------------------------------------------------------------
# element renderers
# --------------------------------------------------------------------------
def _title(pdf, text):
    pdf.set_font("Helvetica", "BU", 12.5)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 9, _lat(text.upper()), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)


def _section(pdf, text):
    lh.ensure_space(pdf, 16)
    pdf.ln(2.5)
    pdf.set_font("Helvetica", "BU", 10)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 6, _lat(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _note(pdf, text, bold=False):
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "B" if bold else "", 8.8)
    pdf.set_text_color(*TEXT if bold else GREY)
    rh = lh.measure_h(pdf, usable, text, 8.8, style="B" if bold else "", line_h=4.6)
    lh.ensure_space(pdf, rh + 2)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(usable, 4.6, _lat(text))
    pdf.ln(0.8)


def _field(pdf, label, value=""):
    """"Label  : value" with a dotted fill-in rule when there is no value."""
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    vw = usable - LABEL_W - 4
    rh = max(lh.measure_h(pdf, LABEL_W, label, 9, line_h=5.0),
             lh.measure_h(pdf, vw, value or " ", 9, line_h=5.0))
    lh.ensure_space(pdf, rh + 1.5)
    x, y0 = pdf.l_margin, pdf.get_y()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*TEXT)
    pdf.set_xy(x, y0)
    pdf.multi_cell(LABEL_W, 5.0, _lat(label))
    y1 = pdf.get_y()

    pdf.set_xy(x + LABEL_W, y0)
    pdf.cell(4, 5.0, ":", new_x=XPos.RIGHT, new_y=YPos.TOP)

    if value:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*TEXT)
        pdf.set_xy(x + LABEL_W + 4, y0)
        pdf.multi_cell(vw, 5.0, _lat(value))
        y2 = pdf.get_y()
    else:                                   # blank rule to write on
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.15)
        pdf.line(x + LABEL_W + 5, y0 + 4.4, x + usable, y0 + 4.4)
        y2 = y0 + 5.0
    pdf.set_xy(pdf.l_margin, max(y1, y2) + 1.2)


def _tickbox(pdf, x, y, ticked):
    pdf.set_draw_color(*TEXT)
    pdf.set_line_width(0.25)
    pdf.rect(x, y, BOX, BOX, style="D")
    if ticked:                              # vector check mark
        pdf.set_line_width(0.45)
        pdf.line(x + 0.7, y + BOX * 0.55, x + BOX * 0.42, y + BOX - 0.7)
        pdf.line(x + BOX * 0.42, y + BOX - 0.7, x + BOX - 0.5, y + 0.6)
        pdf.set_line_width(0.25)


def _choice(pdf, label, options, chosen=None):
    """"Label : optA [ ]  optB [x]" — wraps onto further lines when needed."""
    chosen = {str(c).strip().lower() for c in (chosen or [])}
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    x0 = pdf.l_margin
    vx = x0 + LABEL_W + 4
    right = x0 + usable

    lh.ensure_space(pdf, 12)
    y0 = pdf.get_y()
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*TEXT)
    pdf.set_xy(x0, y0)
    pdf.multi_cell(LABEL_W, 5.0, _lat(label))
    y_label_end = pdf.get_y()

    pdf.set_xy(x0 + LABEL_W, y0)
    pdf.cell(4, 5.0, ":", new_x=XPos.RIGHT, new_y=YPos.TOP)

    x, y = vx, y0
    for opt in options:
        ticked = str(opt).strip().lower() in chosen
        pdf.set_font("Helvetica", "B" if ticked else "", 8.8)
        tw = pdf.get_string_width(_lat(opt))
        need = tw + 2 + BOX + 6
        if x + need > right and x > vx:     # wrap to the next option line
            x = vx
            y += 5.6
            lh.ensure_space(pdf, 8)
        if ticked:                          # highlighter, as on the filled sheets
            pdf.set_fill_color(*HILITE)
            pdf.rect(x - 0.8, y + 0.3, tw + 1.6, 4.6, style="F")
        pdf.set_text_color(*TEXT)
        pdf.set_xy(x, y)
        pdf.cell(tw + 1, 5.0, _lat(opt), new_x=XPos.RIGHT, new_y=YPos.TOP)
        _tickbox(pdf, x + tw + 2, y + 0.7, ticked)
        x += need
    pdf.set_xy(x0, max(y_label_end, y + 5.0) + 1.2)


def _table(pdf, headers, widths, n_rows, row_h=6.0):
    """Bordered grid: header row then `n_rows` blank rows to fill in."""
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    scale = usable / sum(widths)
    w = [x * scale for x in widths]

    hh = max(lh.measure_h(pdf, wi - 2, h, 7.5, style="", line_h=3.8)
             for wi, h in zip(w, headers)) + 1.5
    lh.ensure_space(pdf, hh + row_h * 2)

    x0, y = pdf.l_margin, pdf.get_y()
    pdf.set_draw_color(*TEXT)
    pdf.set_line_width(0.25)
    x = x0
    for wi, h in zip(w, headers):
        pdf.rect(x, y, wi, hh, style="D")
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*TEXT)
        pdf.set_xy(x + 1, y + 0.8)
        pdf.multi_cell(wi - 2, 3.8, _lat(h), align="C")
        x += wi
    y += hh

    for r in range(n_rows):
        lh.ensure_space(pdf, row_h + 1)
        if pdf.get_y() > y:                 # a page break happened
            y = pdf.get_y()
        x = x0
        for i, wi in enumerate(w):
            pdf.rect(x, y, wi, row_h, style="D")
            if i == 0:
                pdf.set_font("Helvetica", "", 7.5)
                pdf.set_text_color(*TEXT)
                pdf.set_xy(x + 1, y + 1.2)
                pdf.cell(wi - 2, 3.6, str(r + 1))
            x += wi
        y += row_h
        pdf.set_xy(x0, y)
    pdf.set_xy(x0, y + 1.5)


# --------------------------------------------------------------------------
# form definitions — mirror the client's printed data sheets
# --------------------------------------------------------------------------
_MATRIX_HEADERS = ["SL.\nNo", "Component\nName", "Weight\nIn KGS",
                   "Size (L x W x H)\nIn mm", "Qty /shift\nIn Nos./8Hrs",
                   "% of\nProduction"]
_MATRIX_WIDTHS = [8, 34, 18, 30, 20, 18]

_PLANT_HANDLING = [
    ("choice", "Type of plant", ["Batch", "Conveyorized"]),
    ("choice", "Material Handling", ["Hoist", "Conveyor", "Trolley"]),
    ("sub", "(How will the job be handled?)"),
    ("choice", "If Conveyor", ["Floor", "Overhead"]),
    ("choice", "If Trolley", ["Manual", "Auto (Gear Drive)"]),
]

_PLANT_SECTION = [
    ("field", "Floor space available (L x W, in metres)"),
    ("field", "Headroom available (H, in metres)"),
    ("field", "Power available (in HP)"),
    ("field", "Any Specific Requirement"),
]

_CONTACT_SAM = ("Mr. D.SAM MOHAN - Business Development Manager - 9444057131")
_CONTACT_BOTH = ("Mr. B. MAGESWARAN - Sales Head - 9444057133\n"
                 "Mr. D.SAM MOHAN - Business Development - 9444057131")

FORMS = {
    "paint_booth": {
        "title": "Data Sheet for Painting Plant",
        "header_fields": ["Company Name & Address", "Date",
                          "Contact Person & Designation", "Contact No. / Mobile",
                          "Site Location", "Mail Id"],
        "contacts": _CONTACT_SAM,
        "closing_note": "NOTE: Please provide auto cad drawing of plant layout by mail",
        "body": [
            ("section", "1.0 COMPONENT MATRIX:"),
            ("table", _MATRIX_HEADERS, _MATRIX_WIDTHS, 5),
            ("sub", "Please tick the appropriate columns:"),
            *_PLANT_HANDLING,

            ("section", "2.0 PRE - TREATMENT PLANT:"),
            ("sub", "PRETREATMENT PROCESS: (As recommended by your chemical supplier)"),
            ("table",
             ["Sl. No", "CHEMICAL\nPROCESS", "TEMPERATURE\n(DEGREE In CELSIUS)",
              "DURATION\nTIME", "AIR\nAGITATION", "ADDITIONAL\nREQUIREMENTS"],
             [10, 26, 32, 22, 22, 30], 6),
            ("choice", "Type", ["Sand Blasting", "Chemical treatment"]),
            ("sub", "(For Sand Blasting)"),
            ("choice", "Process Gun", ["Auto", "Manual"]),
            ("choice", "Material Handling", ["Conveyor", "Trolley"]),
            ("sub", "(For Chemical Treatment)"),
            ("choice", "Type of PT plant", ["DIP", "SPRAY TUNNEL"]),

            ("section", "2.1 FOR HOT PROCESS:"),
            ("choice", "Heating Media Preferred", ["Electrical", "LPG GAS", "CNG GAS"]),
            ("choice", "Handling for Pretreatment", ["Hoist", "Transporter", "Conveyor (if Spray)"]),
            ("choice", "Pump circulation PT tanks", ["Required", "Not Required"]),
            ("choice", "Preferred MOC", ["SS", "MS", "MS+FRP"]),
            ("choice", "Air agitation for PT tanks", ["Required", "Not Required"]),
            ("choice", "Fume extraction for PT tanks", ["Required", "Not required"]),
            ("sub", "(if required, Wet scrubber shall be offered)"),
            ("choice", "Dry Off Oven", ["Required", "Not Required"]),
            ("field", "Mention if any other requirements"),

            ("section", "3.0 PAINTING BOOTH:"),
            ("field", "Process Sequence of Painting (No. of Coats)"),
            ("choice", "Purpose", ["Buffing", "Primer", "Base", "Clear", "Top"]),
            ("choice", "Type of paint", ["Primer", "Epoxy", "PU", "Marine Primer/paint"]),
            ("field", "Flash off duration (Minutes, as recommended by Paint Supplier)"),
            ("choice", "If Batch type process, Flash off Booth", ["Required", "Not Required"]),
            ("field", "Drying / baking duration (Minutes)"),
            ("field", "Drying temperature (Deg C)"),
            ("choice", "Type of Paint Booth", ["Water curtain", "Dry type"]),
            ("choice", "For Wet booth, the water tank is required",
             ["Above Ground level", "Below Ground level"]),
            ("sub", "(For below ground level - Civil pit will be provided by you)"),
            ("choice", "For Dry Booth", ["Side Draft", "Cross Draft", "Down Draft"]),
            ("choice", "Dry Scrubber", ["Yes", "No"]),
            ("sub", "(It is mandatory to provide scrubber on paint booth exhaust to "
                    "eliminate VOC as required by PCB)"),
            ("choice", "Exhaust Ducts", ["Above Shed", "Outside of the Building"]),
            ("choice", "Electrical fittings & Motors", ["Ordinary", "Flame proof"]),
            ("choice", "Fire extinguishing system", ["Required", "Not Required"]),
            ("choice", "Material Handling for Painting", ["Hoist", "Trolley", "Conveyor"]),

            ("section", "4.0 DRYING OVEN:"),
            ("choice", "Type", ["Batch", "Conveyor"]),
            ("choice", "Mounting", ["Elevated", "Floor"]),
            ("field", "Max Operating Temperature (deg C)"),
            ("field", "Temperature Accuracy desired", "+/- 5 deg C"),
            ("choice", "Oven heating media", ["Diesel", "GAS", "Electrical"]),
            ("choice", "Oven Application", ["Drying Paint", "Curing Powder"]),
            ("choice", "No of Doors", ["Front", "Front & Rear"]),
            ("choice", "Material Handling",
             ["Trolley", "Conveyor (Over head)", "Push Pull Trolley", "Floor"]),

            ("section", "5.0 FRESH AIR SYSTEM (for Pressurized Booth):"),
            ("choice", "Requirement (cleanliness level) Microns",
             ["5 to 10", "Below 5", "Below 1", "HEPA (0.3 micron)"]),
            ("choice", "Air wetting (water washer)", ["Required", "Not Required"]),
            ("choice", "Location of AHU",
             ["On Top of the Booth", "Side of Booth", "Outside Building"]),
            ("field", "Site Condition (any obstructions for duct routing)"),
            ("choice", "Temperature system", ["Heating", "Cooling"]),

            ("section", "6.0 PLANT:"),
            *_PLANT_SECTION,
        ],
    },

    "powder_coating_plant": {
        "title": "Data Sheet for Powder Coating Plant",
        "header_fields": ["Company Name & Address", "Date",
                          "Contact Person & Designation", "Contact No. / Mobile",
                          "Site location", "Mail id"],
        "contacts": _CONTACT_SAM,
        "closing_note": None,
        "body": [
            ("section", "1.0 COMPONENT MATRIX:"),
            ("table", _MATRIX_HEADERS, _MATRIX_WIDTHS, 5),
            ("sub", "Please tick the appropriate columns:"),
            *_PLANT_HANDLING,

            ("section", "2.0 POWDER COATING PROCESS:"),
            ("choice", "2.1.1  PRETREATMENT", ["Required", "Not required"]),
            ("choice", "2.1.2  POWDER COATING BOOTH", ["Required", "Not required"]),
            ("choice", "2.1.3  CURING OVEN", ["Required", "Not required"]),

            ("section", "3.0 PRETREATMENT:"),
            ("choice", "Type of PT plant", ["Dip", "Spray"]),
            ("sub", "Process recommended by your chemical supplier"),
            ("table",
             ["Sl.\nNo", "Chemical\nProcess", "Temp\n(Deg.C)", "Duration\nTime",
              "MOC\nSS/MS/FRP", "Air\nAgitation", "Pump\ncirculation",
              "Additional\nrequirement", "Fume Extraction\nSystem"],
             [8, 20, 14, 16, 18, 14, 18, 22, 24], 11, 5.2),
            ("choice", "Heating Media Preferred", ["Electrical", "LPG GAS", "CNG GAS"]),
            ("choice", "Handling for Pretreatment",
             ["Monorail Hoist", "Transporter", "Conveyor (if Spray)"]),
            ("choice", "Pump circulation PT tanks", ["Required", "Not Required"]),
            ("sub", "(Degreasing & Phosphating Tank to be suggested)"),
            ("choice", "Air agitation for PT tanks", ["Required", "Not Required"]),
            ("choice", "Fume extraction for PT tanks", ["Required", "Not required"]),
            ("sub", "(if required, Wet scrubber shall be offered)"),
            ("choice", "Dry Off Oven", ["Required", "Not Required"]),

            ("section", "4.0 POWDER COATING BOOTH:"),
            ("choice", "Type of coating", ["Manual", "Automatic (Reciprocators)"]),
            ("choice", "No of Operators (Manual)", ["Single", "Double"]),
            ("field", "No of colors"),
            ("choice", "Powder Recovery",
             ["Cyclone Recovery Unit", "Cartridge Filter Unit"]),

            ("section", "5.0 CURING OVEN:"),
            ("choice", "Type", ["Batch", "Conveyor"]),
            ("choice", "Mounting", ["Elevated (Camel Back)", "Floor"]),
            ("field", "Max Operating Temperature (deg C)"),
            ("field", "Temperature Accuracy desired", "+/- 5 deg C"),
            ("choice", "Oven heating media", ["Diesel", "GAS", "Electrical"]),
            ("choice", "Oven Application", ["Drying Paint", "Curing Powder"]),
            ("choice", "No of Doors", ["Front", "Front & Rear"]),
            ("field", "Mass of component / Batch"),
            ("choice", "Material Handling",
             ["Trolley", "Conveyor (Overhead Push Pull Trolley)"]),

            ("section", "6.0 PLANT:"),
            *_PLANT_SECTION,
        ],
    },

    "dust_collector": {
        "title": "Data Sheet for Dust Collection Equipment",
        "header_fields": ["Company Name & Address", "Contact Person & Designation",
                          "Contact No. / Mobile", "Telephone / Fax (Business)",
                          "Assistant's Contact Name & No."],
        "contacts": _CONTACT_BOTH,
        "closing_note": None,
        "body": [
            ("field", "Description of Process"),
            ("field", "Operation"),
            ("field", "Name / Nature and Size of Dust"),
            ("field", "Temperature if any"),
            ("field", "Source of dust generation"),
            ("sub", "(Details of equipment generating dust)"),
            ("note", "Please provide machinery and Shop floor layout drawing"),
            ("field", "Total No. of points to be sucked"),
            ("field", "Size of the openings from where dust is generated"),
            ("field", "Plant layout with M/c locations"),
            ("choice", "Dust Collector location", ["Indoor", "Outdoor"]),
            ("field", "Suction Point to Dust Collection Distance"),
            ("field", "Space available for unit installation"),
            ("choice", "Electricity supply available", ["Yes", "No"]),
            ("choice", "Existing dust collection if any", ["Yes", "No"]),
            ("field", "Any Specific Requirement"),
        ],
    },
}

# a couple of friendly aliases onto the same form
FORM_ALIASES = {
    "painting_plant": "paint_booth",
    "paint": "paint_booth",
    "powder_coating_booth": "powder_coating_plant",
    "powder": "powder_coating_plant",
    "dust_collection": "dust_collector",
    "dust": "dust_collector",
}


def available_forms() -> list[dict]:
    return [{"category": k, "title": v["title"]} for k, v in FORMS.items()]


def resolve_form(category: str):
    key = str(category or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = FORM_ALIASES.get(key, key)
    return key if key in FORMS else None


def render_datasheet_pdf(category: str, prefill: dict | None = None) -> bytes:
    """Render the enquiry data sheet for `category`.

    `prefill` maps a field label to a value (printed verbatim) or a choice label
    to the option(s) to tick. Unknown labels are ignored — a data sheet is never
    completed with a value the caller did not supply.

    Several labels repeat across sections ("Type", "Material Handling"), so a
    bare label fills only its FIRST occurrence. To reach a later one, qualify
    the key with its section: "2.0 PRE - TREATMENT PLANT::Material Handling".
    """
    key = resolve_form(category)
    if key is None:
        raise ValueError(f"no data sheet for category {category!r}")
    form = FORMS[key]
    fill = {str(k).strip().lower(): v for k, v in (prefill or {}).items()}
    used: set[str] = set()
    section_now = ""

    def _fill_for(label):
        lab = str(label).strip().lower()
        qualified = f"{section_now.strip().lower()}::{lab}"
        if qualified in fill:
            used.add(qualified)
            return fill[qualified]
        if lab in fill and lab not in used:   # bare label -> first occurrence only
            used.add(lab)
            return fill[lab]
        return None

    pdf = _DSPDF(format="A4")
    lh.apply_page_setup(pdf)
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    _title(pdf, form["title"])
    for lbl in form["header_fields"]:
        v = _fill_for(lbl)
        _field(pdf, lbl, "" if v is None else str(v))
    pdf.ln(1)
    pdf.set_draw_color(*TEXT)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + usable, pdf.get_y())
    pdf.ln(2)

    for el in form["body"]:
        kind = el[0]
        if kind == "section":
            section_now = el[1].rstrip(":")
            _section(pdf, el[1])
        elif kind == "sub":
            _note(pdf, el[1])
        elif kind == "note":
            _note(pdf, el[1], bold=True)
        elif kind == "field":
            default = el[2] if len(el) > 2 else ""
            v = _fill_for(el[1])
            _field(pdf, el[1], str(v) if v is not None else default)
        elif kind == "choice":
            v = _fill_for(el[1])
            chosen = v if isinstance(v, (list, tuple, set)) else ([v] if v else [])
            _choice(pdf, el[1], el[2], chosen)
        elif kind == "table":
            _table(pdf, el[1], el[2], el[3], el[4] if len(el) > 4 else 6.0)

    if form.get("closing_note"):
        pdf.ln(2)
        _note(pdf, form["closing_note"])
    pdf.ln(2)
    _note(pdf, "Note: For any assistance in completing the above please feel free to contact",
          bold=True)
    for line in form["contacts"].split("\n"):
        _note(pdf, line)

    out = pdf.output()
    return bytes(out) if isinstance(out, (bytearray, memoryview)) else out


if __name__ == "__main__":  # manual render for eyeballing
    for cat in FORMS:
        with open(f"_ds_{cat}.pdf", "wb") as f:
            f.write(render_datasheet_pdf(cat))
        print("wrote", f"_ds_{cat}.pdf")
    with open("_ds_filled.pdf", "wb") as f:
        f.write(render_datasheet_pdf("paint_booth", {
            "Company Name & Address": "FORNNAX TECHNOLOGY (P) LIMITED",
            "Date": "09.03.2026",
            "Type of plant": "Batch",
            "Material Handling": "Trolley",
            "If Trolley": "Manual",
            "Type of Paint Booth": "Dry type",
            "Type of paint": ["Primer", "Epoxy", "PU"],
            "Oven heating media": "Electrical",
            "Max Operating Temperature (deg C)": "200",
        }))
    print("wrote _ds_filled.pdf")
