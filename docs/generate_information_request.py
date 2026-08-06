"""Generate the engineering-knowledge request PDF sent TO Vitech.

Run:  backend/.venv/Scripts/python.exe docs/generate_information_request.py

NOTE ON LETTERHEAD: this document is FROM the platform team TO Vitech, so it
deliberately does NOT use `app/vitech_letterhead.py`. That letterhead belongs on
documents Vitech issues to ITS customers; putting it here would misattribute
authorship. Set SENDER below to your own company details.

fpdf2 core fonts are latin-1 only, so `_t()` folds the usual typographic
characters down to ASCII. Keep new text plain.
"""
from datetime import date

from fpdf import FPDF

SENDER = {
    "company": "[Your Company Name]",
    "line1": "[Address line]",
    "line2": "[City, PIN]",
    "contact": "[Contact name]  |  [email]  |  [phone]",
}
RECIPIENT = {
    "company": "Vitech Enviro Systems Pvt. Ltd.",
    "attn": "Engineering / Applications Team",
}
TITLE = "Engineering Knowledge Request"
SUBTITLE = "Information required to build the AI Engineering Platform"

INK = (17, 24, 39)
MUTED = (100, 116, 139)
RULE = (203, 213, 225)
ACCENT = (13, 90, 130)
BAND = (241, 245, 249)
CRIT = (159, 18, 57)

_SUBS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
    "•": "-", " ": " ", "≥": ">=", "≤": "<=",
}


def _t(s: str) -> str:
    for k, v in _SUBS.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


class Doc(FPDF):
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
        self.line(self.l_margin, 15, self.w - self.r_margin, 15)
        self.set_y(22)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-11)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, _t(f"{SENDER['company']}  |  {date.today().strftime('%d %B %Y')}"), align="L")
        self.cell(0, 4, _t(f"Page {self.page_no() - 1}"), align="R")


def avail(p: Doc) -> float:
    return p.w - p.l_margin - p.r_margin


def h1(p: Doc, text: str, num: str = ""):
    p.ln(3)
    if p.get_y() > p.h - 45:
        p.add_page()
    p.set_font("Helvetica", "B", 13)
    p.set_text_color(*ACCENT)
    p.multi_cell(avail(p), 6.5, _t(f"{num}  {text}" if num else text))
    p.set_draw_color(*ACCENT)
    p.set_line_width(0.5)
    y = p.get_y() + 1
    p.line(p.l_margin, y, p.l_margin + 26, y)
    p.ln(4)


def h2(p: Doc, text: str):
    # Keep-with-next: a heading must have room for itself AND a few lines of the
    # text it introduces, or it strands at the foot of the page while its content
    # moves on without it.
    if p.get_y() > p.h - 45:
        p.add_page()
    p.ln(1.5)
    p.set_font("Helvetica", "B", 10)
    p.set_text_color(*INK)
    p.multi_cell(avail(p), 5, _t(text))
    p.ln(1)


def _flow(p: Doc, width: float, lh: float, text: str):
    """Move to the next page rather than stranding a widow line.

    Without this, a paragraph that overruns by one or two lines leaves those
    lines alone at the top of a page that the next section then abandons -- which
    is exactly how page 4 came out holding a single sentence.
    """
    lines = len(p.multi_cell(width, lh, _t(text), dry_run=True, output="LINES"))
    need = lines * lh
    room = p.h - p.b_margin - p.get_y()
    page = p.h - p.b_margin - p.t_margin
    if need > room and need <= page and (need - room <= 2 * lh or room < 3 * lh):
        p.add_page()


def body(p: Doc, text: str, size: float = 9.2, gap: float = 1.8):
    p.set_font("Helvetica", "", size)
    p.set_text_color(*INK)
    _flow(p, avail(p), 4.6, text)
    p.multi_cell(avail(p), 4.6, _t(text))
    p.ln(gap)


def note(p: Doc, text: str):
    """Indented explanatory line, lighter than body."""
    p.set_font("Helvetica", "I", 8.6)
    p.set_text_color(*MUTED)
    _flow(p, avail(p) - 5, 4.3, text)
    p.set_x(p.l_margin + 5)
    p.multi_cell(avail(p) - 5, 4.3, _t(text))
    p.ln(1.5)


