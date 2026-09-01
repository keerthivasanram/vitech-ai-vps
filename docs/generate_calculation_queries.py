"""Generate the calculation-workbook query PDF sent TO Vitech.

Run:  backend/.venv/bin/python docs/generate_calculation_queries.py

This is the follow-up to `generate_information_request.py`: that one asked for
the engineering knowledge, this one asks about the SIX WORKBOOKS Vitech then
supplied (2026-09-01). Every question below was raised by implementing their
formulas, not by reading them, and each cites the cell it came from so an
engineer can open the file and see the same thing we did.

It reuses the sibling script's house style rather than restating it - same
document family, same look, one place to change it.
"""
from datetime import date

from generate_information_request import (ACCENT, BAND, CRIT, Doc, INK, MUTED,
                                          RECIPIENT, RULE, SENDER, _t, avail,
                                          band, body, bullet, h1, h2, note,
                                          table)

TITLE = "Calculation Workbook Queries"
SUBTITLE = "Questions arising from the six calculation sheets, and what each one blocks"

# Every open question, in the order they should be answered: what blocks the
# most work comes first, not what is easiest to answer.
QUESTIONS = [
    dict(
        id="Q1", blocks="Airflow, blower, filters, ducting and price of every paint booth", tag="BLOCKS EVERY BOOTH",
        title="Which dimension is the extracted face, and which height?",
        found=[
            "In `Standard Booth.xlsx` the airflow formula is =1.5*2.4*0.5*3600, where 1.5 is "
            "the L column and 2.4 is H. The W column is a menu of options "
            "(1250 / 1500 / 2250 / 3000) and never enters the calculation at all.",
            "The costing workbook agrees: cells K5 and L5 take L and H, giving 3.0 x 2.4 = "
            "7.2 m2 and 12,960 CMH for the 3.0m L x 2.4m W x 2.4m H booth.",
            "The AI knowledge-base PDF you supplied uses the OPPOSITE naming - it calls that "
            "same open front W and the depth D - and computes on a 1.5 m EFFECTIVE FILTER "
            "OPENING, not the full height: CMH = W x 1.5 x 0.5 x 3600.",
        ],
        impact="For one 3.0 m wide booth the two documents give 12,960 CMH and 8,100 CMH - a "
               "60% difference. That selects a different blower, a different motor, a "
               "different filter count and a different price.",
        ask=[
            "For a booth you describe as 3.0m L x 2.25m W x 2.4m H, is the extracted face "
            "3.0 x 2.4, or 3.0 x 1.5?",
            "When a customer states three dimensions in an enquiry, which one is the open "
            "front? We currently read the SECOND number as the face width, which is your "
            "depth.",
        ],
    ),
    dict(
        id="Q2", blocks="Dry-off oven heater sizing", tag="SAFETY-ADJACENT",
        title="Dry-off oven air density - 101.325 or 1.204?",
        found=[
            "`Heat Load.xlsx` -> Dry off Oven, cell N13 gives the air density as 101.325. "
            "That is standard atmospheric PRESSURE in kPa, not a density.",
            "The Curing Oven sheet uses 1.204 kg/m3 for the same quantity, which is the "
            "density of air.",
            "Read as a density, 101.325 is about 84x too high. On your worked oven the air "
            "term becomes 86,670 of the 188,786 Kcal total - nearly half the heater.",
        ],
        impact="If 101.325 is a typo, every dry-off oven sized from this sheet is "
               "substantially oversized. If it is deliberate (a leakage or air-change "
               "allowance folded into one number), we need to know that, because we would "
               "otherwise 'correct' a figure you intended.",
        ask=["Should the dry-off oven use 1.204 kg/m3, or is 101.325 carrying something else?"],
    ),
    dict(
        id="Q3", blocks="Both oven heat loads", tag="CONFIRM A TYPO",
        title="The oven steel-mass cell adds an area to a mass",
        found=[
            "`Heat Load.xlsx` -> Dry off Oven D18 (and Curing Oven D17, identically):",
            "=ROUNDUP(((D8/1000*F8/1000)*2)+((E8/1000*F8/1000)*2)"
            "+((D8/1000*E8/1000)*3)*N12/1000*H18,0)",
            "The '* density * thickness' at the end binds to the THIRD term only. So the two "
            "wall terms - 25.8 and 16.5 square METRES on your worked oven - are added "
            "straight to a mass in kilograms.",
            "The cell returns 377 kg. The formula as written in words gives 733 kg. Your "
            "curing oven reads 1,647 kg where the same wording gives 3,016 kg.",
        ],
        impact="We reproduce your cell exactly, so your totals (188,786 Kcal / 220 kW) come "
               "out right - but we cannot adopt a formula that adds m2 to kg. Until this is "
               "confirmed our oven figures will differ from yours by exactly this amount.",
        ask=["Is the bracket a typo? If so we will use the sound reading and your sheets "
             "should be corrected, since both oven sheets carry it."],
    ),
    dict(
        id="Q4", blocks="Scrubber and duct sizing, and the GA drawing that follows it", tag="BLOCKS SCRUBBER SIZING",
        title="Scrubber and duct diameters - what is the standard ladder?",
        found=[
            "`Vertical Scrubber - Diameter calculation.xlsx` computes D = 1545 mm at "
            "6750 CMH (cell D12), and the row beneath it (D13) reads '~ 950'.",
            "950 mm corresponds to roughly 2550 CMH, not 6750. The same happens on both "
            "ducts: computed 399 mm, typed '~ 300' and '~ 350'.",
            "We checked the cells: those three rows are hand-typed TEXT, not formulas, so "
            "they appear to be leftovers from an earlier run.",
        ],
        impact="We can compute the diameter exactly as your sheet does, and we do. We cannot "
               "round it to a size you actually build without knowing your standard "
               "diameters and whether you round up or to nearest.",
        ask=[
            "What are your standard tower and duct diameters?",
            "Do you round up to the next standard size, or to the nearest?",
        ],
    ),
    dict(
        id="Q5", blocks="Structural weight in the BOM and the cost", tag="COSTING",
        title="MS flat - 12 kg or 16 kg per 6 m length?",
        found=[
            "The paint-booth sheet costs MS Flat 40 x 6 x 6000 at 12 kg per length.",
            "The cyclone sheet costs MS FLAT 40x6x6000 at 16 kg per length.",
            "40 x 6 mm x 6 m of mild steel weighs about 11.3 kg, so 12 matches the steel and "
            "16 does not.",
            "Note we resolved the square-tube difference ourselves - the booth uses "
            "40x40x3 (21 kg) and the cyclone 40x40x2 (18 kg), two different sections. Only "
            "the flat remains.",
        ],
        impact="Structural weight feeds the BOM and the cost. A 33% error on a section runs "
               "straight into the quoted price.",
        ask=["Which figure governs for MS flat, and is the 16 kg row a different section?"],
    ),
    dict(
        id="Q6", blocks="Rate card and every painted line in a quotation", tag="COSTING",
        title="Painting rate - Rs 35 or Rs 50 per sq.ft?",
        found=[
            "Within `Cyclone recovery & Cartridge filter unit.xlsx`, the cartridge filter "
            "unit costs painting at Rs 35/sq.ft (cell H14) while the cyclone and the ducting "
            "use Rs 50/sq.ft (H14 and H23 of the other sheet).",
            "The paint-booth sheet uses Rs 35/sq.ft.",
        ],
        impact="On the cartridge unit alone the painting line is Rs 75,250 - it is not a "
               "rounding difference.",
        ask=[
            "Is Rs 50 a different paint specification (two-coat, epoxy, a different surface "
            "preparation), or a rate change?",
            "Which rate should the platform quote by default?",
        ],
    ),
    dict(
        id="Q7", blocks="Cyclone / cartridge cost model", tag="COSTING",
        title="An unlabelled Rs 70,000 line",
        found=[
            "`Cyclone recovery & Cartridge filter unit.xlsx` -> Combine, cell B5 is a "
            "hardcoded 70,000 with no description and no formula. It is 13% of the "
            "Rs 5,28,790 works cost.",
        ],
        impact="We cannot reproduce your total without knowing what it buys, and we will not "
               "invent a line item to make a total balance.",
        ask=["What is the Rs 70,000 - blower, panel, erection, something else?"],
    ),
    dict(
        id="Q8", blocks="The whole quotation margin model", tag="COMMERCIAL POLICY",
        title="How is the margin multiplier chosen?",
        found=[
            "The booth workbook applies x1.40 to the booth and x1.26 to the exhaust duct, "
            "adds fixed lines for design (25,000), packing (11,000) and E&C (65,000), then "
            "deducts a 10% discount, landing at 27% profit.",
            "The cyclone workbook instead shows three alternatives - x1.35, x1.25 and x1.17 "
            "- beside a typed Rs 7,60,000 and a Rs 1,50,000 deduction, which reads like a "
            "negotiation rather than a rule.",
        ],
        impact="Our current model applies a flat 15% allowance for bought-out items, which "
               "is why our cost-plus figure diverges from your history by up to 57%. Your "
               "per-line multipliers would replace it - we just need the selection rule.",
        ask=[
            "What decides the multiplier - equipment type, order value, customer, "
            "competition?",
            "Are the fixed lines (design / packing / E&C) always those amounts, or do they "
            "scale?",
            "Is the 10% discount a standard concession or was it specific to that enquiry?",
        ],
    ),
]

