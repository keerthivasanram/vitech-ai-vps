"""Non-SVG exports of a GA sheet: DXF (CAD) and PDF (print).

The SVG stays the SOURCE OF TRUTH. Both exporters consume the very same
`Canvas` shape list the SVG is emitted from — they never re-derive geometry —
so a drawing opened in AutoCAD, printed to PDF, or shown in the studio is the
same drawing. That is the drafting-room version of the rule that keeps geometry
in exactly one place (golden rule #2).

DXF is hand-rolled rather than taken from `ezdxf`: the primitives are only
lines, circles, polylines and text, which R12 ASCII expresses directly, so a
dependency would buy nothing and add a wheel to every deployment. Polygons are
written as their constituent LINEs, which every CAD package reads without
relying on R2000 entities.
"""
from .primitives import (DASH_CENTRE, DASH_HIDDEN, Canvas, Circle, Line, Path,
                         Rect, Text)

# --------------------------------------------------------------------------
# DXF
# --------------------------------------------------------------------------
# One DXF linetype per dash pattern the engine uses, so hidden and centre lines
# stay hidden and centre lines in CAD instead of flattening to solid.
_LTYPE = {None: "CONTINUOUS", DASH_HIDDEN: "DASHED", DASH_CENTRE: "CENTER"}

# ACI colours per layer, so a CAD user sees the same separation the studio's
# layer toggles give. 7 = black/white (follows the drawing background).
_ACI = {"border": 8, "outline": 7, "hidden": 8, "centre": 4,
        "component": 3, "dimension": 1, "text": 7, "title": 7}


def _tag(code: int, value) -> str:
    return f"{code}\n{value}\n"


def _seg(layer: str, ltype: str, x1: float, y1: float, x2: float, y2: float) -> str:
    return ("0\nLINE\n" + _tag(8, layer) + _tag(6, ltype)
            + _tag(10, f"{x1:.4f}") + _tag(20, f"{y1:.4f}") + _tag(30, "0")
            + _tag(11, f"{x2:.4f}") + _tag(21, f"{y2:.4f}") + _tag(31, "0"))


def to_dxf(canvas: Canvas) -> str:
    """The sheet as DXF R12 ASCII, in millimetres.

    DXF has +y UP while the sheet model has +y DOWN (SVG convention), so every
    ordinate is flipped about the sheet height. Getting this wrong mirrors the
    drawing, which is why it happens in exactly one place.
    """
    H = canvas.h

    def fy(y: float) -> float:
        return H - y

    out = [
        "0\nSECTION\n" + _tag(2, "HEADER")
        + _tag(9, "$INSUNITS") + _tag(70, 4)          # 4 = millimetres
        + _tag(9, "$EXTMIN") + _tag(10, "0") + _tag(20, "0") + _tag(30, "0")
        + _tag(9, "$EXTMAX") + _tag(10, f"{canvas.w:.4f}")
        + _tag(20, f"{H:.4f}") + _tag(30, "0")
        + "0\nENDSEC\n",
    ]

    # TABLES: the linetypes and layers the entities reference.
    tables = ["0\nSECTION\n" + _tag(2, "TABLES")]
    tables.append("0\nTABLE\n" + _tag(2, "LTYPE") + _tag(70, 3))
    tables.append("0\nLTYPE\n" + _tag(2, "CONTINUOUS") + _tag(70, 0)
                  + _tag(3, "Solid line") + _tag(72, 65) + _tag(73, 0) + _tag(40, "0"))
    tables.append("0\nLTYPE\n" + _tag(2, "DASHED") + _tag(70, 0)
                  + _tag(3, "Dashed __ __ __") + _tag(72, 65) + _tag(73, 2)
                  + _tag(40, "3.5") + _tag(49, "2.0") + _tag(49, "-1.5"))
    tables.append("0\nLTYPE\n" + _tag(2, "CENTER") + _tag(70, 0)
                  + _tag(3, "Centre ____ _ ____") + _tag(72, 65) + _tag(73, 4)
                  + _tag(40, "10.5") + _tag(49, "6.0") + _tag(49, "-1.5")
                  + _tag(49, "1.5") + _tag(49, "-1.5"))
    tables.append("0\nENDTAB\n")

    layers = canvas.layers_present()
    tables.append("0\nTABLE\n" + _tag(2, "LAYER") + _tag(70, len(layers)))
    for lay in layers:
        tables.append("0\nLAYER\n" + _tag(2, lay) + _tag(70, 0)
                      + _tag(62, _ACI.get(lay, 7)) + _tag(6, "CONTINUOUS"))
    tables.append("0\nENDTAB\n0\nENDSEC\n")
    out += tables

    ents = ["0\nSECTION\n" + _tag(2, "ENTITIES")]
    for s in canvas.shapes:
        lay = s.layer
        lt = _LTYPE.get(getattr(s, "dash", None), "CONTINUOUS")
        if isinstance(s, Line):
            ents.append(_seg(lay, lt, s.x1, fy(s.y1), s.x2, fy(s.y2)))
        elif isinstance(s, Rect):
            x0, y0, x1, y1 = s.x, fy(s.y), s.x + s.w, fy(s.y + s.h)
            ents.append(_seg(lay, lt, x0, y0, x1, y0))
            ents.append(_seg(lay, lt, x1, y0, x1, y1))
            ents.append(_seg(lay, lt, x1, y1, x0, y1))
            ents.append(_seg(lay, lt, x0, y1, x0, y0))
        elif isinstance(s, Circle):
            ents.append("0\nCIRCLE\n" + _tag(8, lay) + _tag(6, lt)
                        + _tag(10, f"{s.cx:.4f}") + _tag(20, f"{fy(s.cy):.4f}")
                        + _tag(30, "0") + _tag(40, f"{s.r:.4f}"))
        elif isinstance(s, Path):
            pts = list(s.pts)
            if len(pts) < 2:
                continue
            ring = pts + [pts[0]] if s.closed else pts
            for (ax, ay), (bx, by) in zip(ring, ring[1:]):
                ents.append(_seg(lay, lt, ax, fy(ay), bx, fy(by)))
        elif isinstance(s, Text):
            halign = {"start": 0, "middle": 1, "end": 2}.get(s.anchor, 0)
            # SVG rotates clockwise, DXF counter-clockwise.
            ents.append(
                "0\nTEXT\n" + _tag(8, lay) + _tag(6, "CONTINUOUS")
                + _tag(10, f"{s.x:.4f}") + _tag(20, f"{fy(s.y):.4f}") + _tag(30, "0")
                + _tag(40, f"{s.size:.4f}") + _tag(1, _ascii(s.text))
                + _tag(50, f"{-s.rotate:.4f}") + _tag(72, halign)
                # When the alignment is not left, DXF takes the position from
                # the SECOND alignment point (11/21), not from 10/20.
                + _tag(11, f"{s.x:.4f}") + _tag(21, f"{fy(s.y):.4f}") + _tag(31, "0"))
    ents.append("0\nENDSEC\n0\nEOF\n")
    out += ents
    return "".join(out)