def bullet(p: Doc, text: str, indent: float = 4.0):
    p.set_font("Helvetica", "", 9.2)
    _flow(p, avail(p) - indent - 4, 4.5, text)
    if p.get_y() > p.h - 24:
        p.add_page()
    p.set_text_color(*INK)
    x0 = p.l_margin + indent
    y0 = p.get_y()
    p.set_fill_color(*ACCENT)
    p.rect(x0, y0 + 1.7, 1.4, 1.4, style="F")
    p.set_xy(x0 + 4, y0)
    p.multi_cell(avail(p) - indent - 4, 4.5, _t(text))
    p.ln(0.6)


def band(p: Doc, text: str, fill=BAND, colour=INK):
    if p.get_y() > p.h - 30:
        p.add_page()
    p.set_fill_color(*fill)
    p.set_text_color(*colour)
    p.set_font("Helvetica", "B", 9)
    p.multi_cell(avail(p), 5.6, _t(text), fill=True)
    p.ln(2)


def table(p: Doc, widths, headers, rows, size: float = 8.4, head_fill=BAND):
    """Grid table that never splits a row across a page break."""
    def row_h(cells):
        p.set_font("Helvetica", "", size)
        n = 1
        for w, c in zip(widths, cells):
            n = max(n, len(p.multi_cell(w - 3, 4.1, _t(str(c)), dry_run=True,
                                        output="LINES")))
        return n * 4.1 + 2.4

    def draw_head():
        p.set_font("Helvetica", "B", size)
        p.set_fill_color(*head_fill)
        p.set_text_color(*INK)
        p.set_draw_color(*RULE)
        p.set_line_width(0.2)
        h = row_h(headers)
        y = p.get_y()
        for w, c in zip(widths, headers):
            x = p.get_x()
            p.rect(x, y, w, h, style="DF")
            p.set_xy(x + 1.5, y + 1.2)
            p.multi_cell(w - 3, 4.1, _t(str(c)))
            p.set_xy(x + w, y)
        p.set_y(y + h)

    if p.get_y() > p.h - 40:
        p.add_page()
    draw_head()
    for r in rows:
        h = row_h(r)
        if p.get_y() + h > p.h - 20:
            p.add_page()
            draw_head()
        y = p.get_y()
        p.set_font("Helvetica", "", size)
        p.set_text_color(*INK)
        for w, c in zip(widths, r):
            x = p.get_x()
            p.rect(x, y, w, h)
            p.set_xy(x + 1.5, y + 1.2)
            p.multi_cell(w - 3, 4.1, _t(str(c)))
            p.set_xy(x + w, y)
        p.set_y(y + h)
    p.ln(3)


def checklist(p: Doc, items):
    p.set_font("Helvetica", "", 9)
    for it in items:
        if p.get_y() > p.h - 24:
            p.add_page()
        y = p.get_y()
        p.set_draw_color(*MUTED)
        p.set_line_width(0.25)
        p.rect(p.l_margin + 4, y + 0.9, 3.2, 3.2)
        p.set_xy(p.l_margin + 11, y)
        p.set_text_color(*INK)
        p.multi_cell(avail(p) - 11, 4.6, _t(it))
        p.ln(0.8)


# ---------------------------------------------------------------- cover ----

