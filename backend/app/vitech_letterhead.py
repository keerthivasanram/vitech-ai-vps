"""Shared Vitech Enviro Systems letterhead for generated PDFs.

Reproduces the company's official data-sheet stationery (logo header, green
footer band with office/factory/contact details, and the vertical tagline
banner) so generated specifications and quotations carry the same branding as
the hand-issued Vitech data sheets. Header/footer are drawn on every page.
"""
from pathlib import Path

from fpdf.enums import MethodReturnValue, XPos, YPos

LOGO_PATH = Path(__file__).with_name("assets") / "logo.png"
LOGO_W = 34.0                      # mm; logo is 245x79 px -> ~10.9mm tall
LOGO_H = LOGO_W * 79 / 245

# Brand colours sampled from the official logo / stationery.
GREEN = (81, 146, 88)
GREEN_DARK = (46, 105, 55)
DARKTEXT = (34, 40, 34)
GREY = (100, 116, 139)
WHITE = (255, 255, 255)

COMPANY = "VITECH ENVIRO SYSTEMS PVT. LTD"
HEADER_ADDR = "AP-123, AF-BLOCK, 6th STREET, 11th MAIN ROAD, ANNA NAGAR, CHENNAI-600 040"
TAGLINE = "LET US MAKE THE EARTH A CLEANER AND SAFER PLACE TO LIVE"

OFFICE = ("Office: AP 123 AF Block, 6 Street, 11 Main Road, Anna Nagar, "
          "Chennai - 600 040, TN, India.")
FACTORY = ("Factory: Survey No 28/3 29/1, Puduvoyal-Arani Road, Vadakanallur Village, "
           "Ponneri Taluk, Thiruvallur District - 601 206, TN, India.")
TEL = ("Tel: +91-44-2628 0288, 4217 0487, "
       "Mobile: +91-9444057133 / +91-9444057131")
EMAIL = "E-mail: sales@vitechindia.com / mktg@vitechindia.com"

# Administration / contact persons (as on the official data sheets).
CONTACTS = [
    ("Mr. B. MAGESWARAN", "Sales Head", "+91-9444057133"),
    ("Mr. D.SAM MOHAN", "Business Development Manager", "+91-9444057131"),
]

# Layout constants shared with the PDF page setup.
TOP_MARGIN = 6.0
BODY_TOP = 30.0        # where body content begins, below the header block
BOTTOM_MARGIN = 28.0   # keeps content clear of the footer band
BANNER_W = 6.5         # vertical tagline banner width (right edge)

_MAP = {"–": "-", "—": "-", "•": "*", "→": "->", "₹": "INR ", "×": "x",
        "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "≈": "~"}


def lat(s) -> str:
    """Sanitise to latin-1 (core PDF fonts are latin-1 only)."""
    s = str(s if s is not None else "")
    for a, b in _MAP.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def measure_h(pdf, w, text, size, style="", family="Helvetica", line_h=5.5):
    """Height a wrapping cell will occupy, without drawing it."""
    pdf.set_font(family, style, size)
    lines = pdf.multi_cell(w, line_h, lat(text), dry_run=True,
                           output=MethodReturnValue.LINES)
    return max(1, len(lines)) * line_h


def ensure_space(pdf, need):
    """Start a new page if `need` mm won't fit above the footer band."""
    if pdf.get_y() + need > pdf.h - BOTTOM_MARGIN:
        pdf.add_page()


def draw_header(pdf):
    """Logo + company name + address + green rule (top of every page)."""
    lm = pdf.l_margin
    if LOGO_PATH.exists():
        pdf.image(str(LOGO_PATH), x=lm, y=TOP_MARGIN + 1, w=LOGO_W, h=LOGO_H)
    text_x = lm + LOGO_W + 5
    text_w = pdf.w - pdf.r_margin - text_x
    pdf.set_xy(text_x, TOP_MARGIN + 1)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*DARKTEXT)
    pdf.cell(text_w, 7, lat(COMPANY), align="R",
             new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_x(text_x)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*GREEN_DARK)
    pdf.multi_cell(text_w, 4, lat(HEADER_ADDR), align="R")

    y = max(pdf.get_y(), TOP_MARGIN + LOGO_H + 1) + 1.5
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.7)
    pdf.line(lm, y, pdf.w - pdf.r_margin, y)
    pdf.set_line_width(0.2)
    pdf.set_xy(lm, BODY_TOP)


def draw_side_banner(pdf):
    """Vertical green tagline banner down the right edge."""
    x = pdf.w - BANNER_W
    top = BODY_TOP
    bottom = pdf.h - BOTTOM_MARGIN
    pdf.set_fill_color(*GREEN)
    pdf.rect(x, top, BANNER_W, bottom - top, style="F")
    cy = (top + bottom) / 2
    with pdf.rotation(90, x + BANNER_W / 2, cy):
        pdf.set_xy(x + BANNER_W / 2 - (bottom - top) / 2, cy - 2.2)
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(bottom - top, 4.4, lat('" ' + TAGLINE), align="C")
    pdf.set_xy(pdf.l_margin, BODY_TOP)


def draw_footer(pdf):
    """Green address band across the bottom of every page."""
    band_h = 22.0
    y = pdf.h - band_h
    lm = pdf.l_margin
    w = pdf.w - lm - pdf.r_margin
    pdf.set_fill_color(*GREEN)
    pdf.rect(0, y, pdf.w, band_h, style="F")
    pdf.set_text_color(*WHITE)
    pdf.set_xy(lm, y + 2.2)
    pdf.set_font("Helvetica", "B", 7)
    pdf.multi_cell(w, 3.5, lat(OFFICE), align="L")
    pdf.set_x(lm)
    pdf.set_font("Helvetica", "", 6.6)
    pdf.multi_cell(w, 3.3, lat(FACTORY), align="L")
    pdf.set_x(lm)
    pdf.multi_cell(w, 3.3, lat(TEL), align="L")
    pdf.set_x(lm)
    pdf.set_font("Helvetica", "B", 6.8)
    pdf.multi_cell(w, 3.3, lat(EMAIL), align="L")

    # page number, discreetly, above the band
    pdf.set_xy(lm, y - 4.5)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*GREY)
    pdf.cell(w, 4, f"Page {pdf.page_no()}", align="R")


def contacts_block(pdf, usable, heading_fn):
    """Render the administration / contact-persons block."""
    ensure_space(pdf, 14 + 6 * len(CONTACTS))
    heading_fn(pdf, "For any assistance, please contact")
    for name, role, phone in CONTACTS:
        x, y0 = pdf.l_margin, pdf.get_y()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*DARKTEXT)
        pdf.set_xy(x, y0)
        pdf.cell(60, 5.5, lat(name), new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY)
        pdf.cell(usable - 60 - 40, 5.5, lat(role), new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*DARKTEXT)
        pdf.cell(40, 5.5, lat(phone), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def apply_page_setup(pdf):
    """Common margins/page-break setup so header/footer have room."""
    pdf.set_auto_page_break(True, margin=BOTTOM_MARGIN)
    pdf.set_margins(15, TOP_MARGIN, 15 + BANNER_W)