def _ascii(text) -> str:
    """DXF R12 is byte-oriented; keep the text to characters CAD reads back."""
    return (str(text).replace("—", "-").replace("–", "-")
            .replace("‘", "'").replace("’", "'")
            .replace("“", '"').replace("”", '"')
            .encode("ascii", "replace").decode("ascii"))


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
# The GA sheet carries its own title block, which IS the drawing's identity, so
# the PDF is the sheet at true size — no letterhead. A GA printed inside the
# marketing stationery would be the wrong document.
def to_pdf(canvas: Canvas) -> bytes:
    """The sheet as a single-page, true-size, vector PDF."""
    from fpdf import FPDF

    # orientation stays "P": fpdf2 SWAPS an explicit (w, h) format when told
    # "L", which turned a 420x297 landscape sheet into a 297x420 portrait one.
    # The format tuple already states the true sheet size.
    pdf = FPDF(orientation="P", unit="mm", format=(canvas.w, canvas.h))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.add_page()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(0, 0, 0)

    dash: tuple = ()

    def use_dash(pattern):
        """Dash state is a document-level setting in fpdf2, so it is only
        touched when it actually changes — otherwise a solid line inherits the
        previous shape's dashes."""
        nonlocal dash
        want = _dash_mm(pattern)
        if want != dash:
            if want:
                pdf.set_dash_pattern(dash=want[0], gap=want[1])
            else:
                pdf.set_dash_pattern()
            dash = want

    for s in canvas.shapes:
        if isinstance(s, Text):
            continue                       # text is drawn after the geometry
        pdf.set_line_width(max(getattr(s, "width", 0.2), 0.05))
        use_dash(getattr(s, "dash", None))
        if isinstance(s, Line):
            pdf.line(s.x1, s.y1, s.x2, s.y2)
        elif isinstance(s, Rect):
            pdf.rect(s.x, s.y, s.w, s.h, style="D")
        elif isinstance(s, Circle):
            # fpdf2 >= 2.5.6 takes CENTRE + RADIUS. The legacy signature was
            # top-left of the bounding box + diameter; using it drew every
            # balloon at twice size, offset up and left.
            pdf.circle(s.cx, s.cy, s.r, style="D")
        elif isinstance(s, Path):
            pts = list(s.pts)
            if len(pts) < 2:
                continue
            filled = s.fill not in ("none", "", None)
            if s.closed and len(pts) >= 3:
                pdf.polygon(pts, style="DF" if filled else "D")
            else:
                for a, b in zip(pts, pts[1:]):
                    pdf.line(a[0], a[1], b[0], b[1])

    use_dash(None)
    pdf.set_font("Helvetica", "", 8)
    for s in canvas.shapes:
        if not isinstance(s, Text):
            continue
        pdf.set_font("Helvetica", "B" if s.bold else "", _pt(s.size))
        txt = _latin1(s.text)
        w = pdf.get_string_width(txt)
        dx = {"start": 0.0, "middle": -w / 2.0, "end": -w}.get(s.anchor, 0.0)
        if s.rotate:
            # fpdf2 rotates counter-clockwise; SVG's rotate() is clockwise.
            with pdf.rotation(-s.rotate, s.x, s.y):
                pdf.text(s.x + dx, s.y, txt)
        else:
            pdf.text(s.x + dx, s.y, txt)

    return bytes(pdf.output())


def _dash_mm(pattern):
    """An SVG stroke-dasharray -> the (dash, gap) fpdf2 takes."""
    if not pattern:
        return ()
    parts = [p for p in str(pattern).replace(",", " ").split() if p]
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return ()
    if not vals:
        return ()
    return (vals[0], vals[1] if len(vals) > 1 else vals[0])


def _pt(size_mm: float) -> float:
    """Text height in sheet mm -> font size in points."""
    return round(size_mm * 72.0 / 25.4, 2)


def _latin1(text) -> str:
    """The core PDF fonts are latin-1; keep the sheet legible without shipping
    an embedded font just for a dash."""
    return (str(text).replace("—", "-").replace("–", "-")
            .encode("latin-1", "replace").decode("latin-1"))