def cover(p: Doc):
    p.add_page()
    p.set_fill_color(*ACCENT)
    p.rect(0, 0, p.w, 46, style="F")
    p.set_text_color(255, 255, 255)
    p.set_font("Helvetica", "B", 21)
    p.set_xy(p.l_margin, 15)
    p.multi_cell(avail(p), 9, _t(TITLE))
    p.set_font("Helvetica", "", 10.5)
    p.set_x(p.l_margin)
    p.multi_cell(avail(p), 5.4, _t(SUBTITLE))

    p.set_y(56)
    p.set_font("Helvetica", "", 9)
    p.set_text_color(*MUTED)
    p.cell(0, 4.6, _t(date.today().strftime("%d %B %Y")),
           new_x="LMARGIN", new_y="NEXT")

    p.ln(5)
    p.set_draw_color(*RULE)
    p.line(p.l_margin, p.get_y(), p.w - p.r_margin, p.get_y())
    p.ln(6)

    h2(p, "Purpose of this document")
    body(p,
         "The AI engineering platform being built for Vitech turns a customer requirement into a "
         "technical specification, a general-arrangement drawing, a bill of materials and a "
         "budgetary quotation. Every number it produces is calculated by engineering rules and "
         "your own historical designs - the language model only writes the surrounding text. It "
         "never invents a dimension, a capacity, a material or a price.")
    body(p,
         "That design has one consequence: the platform can only be as complete as the "
         "engineering knowledge it is given. This document lists what we need from Vitech, and "
         "explains why each item matters and what it unlocks.")

    band(p, "We are not asking for project paperwork. We are asking for the engineering "
            "knowledge your application and design engineers already use every day.")

    h2(p, "How this document is organised")
    bullet(p, "Part 1 - Engineering assets. The twelve categories of material that teach the "
              "platform how Vitech engineers.")
    bullet(p, "Part 2 - Specific open items. Named gaps that are blocking identified features "
              "today. These are the highest-value items in this document.")
    bullet(p, "Part 3 - Readiness questions. A short set of questions whose answers define how "
              "the platform decides a requirement is complete enough to work from.")
    bullet(p, "Part 4 - Practical notes. Formats, handling and confidentiality.")
    bullet(p, "Appendix - A checklist you can work through and return.")

    p.ln(2)
    body(p, "Partial material is genuinely useful. Please do not hold anything back waiting to "
            "assemble a complete set - each item can be put to work on its own, and Part 2 "
            "items in particular unblock work immediately.")


# --------------------------------------------------------------- part 1 ----

