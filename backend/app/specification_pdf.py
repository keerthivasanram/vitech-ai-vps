"""Render an engineering specification to a Vitech-format PDF (fpdf2, no system deps).

A faithful print of the deterministic specification object built by
`/api/tools/spec` (generate_specification) — it adds no numbers of its own,
mirroring `quotation_pdf.py`. Core PDF fonts are latin-1 only, so text is
sanitised to ASCII-safe glyphs (see `_lat`).

Accepts either the structured spec payload:
    {category_label, confidence_pct, confidence_label, given_data[],
     technical_details[], missing_inputs[], sources[]}
or a bare {text: "..."} fallback, which is printed as-is.
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from . import vitech_letterhead as lh

NAVY = lh.GREEN_DARK
ACCENT = lh.GREEN
LIGHT = (233, 245, 238)
GREY = lh.GREY
TEXT = (15, 23, 42)
LINE = (210, 216, 228)

_lat = lh.lat


class _SPDF(FPDF):
    def header(self):
        lh.draw_header(self)
        lh.draw_side_banner(self)

    def footer(self):
        lh.draw_footer(self)


def _heading(pdf, text):
    lh.ensure_space(pdf, 20)
    pdf.ln(3)
    pdf.set_fill_color(*LIGHT)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(0, 7, _lat("  " + text.upper()), border=0, fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1.5)


def _row(pdf, cols, widths, bold_last=False, h=5.5):
    """A rule-bottomed row of N wrapping columns."""
    rh = max(lh.measure_h(pdf, w, t,
                          9, style="B" if (bold_last and i == len(cols) - 1) else "",
                          line_h=h)
             for i, (t, w) in enumerate(zip(cols, widths)))
    lh.ensure_space(pdf, rh + 2)
    x, y0 = pdf.l_margin, pdf.get_y()
    ymax = y0
    cx = x
    for i, (t, w) in enumerate(zip(cols, widths)):
        last = i == len(cols) - 1
        pdf.set_font("Helvetica", "B" if (bold_last and last) else "", 9)
        pdf.set_text_color(*(TEXT if last else GREY))
        pdf.set_xy(cx, y0)
        pdf.multi_cell(w, h, _lat(t), align="L")
        ymax = max(ymax, pdf.get_y())
        cx += w
    pdf.set_draw_color(*LINE)
    pdf.line(x, ymax + 0.6, x + sum(widths), ymax + 0.6)
    pdf.set_xy(x, ymax + 1.6)


def render_specification_pdf(spec: dict) -> bytes:
    s = spec or {}
    pdf = _SPDF(format="A4")
    lh.apply_page_setup(pdf)
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    # ---- title band + DRAFT + confidence ----
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*TEXT)
    pdf.cell(usable * 0.7, 8, _lat("ENGINEERING SPECIFICATION"),
             new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(217, 119, 6)
    pdf.cell(usable * 0.3, 8, _lat("DRAFT"), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, _lat(s.get("category_label") or "Equipment"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if s.get("confidence_pct") is not None:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 5, _lat(f"Confidence: {s.get('confidence_label', '-')} "
                            f"({s.get('confidence_pct')}%)"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ---- bare-text fallback (knowledge mode / no structured rows) ----
    given = s.get("given_data") or []
    tech = [t for t in (s.get("technical_details") or []) if t.get("source") != "requirement"]
    if not given and not tech:
        text = s.get("text") or s.get("spec_markdown") or "No specification content."
        pdf.ln(3)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*TEXT)
        for line in _lat(text).split("\n"):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(usable, 5.5, line)
        return _bytes(pdf)

    # ---- customer requirement ----
    if given:
        _heading(pdf, "Customer requirement")
        for g in given:
            _row(pdf, [g.get("label", ""), g.get("value", "")], [70, usable - 70])

    # ---- technical specification ----
    if tech:
        _heading(pdf, "Technical specification")
        # Basis / Calculation shows the derivation (formula for a calculated value,
        # or the offer a value was reused/scaled from) — wider column since it now
        # carries the full working, wrapping over multiple lines as needed.
        cols_w = [45, usable - 120, 75]
        _row(pdf, ["Parameter", "Value", "Basis / Calculation"], cols_w)
        for t in tech:
            basis = t.get("reason") or t.get("origin", "")
            _row(pdf, [t.get("label", ""), t.get("value", ""), basis], cols_w)

    # ---- to confirm ----
    miss = s.get("missing_inputs") or []
    if miss:
        _heading(pdf, "To confirm before detailed design")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(usable, 5.5, _lat(", ".join(str(m) for m in miss)))

    # ---- administration / contacts ----
    lh.contacts_block(pdf, usable, _heading)

    # ---- basis + disclaimer ----
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY)
    sources = s.get("sources") or []
    if sources:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(usable, 4.5,
                       _lat("Grounded in historical projects: " + ", ".join(str(x) for x in sources)))
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(usable, 4.5,
                   _lat("Engineer-reviewed draft - not a released design."))
    return _bytes(pdf)


def _bytes(pdf) -> bytes:
    out = pdf.output()  # fpdf2 2.8 returns a bytearray
    return bytes(out) if isinstance(out, (bytearray, memoryview)) else out


if __name__ == "__main__":  # quick manual render for eyeballing
    sample = {
        "category_label": "Wet Scrubber",
        "confidence_pct": 78, "confidence_label": "Medium",
        "given_data": [{"label": "Air volume", "value": "800 CFM"},
                       {"label": "Tower diameter", "value": "750 mm"},
                       {"label": "Quantity", "value": "4 nos"}],
        "technical_details": [
            {"label": "Chamber material", "value": "SS-304 2mm", "origin": "reused", "source": "engineered"},
            {"label": "Spray nozzles", "value": "17 nos SS-304", "origin": "rule", "source": "engineered"},
        ],
        "missing_inputs": ["Inlet dust load", "Operating temperature"],
        "sources": ["OFF-C2C-WS-178.pdf", "OFF-C2C-WS-20240921R1.pdf"],
    }
    with open("_sample_spec.pdf", "wb") as f:
        f.write(render_specification_pdf(sample))
    print("wrote _sample_spec.pdf")