RESOLVED = [
    ("Face velocity", "0.5 m/s, stated in two of your workbooks",
     "Adopted. It replaces the NFPA 33 default of 0.45 we had used while your earlier "
     "document was silent. Every booth airflow rose about 11%."),
    ("Square tube weight", "21 kg vs 18 kg per 6 m",
     "Not a conflict - two thicknesses (40x40x3 and 40x40x2). Both now on file."),
    ("The Rs 80,730 gap", "Your cost sheet's first row was cropped in the earlier image",
     "Recovered: MS 18 SWG sheet, 621 kg, RM 52,785 + labour 27,945. Your total of "
     "Rs 6,49,264 now reconciles exactly."),
    ("Booth sheet weight", "We computed 1,240 kg, our pricing model assumed 3,645 kg",
     "Your panel module settles it: 27 panels x 23 kg = 621 kg. Both of our figures were "
     "wrong."),
    ("Rates", "Rs 85 + 45 /kg sheet, Rs 75 + 50 /kg sections, Rs 3,500/HP",
     "All confirmed against your cost sheet, and the cyclone sheet's Rs 130/kg is the same "
     "85 + 45."),
    ("Blower selection", "9000 CFM booth duty",
     "Our selector reproduces your BOM line CLP-4-10-9000 exactly."),
]