def part1(p: Doc):
    p.add_page()
    h1(p, "Engineering assets", "PART 1")
    body(p, "Listed in priority order. Priority reflects how much each item improves the "
            "platform's engineering output, not how hard it is to supply.")

    w = [avail(p) * 0.42, avail(p) * 0.20, avail(p) * 0.38]
    table(p, w,
          ["Asset", "Priority", "What it unlocks"],
          [["1. Customer requirement / enquiry forms", "CRITICAL",
            "Defines exactly what your engineers ask a customer, and in what order"],
           ["2. Design calculation sheets", "CRITICAL",
            "Becomes the deterministic calculation engine"],
           ["3. Engineering rules and design judgement", "CRITICAL",
            "The decisions that are not written down anywhere"],
           ["4. Default assumptions", "CRITICAL",
            "Lets the platform proceed sensibly when a customer does not know a value"],
           ["5. Complete equipment list", "HIGH",
            "Defines the scope the platform must cover"],
           ["6. Standard specifications (completed)", "HIGH",
            "Defines the expected output format and content"],
           ["7. Previous quotations (as issued)", "HIGH",
            "Pricing structure, scope, exclusions and commercial language"],
           ["8. Bills of material", "HIGH",
            "How a specification becomes something manufacturable"],
           ["9. GA drawings", "MEDIUM",
            "Components, proportions and drafting conventions"],
           ["10. Standards followed", "MEDIUM",
            "Lets the platform cite the governing standard for a value"],
           ["11. Document templates", "MEDIUM",
            "House format for issued documents"],
           ["12. Completed project sets", "MEDIUM",
            "End-to-end examples for retrieval and validation"]])

    h2(p, "1. Customer requirement and enquiry forms")
    body(p, "Any form your sales or application engineers use to capture a customer's "
            "requirement. Word, Excel, PDF, or a photograph of a printed or handwritten sheet is "
            "fine. Superseded and draft versions are welcome.")
    note(p, "Why this matters most: these forms record what an experienced Vitech engineer "
            "considers necessary before starting work - exactly what the platform needs in "
            "order to ask the right questions instead of guessing.")

    h2(p, "2. Design calculation sheets")
    body(p, "Excel calculators, sizing spreadsheets, formula sheets, design books, or the "
            "worked longhand calculations an engineer keeps. Please include the constants used "
            "and their units.")
    note(p, "These become executable engineering. Where a calculation is supplied, the platform "
            "computes the value; where it is not, the platform must either copy an older design "
            "or report the field as 'To be determined'.")

    h2(p, "3. Engineering rules and design judgement")
    body(p, "The reasoning your engineers apply that is not captured in any calculation sheet. "
            "This is usually the hardest material to collect and the most valuable. Examples:")
    bullet(p, "When a side draft booth is chosen over a down draft booth, and why.")
    bullet(p, "When fan capacity is increased beyond the calculated figure.")
    bullet(p, "Preferred materials of construction for specific corrosive duties.")
    bullet(p, "Standard safety factors and design margins, and when they are varied.")
    bullet(p, "When a duty is split across multiple machines rather than one larger one.")
    note(p, "A recorded conversation or a few bullet points from a senior engineer is perfectly "
            "adequate. It does not need to be a formal document.")

    h2(p, "4. Default assumptions")
    body(p, "What your engineers assume when a customer cannot supply a value. Please give the "
            "value, and the condition under which it changes. A partial answer is still useful.")
    note(p, "A table to complete is provided in the appendix.")

    h2(p, "5. Complete equipment list")
    body(p, "Every equipment type Vitech designs and manufactures, with variants, typical "
            "applications, and whether it is still actively sold. Discontinued equipment should "
            "be marked as such rather than omitted, so the platform does not offer it.")

    h2(p, "6. Standard specifications")
    body(p, "Completed specifications as issued to customers - ideally 20 to 50 per equipment "
            "type, but any number helps. These define which fields appear, in what order, and "
            "the wording used.")

    h2(p, "7. Previous quotations")
    body(p, "Quotations as sent to a customer - not the enquiry data sheets already supplied, "
            "which are input forms (see Part 2, item B4).")

    h2(p, "8. Bills of material")
    body(p, "Fabrication and purchase BOMs, costed where possible - these show which parts are "
            "bought in rather than made.")

    h2(p, "9. GA drawings")
    body(p, "AutoCAD (DWG/DXF) or PDF general-arrangement and layout drawings. DWG or DXF is "
            "considerably more useful, because component positions can be read from it rather "
            "than estimated.")

    h2(p, "10. Standards followed")
    body(p, "IS, CPCB, OSHA, NFPA, customer-imposed and internal standards - with the clause or "
            "value used, where known, so a computed value can cite the standard governing it.")

    h2(p, "11. Document templates")
    body(p, "Specification, quotation and BOM templates, plus inspection reports and test "
            "certificates if these are to be generated later.")

    h2(p, "12. Completed project sets")
    body(p, "One complete chain for a real project: the customer's original requirement, the "
            "specification issued, the GA drawing, the BOM, the quotation, and any revisions "
            "with the reason for each.")
    note(p, "Ten such chains are worth more than a hundred loose documents, because they show "
            "how one stage led to the next.")


# --------------------------------------------------------------- part 2 ----

