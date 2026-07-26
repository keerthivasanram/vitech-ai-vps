"""Render a quotation object to a Vitech-format PDF (fpdf2, no system deps).

The PDF is a faithful print of the deterministic quotation object built by
`quotation.build_quotation` — it adds no numbers of its own. Core PDF fonts are
latin-1 only, so text is sanitised to ASCII-safe glyphs and prices are written
"INR 25,50,000" (Indian grouping) rather than with a rupee symbol. The page
carries the official Vitech letterhead (see `vitech_letterhead`).

Layout follows the **house document style** of Vitech's own data sheets: a
centred underlined title, numbered "1.0 / 2.0" underlined section headings,
"Label : Value" rows with an aligned colon column, bordered grid tables, and
the closing "For any assistance..." contact note. Customer-facing, so it shows
no confidence score, margin, cost break-up or market band — same stance as
`quotation.render_quotation_markdown`.
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from . import vitech_letterhead as lh
from .quotation import COMMERCIAL_NOTES, SCOPE_EXCLUSIONS, STANDARD_ASSUMPTIONS

NAVY = lh.GREEN_DARK
ACCENT = lh.GREEN
LIGHT = (233, 245, 238)
GREY = lh.GREY
TEXT = (15, 23, 42)
LINE = (210, 216, 228)

_lat = lh.lat


def _inr(n) -> str:
    """Indian-grouped rupee amount, e.g. 2550000 -> 'INR 25,50,000'."""
    n = int(round(n or 0))
    neg, s = n < 0, str(abs(n))
    if len(s) <= 3:
        grp = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grp = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "INR " + grp


class _QPDF(FPDF):
    def header(self):
        lh.draw_header(self)
        lh.draw_side_banner(self)

    def footer(self):
        lh.draw_footer(self)


def _title(pdf, text):
    """Centred, bold, underlined document title - as on the Vitech data sheets."""
    pdf.set_font("Helvetica", "BU", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 9, _lat(text.upper()), align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)


class _Sections:
    """Hands out 1.0, 2.0, 3.0 ... so conditional sections stay consecutive."""

    def __init__(self):
        self.n = 0

    def __call__(self, pdf, text):
        self.n += 1
        lh.ensure_space(pdf, 18)
        pdf.ln(3)
        pdf.set_font("Helvetica", "BU", 10)
        pdf.set_text_color(*TEXT)
        pdf.cell(0, 6, _lat(f"{self.n}.0 {text.upper()}:"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)


def _field(pdf, label, value, lw=58, bold=False, h=5.2):
    """A "Label : Value" row with the colon in its own aligned column."""
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    vw = usable - lw - 4
    rh = max(lh.measure_h(pdf, lw, label, 9, line_h=h),
             lh.measure_h(pdf, vw, value, 9, style="B" if bold else "", line_h=h))
    lh.ensure_space(pdf, rh + 1.5)
    x, y0 = pdf.l_margin, pdf.get_y()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*TEXT)
    pdf.set_xy(x, y0)
    pdf.multi_cell(lw, h, _lat(label), align="L")
    y1 = pdf.get_y()

    pdf.set_xy(x + lw, y0)
    pdf.cell(4, h, ":", new_x=XPos.RIGHT, new_y=YPos.TOP)

    pdf.set_font("Helvetica", "B" if bold else "", 9)
    pdf.set_text_color(*TEXT if bold else GREY)
    pdf.set_xy(x + lw + 4, y0)
    pdf.multi_cell(vw, h, _lat(value), align="L")
    pdf.set_xy(pdf.l_margin, max(y1, pdf.get_y()) + 1.0)


def _grid_row(pdf, widths, cells, *, bold=False, fill=None, aligns=None, h=5.0):
    """One bordered table row; every cell wraps and the row never splits."""
    aligns = aligns or ["L"] * len(cells)
    style = "B" if bold else ""
    rh = max(lh.measure_h(pdf, w - 3, str(c), 8.5, style=style, line_h=h)
             for w, c in zip(widths, cells))
    rh = max(rh, h + 1)
    lh.ensure_space(pdf, rh + 1)

    x0, y0 = pdf.l_margin, pdf.get_y()
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    x = x0
    for w, c, al in zip(widths, cells, aligns):
        if fill:
            pdf.set_fill_color(*fill)
            pdf.rect(x, y0, w, rh, style="FD")
        else:
            pdf.rect(x, y0, w, rh, style="D")
        pdf.set_font("Helvetica", style, 8.5)
        pdf.set_text_color(*(TEXT if (bold or fill) else GREY))
        pdf.set_xy(x + 1.5, y0 + 0.8)
        pdf.multi_cell(w - 3, h, _lat(str(c)), align=al)
        x += w
    pdf.set_xy(x0, y0 + rh)


def _bullets(pdf, items):
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "", 8.8)
    pdf.set_text_color(*GREY)
    for it in items:
        rh = lh.measure_h(pdf, usable - 6, it, 8.8, line_h=4.6)
        lh.ensure_space(pdf, rh + 1)
        y0 = pdf.get_y()
        pdf.set_xy(pdf.l_margin, y0)
        pdf.cell(6, 4.6, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_xy(pdf.l_margin + 6, y0)
        pdf.multi_cell(usable - 6, 4.6, _lat(it), align="L")
        pdf.set_x(pdf.l_margin)


def render_quotation_pdf(quote: dict) -> bytes:
    q = quote or {}
    price = q.get("price") or {}
    pdf = _QPDF(format="A4")
    lh.apply_page_setup(pdf)
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    section = _Sections()

    # ---- title ----
    _title(pdf, "Budgetary Quotation")

    # ---- 1.0 customer / offer particulars (data-sheet field block) ----
    section(pdf, "Offer particulars")
    _field(pdf, "Quotation Ref", q.get("ref", "-"))
    _field(pdf, "Date", q.get("date", "-"))
    _field(pdf, "Company Name & Address", q.get("customer") or "(to be completed)")
    _field(pdf, "Contact Person & Designation", q.get("attention") or "(to be completed)")
    _field(pdf, "Site Location", q.get("location") or "(to be completed)")
    _field(pdf, "Equipment", q.get("headline", q.get("category_label", "Equipment")), bold=True)
    _field(pdf, "Prepared by", "Applications Engineering Department")
    _field(pdf, "Status", "DRAFT - for engineer review before issue")

    # ---- 2.0 requirement as received ----
    given = q.get("given_data") or []
    if given:
        section(pdf, "Requirement as received")
        for g in given:
            _field(pdf, g.get("label", ""), g.get("value", ""))

    # ---- 3.0 technical scope (exclude requirement-echo rows) ----
    scope = [s for s in (q.get("scope") or []) if s.get("origin") != "given"]
    if scope:
        section(pdf, "Technical scope of supply")
        w = [12.0, 68.0, usable - 80.0]
        _grid_row(pdf, w, ["SL.\nNo", "Description", "Specification"],
                  bold=True, fill=LIGHT, aligns=["C", "L", "L"])
        for i, s in enumerate(scope, 1):
            _grid_row(pdf, w, [i, s.get("item", ""), s.get("spec", "")],
                      aligns=["C", "L", "L"])

    # ---- 4.0 price schedule (bordered grid, no confidence: customer-facing) ----
    section(pdf, "Price schedule")
    qty = price.get("qty", 1) or 1
    w = [12.0, usable - 92.0, 18.0, 31.0, 31.0]
    _grid_row(pdf, w, ["SL.\nNo", "Description", "Qty", "Unit Price", "Amount"],
              bold=True, fill=LIGHT, aligns=["C", "L", "C", "R", "R"])
    _grid_row(pdf, w, [1, q.get("headline", "System"), f"{qty} nos",
                       _inr(price.get("unit_price")), _inr(price.get("amount"))],
              aligns=["C", "L", "C", "R", "R"])
    _grid_row(pdf, w, ["", "TOTAL (Ex-Works)", "", "", _inr(price.get("amount"))],
              bold=True, fill=LIGHT, aligns=["C", "R", "C", "R", "R"])
    pdf.ln(1.5)
    _field(pdf, "Indicative range",
           f"{_inr(price.get('range_low'))}  to  {_inr(price.get('range_high'))}")
    if price.get("currency") and price["currency"] != "INR":
        _field(pdf, "Currency", price["currency"])
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(usable, 4.5, _lat("Budgetary estimate - expected variation +/-15%. "
                                     "Prices are Ex-Works; GST extra as applicable."))

    # ---- 5.0 scope exclusions ----
    section(pdf, "Scope exclusions")
    _bullets(pdf, SCOPE_EXCLUSIONS)

    # ---- 6.0 commercial terms ----
    terms = q.get("terms") or []
    if terms:
        section(pdf, "Commercial terms")
        for t in terms:
            _field(pdf, t[0] if len(t) > 0 else "", t[1] if len(t) > 1 else "", lw=40)

    # ---- 7.0 commercial notes & assumptions ----
    section(pdf, "Notes and assumptions")
    _bullets(pdf, list(COMMERCIAL_NOTES) + list(STANDARD_ASSUMPTIONS))

    # ---- administration / contacts (data-sheet closing note) ----
    lh.contacts_block(pdf, usable, lambda p, t: section(p, t))

    # ---- basis + disclaimer ----
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY)
    basis = q.get("basis_offers") or []
    if basis:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(usable, 4.5, _lat("Priced from historical offers: " + ", ".join(basis)))
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(usable, 4.5, _lat(q.get("note",
                   "Budgetary estimate from historical offers - engineer to confirm.")))

    out = pdf.output()  # fpdf2 2.8 returns a bytearray
    return bytes(out) if isinstance(out, (bytearray, memoryview)) else out


if __name__ == "__main__":  # quick manual render for eyeballing
    sample = {
        "ref": "Q-TEST-DRAFT", "date": "02 Jul 2026",
        "headline": "Wet Scrubber - 800 CFM x 4", "category_label": "Wet Scrubber",
        "given_data": [{"label": "Air volume", "value": "800 CFM"},
                       {"label": "Tower diameter", "value": "750 mm"},
                       {"label": "Quantity", "value": "4"}],
        "scope": [{"item": "Chamber", "spec": "SS-304 2mm", "origin": "reused"},
                  {"item": "Spray nozzles", "spec": "17 nos SS-304", "origin": "rule"},
                  {"item": "Air volume", "spec": "800 CFM", "origin": "given"}],
        "price": {"amount": 2550000, "unit_price": 635000, "qty": 4,
                  "range_low": 2175000, "range_high": 2925000, "currency": "INR"},
        "terms": [["Prices", "Ex-works; GST extra as applicable."],
                  ["Validity", "30 days from date of offer."]],
        "confidence_pct": 75, "confidence_label": "Medium",
        "basis_offers": ["OFF-C2C-WS-178", "OFF-C2C-WS-20240921R1"],
        "note": "Budgetary draft - for engineer review before issue.",
    }
    with open("_sample_quote.pdf", "wb") as f:
        f.write(render_quotation_pdf(sample))
    print("wrote _sample_quote.pdf")