class QueryDoc(Doc):
    """Same shell, this document's own running head.

    `Doc.header()` reads the sibling module's TITLE, so without this override
    every page of this PDF is headed "Engineering Knowledge Request".
    """

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*MUTED)
        self.set_y(9)
        self.cell(0, 4, _t(TITLE), align="L")
        self.cell(0, 4, _t(RECIPIENT["company"]), align="R")
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(self.l_margin, 14, self.w - self.r_margin, 14)
        self.set_y(22)


def sub(p: Doc, text: str):
    """Bold in-question sub-heading.

    It resets X to the left margin afterwards. `multi_cell` leaves the cursor at
    the RIGHT edge, and `body()` starts from wherever X happens to be - which
    silently printed every "Why it matters" paragraph off the side of the page
    until the PDF was rendered and looked at.
    """
    p.set_font("Helvetica", "B", 9)
    p.set_text_color(*INK)
    p.multi_cell(avail(p), 4.6, _t(text))
    p.set_x(p.l_margin)


def cover(p: Doc):
    p.add_page()
    p.set_fill_color(*ACCENT)
    p.rect(0, 0, p.w, 52, style="F")
    p.set_text_color(255, 255, 255)
    p.set_font("Helvetica", "B", 20)
    p.set_xy(p.l_margin, 16)
    p.multi_cell(avail(p), 9, _t(TITLE))
    p.set_font("Helvetica", "", 10.5)
    p.set_x(p.l_margin)
    p.multi_cell(avail(p), 5.4, _t(SUBTITLE))

    p.set_y(62)
    p.set_text_color(*INK)
    p.set_font("Helvetica", "", 9.5)
    p.multi_cell(avail(p), 5, _t(
        f"To:   {RECIPIENT['company']}  ({RECIPIENT['attn']})\n"
        f"From: {SENDER['company']}\n"
        f"Date: {date.today().strftime('%d %B %Y')}"))
    p.ln(4)

    band(p, "Why this document exists")
    body(p, _t(
        "You supplied six calculation workbooks. We have transcribed every formula in them "
        "and implemented four - the VOC and LEL check, the tank and oven heat loads, the "
        "scrubber and duct diameters, and the structural stock weights - each verified "
        "against the worked example on your own sheet."))
    body(p, _t(
        "The eight questions below are what implementing them raised. They are not requests "
        "for more documents. Each one is a point where your sheets either disagree with each "
        "other, or where a cell does something its own description does not, and where "
        "guessing would put a number we invented into a document a customer reads."))
    note(p, _t(
        "Answer Q1 first if you answer nothing else. It decides the airflow, and the airflow "
        "decides the blower, the motor, the filters, the ducting and the price of every "
        "paint booth the platform quotes."))

    h2(p, "The eight questions at a glance")
    table(p, [16, 30, 90, 38],
          ["#", "Area", "Question", "Blocks"],
          [[q["id"], q["tag"].title(), q["title"], q["blocks"]] for q in QUESTIONS])