def part2(p: Doc):
    p.add_page()
    h1(p, "Specific open items", "PART 2")
    body(p, "These are named gaps encountered while building the platform. Each one is currently "
            "blocking an identified feature, so these are the highest-value items in this "
            "document. Several are small.")

    h2(p, "B1. Engineering calculations for the two remaining categories")
    body(p, "The calculation document supplied covers the Paint Shop Plant, and has been "
            "implemented in full. That document states that Powder Coating Plant and Pollution "
            "Control Equipment calculations will follow. Those two are still outstanding.")
    note(p, "Effect today: for those categories the platform reuses the closest historical "
            "design instead of calculating, so a size the archive does not cover is answered "
            "less accurately.")

    h2(p, "B2. Two constants the calculation document does not state")
    bullet(p, "Face velocity. The platform currently uses 0.45 m/s from NFPA 33. Please confirm "
              "this, or give the value Vitech uses per booth type.")
    bullet(p, "Air changes per hour for a drying room or oven. No default exists, so oven "
              "exhaust volume is reported as 'To be determined' on every oven specification.")

    h2(p, "B3. The complete costed BOM for the paint spray booth")
    body(p, "The cost sheet supplied has its first row cut off in the image. The visible lines "
            "total Rs 5,68,534 against a stated total of Rs 6,49,264, leaving Rs 80,730 "
            "unaccounted for.")
    note(p, "Effect today: a cost model cannot be validated against your real total, so no "
            "build-up figure can be trusted. A clean copy of this one sheet unblocks it.")

    h2(p, "B4. A quotation as actually issued to a customer")
    body(p, "The three documents received are enquiry and input data sheets, not offers. They "
            "have been used for the house document style, which is now applied.")
    note(p, "Effect today: the order and content of sections in the generated quotation is our "
            "best estimate rather than Vitech's actual format.")

    h2(p, "B5. Height rule for horizontal baffle wet scrubbers")
    body(p, "For vertical spray towers, tower height is computed from the rule supplied. For "
            "horizontal baffle units no such rule exists, so the platform cannot establish an "
            "overall height and therefore produces no dimensioned drawing for that type.")
    note(p, "This is a single rule and it is the only thing blocking that equipment type from "
            "drawing.")

    h2(p, "B6. Component setting-out rules")
    body(p, "Where components sit within an enclosure: nozzle heights, pump position, filter "
            "bank offsets, luminaire spacing, door and access positions, duct take-off points.")
    note(p, "Effect today: components are drawn schematically and without dimensions, and the "
            "drawing carries a note saying so. Overall envelope dimensions are correct; internal "
            "positions are indicative. This is the main gap between the current output and an "
            "issue-quality general arrangement.")

    h2(p, "B7. Reference documents for the knowledge base")
    body(p, "Standards, vendor catalogues, design guides, technical literature and training "
            "material - in any format.")
    note(p, "Effect today: the platform's knowledge search has no documents to search and "
            "returns nothing. Technical questions are answered from general engineering "
            "knowledge rather than from Vitech's own references.")

    h2(p, "B8. Thin areas in the historical archive")
    body(p, "Thirty-three historical offers are held. Some equipment types are represented by "
            "very few records, which limits how well a new requirement can be matched:")
    w = [avail(p) * 0.44, avail(p) * 0.18, avail(p) * 0.38]
    table(p, w,
          ["Equipment type", "On file", "Consequence"],
          [["Water-wash paint booths", "1 (vs 13 dry-filter)",
            "A water-wash enquiry is matched against dry-filter designs"],
           ["Powder coating plants", "1",
            "Reuse is effectively a copy of that single plant"],
           ["Hot air ovens", "2 (neither LPG-fired)",
            "An LPG requirement is matched to a diesel-fired design"],
           ["Booths recording a dry scrubber value", "1 (9 sq.m)",
            "The field cannot be filled for a booth of a different size"]])
    body(p, "Additional offers in these areas would improve results immediately, with no "
            "software change required.")

    h2(p, "B9. Rate card and commercial policy")
    body(p, "Material rates, fabrication rates, motor and bought-out prices have been supplied "
            "and implemented. Still needed: the standard margin policy, and how bought-out items "
            "are marked up - bought-out items dominate the cost of a booth, so this is the "
            "single largest factor in pricing accuracy.")


# --------------------------------------------------------------- part 3 ----

def part3(p: Doc):
    p.add_page()
    h1(p, "Readiness questions", "PART 3")
    body(p, "The platform is being extended so that it asks a customer for missing information "
            "the way an experienced applications engineer would, rather than producing a draft "
            "from an incomplete enquiry. To do that it needs to know what 'enough information' "
            "means at each stage of your process.")

    band(p, "Key question: for each equipment type, what must always be known before an engineer "
            "can confidently prepare (a) a budgetary quotation, (b) a draft specification, and "
            "(c) a final release for manufacture?")

    body(p, "The distinction matters because these three stages have genuinely different "
            "thresholds. A budgetary figure can rest on assumptions that a manufacturing release "
            "cannot. A table to complete, one per equipment type, is provided in the appendix.")

    h2(p, "Three supporting questions")
    bullet(p, "Which values, if a customer gets them wrong or changes them later, force the "
              "design to be redone? These are the ones worth asking about first.")
    bullet(p, "Which questions can be skipped because the answer can be inferred from the "
              "application? For example, does 'for our paint shop' already tell an engineer "
              "enough about the contaminant to proceed?")
    bullet(p, "Which values must never be assumed, and must always be confirmed by the customer "
              "in writing before release?")

    h2(p, "A worked example of what we are asking for")
    body(p, "If a customer says only 'we need a wet scrubber for our paint shop', an experienced "
            "engineer would not produce a specification. They would ask two or three questions, "
            "and assume the rest from experience while stating those assumptions.")
    body(p, "We would like to know which two or three questions your engineers would ask first, "
            "and which values they would assume rather than ask about. The same answer for each "
            "equipment type would let the platform behave the same way.")


# --------------------------------------------------------------- part 4 ----

def part4(p: Doc):
    p.add_page()
    h1(p, "Practical notes", "PART 4")

    h2(p, "Formats")
    body(p, "Native formats are preferred throughout, because they carry information that print "
            "formats lose:")
    w = [avail(p) * 0.34, avail(p) * 0.32, avail(p) * 0.34]
    table(p, w,
          ["Material", "Preferred", "Also usable"],
          [["Calculations", "Excel with formulas intact", "PDF, scan, photograph"],
           ["Drawings", "DWG or DXF", "PDF, image"],
           ["Specifications and quotations", "Word or Excel", "PDF, scan"],
           ["BOMs", "Excel", "PDF, scan"],
           ["Standards and catalogues", "PDF", "Scan, printed copy"],
           ["Engineering rules", "Any written note", "Recorded conversation, email"]])
    note(p, "An Excel sheet with its formulas intact is far more valuable than the same sheet "
            "printed to PDF, because the formula itself is the engineering.")

    h2(p, "Quantity")
    body(p, "More is better, but do not let volume delay a response. One complete project chain, "
            "or a single clean calculation sheet, can be put to use immediately. The Part 2 items "
            "in particular are mostly small and individually unblock specific features.")

    h2(p, "Confidentiality and handling")
    bullet(p, "All material is used solely to build and validate the Vitech platform.")
    bullet(p, "Nothing is shared with any third party, and nothing is used for any other client.")
    bullet(p, "Customer names and commercial values may be redacted where you prefer. Engineering "
              "content is what matters; a specification with the customer name removed is almost "
              "as useful as one with it.")
    bullet(p, "The platform runs on infrastructure under your control, and customer requirement "
              "text is not written into application logs.")
    bullet(p, "We are happy to sign a non-disclosure agreement before anything is transferred.")

    h2(p, "What we do not need")
    bullet(p, "Financial accounts, payroll, or supplier commercial terms.")
    bullet(p, "Customer contact details or correspondence.")
    bullet(p, "Anything under a customer confidentiality obligation you cannot discharge.")

    h2(p, "Suggested next step")
    body(p, "A short working session with one senior application engineer and one design engineer "
            "would likely produce more than a long document exchange - particularly for Part 1 "
            "item 3 and Part 3, where the knowledge is experience rather than paperwork. One hour "
            "with the right person is often enough.")


# ------------------------------------------------------------- appendix ----