def questions(p: Doc):
    h1(p, "The questions", "1.")
    for q in QUESTIONS:
        h2(p, f"{q['id']}.  {q['title']}")
        p.set_font("Helvetica", "B", 8)
        p.set_text_color(*(CRIT if "BLOCKS" in q["tag"] else MUTED))
        p.multi_cell(avail(p), 4.2, _t(q["tag"]))
        p.set_text_color(*INK)
        p.ln(1.5)

        sub(p, "What we found")
        for f in q["found"]:
            bullet(p, f)
        p.ln(1)

        sub(p, "Why it matters")
        body(p, q["impact"])

        sub(p, "What we need from you")
        for a in q["ask"]:
            bullet(p, a)
        p.ln(3)


def resolved(p: Doc):
    h1(p, "What we already settled from the workbooks", "2.")
    body(p, _t(
        "So the list above is read for what it is - the genuine remainder, not a request to "
        "re-explain your own documents. Everything here was answered by the sheets "
        "themselves and needs nothing further from you."))
    table(p, [34, 58, 82], ["Item", "What was in question", "Resolution"],
          [[a, b, c] for a, b, c in RESOLVED])


def closing(p: Doc):
    h1(p, "What happens when you answer", "3.")
    body(p, _t(
        "Q1 releases the booth engine: the airflow, blower, filter and duct chain, the "
        "panel-count weight model and a validated booth cost model that reconciles to your "
        "own Rs 6,49,264. Q2 and Q3 release the oven heat loads. Q4 releases scrubber "
        "sizing. Q5 to Q8 release the costed BOM and the quotation margin."))
    body(p, _t(
        "One further note, offered rather than asked. Your AI database PDF lists a real "
        "standard range - VT/1.5 through VT/4.5, front-open and enclosed, wet and dry, each "
        "with its airflow and motor. The platform currently engineers every booth from "
        "first principles. Once Q1 is settled it could instead recognise a standard model "
        "and quote it directly, which is both faster and closer to how you actually sell."))
    p.ln(2)
    band(p, "Contact")
    body(p, _t(SENDER["contact"]))


def build(path: str = "docs/Vitech_Calculation_Workbook_Queries.pdf"):
    p = QueryDoc(orientation="P", unit="mm", format="A4")
    p.set_auto_page_break(auto=True, margin=18)
    p.set_margins(18, 22, 18)
    p.set_title(_t(TITLE))
    p.set_author(_t(SENDER["company"]))
    p.set_subject(_t(SUBTITLE))
    cover(p)
    questions(p)
    resolved(p)
    closing(p)
    p.output(path)
    return path, p.page_no()


if __name__ == "__main__":
    out, pages = build()
    print(f"wrote {out}  ({pages} pages)")