def appendix(p: Doc):
    p.add_page()
    h1(p, "Checklist", "APPENDIX A")
    body(p, "For working through and returning. Partial is fine - please send items as they "
            "become available rather than holding a complete set.")

    h2(p, "Part 1 - Engineering assets")
    checklist(p, [
        "Complete equipment list, with variants and current sales status",
        "Customer requirement / enquiry forms (any format, including superseded versions)",
        "Design calculation sheets (Excel with formulas preferred)",
        "Engineering rules and design judgement (written notes or a recorded discussion)",
        "Default assumptions table (Part 1, item 4)",
        "Standard specifications, per equipment type",
        "Quotations as issued to customers",
        "Bills of material, costed where possible",
        "GA drawings (DWG or DXF preferred)",
        "Standards followed, with clause or value where known",
        "Document templates",
        "Completed project sets: requirement, specification, drawing, BOM, quotation, revisions",
    ])

    h2(p, "Part 2 - Specific open items")
    checklist(p, [
        "B1. Powder Coating Plant calculations",
        "B1. Pollution Control Equipment calculations",
        "B2. Face velocity - confirm 0.45 m/s or supply Vitech's value per booth type",
        "B2. Air changes per hour for drying room / oven",
        "B3. Complete costed BOM for the paint spray booth (uncropped)",
        "B4. One quotation as actually issued to a customer",
        "B5. Height rule for horizontal baffle wet scrubbers",
        "B6. Component setting-out rules",
        "B7. Reference documents for the knowledge base",
        "B8. Additional offers: water-wash booths, powder coating plants, ovens (incl. LPG)",
        "B9. Margin policy and bought-out mark-up",
    ])

    h2(p, "Part 3 - Readiness questions")
    checklist(p, [
        "Required information per equipment, per stage (budgetary / draft / release)",
        "Values that force a redesign if they change",
        "Questions that can be skipped because the answer is inferable",
        "Values that must always be confirmed in writing before release",
    ])

    p.add_page()
    h1(p, "Forms to complete", "APPENDIX B")

    h2(p, "B-1. Default assumptions")
    body(p, "The value your engineers assume when the customer cannot supply one, and what "
            "would make them change it. Partial answers are welcome - please leave a row blank "
            "rather than guessing.")
    w = [avail(p) * 0.30, avail(p) * 0.14, avail(p) * 0.24, avail(p) * 0.32]
    table(p, w,
          ["Parameter", "Unit", "Default assumed", "When does it change"],
          [["Face velocity (per booth type)", "m/s", "", ""],
           ["Air changes per hour (oven / drying room)", "ACH", "", ""],
           ["Ambient / inlet temperature", "deg C", "", ""],
           ["Transfer efficiency / overspray", "%", "", ""],
           ["Design safety factor", "-", "", ""],
           ["Removal efficiency (scrubber)", "%", "", ""],
           ["Filter media velocity", "m/s", "", ""],
           ["Duct transport velocity", "m/s", "", ""],
           ["Electrical supply", "V/ph/Hz", "", ""],
           ["Installation (indoor / outdoor)", "-", "", ""]])

    h2(p, "B-2. Required information by stage")
    body(p, "One table per equipment type. For each item of information, mark whether it is "
            "REQUIRED, may be ASSUMED, or is NOT NEEDED at that stage.")
    p.set_font("Helvetica", "B", 9)
    p.set_text_color(*INK)
    p.cell(0, 5.4, _t("Equipment type: ......................................................"),
           new_x="LMARGIN", new_y="NEXT")
    p.ln(2)
    w = [avail(p) * 0.34, avail(p) * 0.22, avail(p) * 0.22, avail(p) * 0.22]
    table(p, w,
          ["Information required from the customer", "Budgetary quotation",
           "Draft specification", "Manufacturing release"],
          [["", "", "", ""] for _ in range(9)])

    p.ln(2)
    p.set_draw_color(*RULE)
    p.line(p.l_margin, p.get_y(), p.w - p.r_margin, p.get_y())
    p.ln(5)
    h2(p, "Return to")
    body(p, f"{SENDER['contact']}")
    body(p, "Please raise any question about a specific item rather than omitting it - in most "
            "cases a partial or informal answer is still directly usable.")


def build(path: str = "docs/Vitech_Engineering_Knowledge_Request.pdf"):
    p = Doc(orientation="P", unit="mm", format="A4")
    p.set_auto_page_break(auto=True, margin=18)
    p.set_margins(18, 22, 18)
    p.set_title(_t(TITLE))
    p.set_author(_t(SENDER["company"]))
    p.set_subject(_t(SUBTITLE))
    cover(p)
    part1(p)
    part2(p)
    part3(p)
    part4(p)
    appendix(p)
    p.output(path)
    return path, p.page_no()


if __name__ == "__main__":
    out, pages = build()
    print(f"wrote {out}  ({pages} pages)")
