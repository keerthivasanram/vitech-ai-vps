"""The Vitech drawing title block.

Reuses the SAME company constants as the spec/quotation PDFs
(`vitech_letterhead`), so a GA drawing carries identical stationery to every
other document that leaves the building — one place to change the address.

Layout is a conventional bottom-right block: identity strip, then a grid of
drawn/checked/scale/size/date/revision cells, with the DRAFT status stated
explicitly because every output of this platform is an engineer-reviewed draft
(golden rule #3).
"""
from ..vitech_letterhead import COMPANY, HEADER_ADDR
from .primitives import (LW_MED, LW_THICK, LW_THIN, L_TITLE, Line, Rect, Text)
from .style import T_BODY, T_DIM, T_TINY, T_TITLE_MAIN, T_VIEW_TITLE

def _fit_size(text: str, avail_mm: float, base: float, bold: bool = False) -> float:
    """Largest size at or below `base` at which `text` fits `avail_mm`.

    The canvas cannot measure rendered text — it must stay deterministic and
    dependency-free — so this uses a per-character width ratio for the sheet's
    sans face. Bold is measurably wider, and ignoring that is what let an
    11-character bold status overflow a cell a 5-character one sat in happily.
    Floored at 1.5 mm: below that a title-block value stops being readable, and
    a value too long even for that is a content problem, not a layout one.

    THE RATIOS WERE MEASURED, NOT GUESSED. Rasterising the actual face gives
    0.69 per character for bold uppercase and 0.63-0.67 for regular; the first
    version of this guessed 0.62/0.55 and still overflowed, because a guess low
    by a tenth is a cell short by a millimetre. The values below carry a small
    margin over what was measured.
    """
    if not text:
        return base
    ratio = 0.75 if bold else 0.68
    return max(1.5, min(base, avail_mm / (len(text) * ratio)))


TB_W = 148.0        # title block width, mm
TB_H = 45.0         # title block height, mm (3 sign-off rows)

_ROW = 7.0


def draw(canvas, sheet_w: float, sheet_h: float, margin: float, info: dict) -> None:
    """Render the title block into the sheet's bottom-right corner.

    `info` keys (all optional, all rendered as given — this function invents
    nothing): title, client, ref, scale, size, date, drawn, checked, rev, units.
    """
    x = sheet_w - margin - TB_W
    y = sheet_h - margin - TB_H

    canvas.add(Rect(x, y, TB_W, TB_H, L_TITLE, LW_THICK))

    # --- identity strip ---------------------------------------------------
    canvas.add(Line(x, y + 12.0, x + TB_W, y + 12.0, L_TITLE, LW_MED))
    canvas.add(Text(x + 3.0, y + 5.6, COMPANY, L_TITLE, T_TITLE_MAIN, "start", bold=True))
    canvas.add(Text(x + 3.0, y + 10.0, HEADER_ADDR, L_TITLE, T_TINY, "start"))

    # --- drawing title ----------------------------------------------------
    canvas.add(Line(x, y + 22.0, x + TB_W, y + 22.0, L_TITLE, LW_MED))
    canvas.add(Text(x + 3.0, y + 16.4, "TITLE", L_TITLE, T_TINY, "start"))
    canvas.add(Text(x + 3.0, y + 20.6, str(info.get("title", "")).upper(),
                    L_TITLE, T_VIEW_TITLE, "start", bold=True))
    # The equipment's DUTY next to its name: a GA titled only "Wet Scrubber"
    # does not say which wet scrubber. The figure comes from the resolved
    # specification, so it is the same number the spec was engineered to.
    if info.get("duty"):
        canvas.add(Text(x + TB_W - 3.0, y + 20.6, str(info["duty"])[:34],
                        L_TITLE, T_BODY, "end"))

    # --- client / reference row -------------------------------------------
    canvas.add(Line(x, y + 29.0, x + TB_W, y + 29.0, L_TITLE, LW_THIN))
    canvas.add(Line(x + 88.0, y + 22.0, x + 88.0, y + TB_H, L_TITLE, LW_THIN))
    canvas.add(Text(x + 3.0, y + 25.4, "CLIENT", L_TITLE, T_TINY, "start"))
    canvas.add(Text(x + 22.0, y + 25.4, str(info.get("client", "")), L_TITLE, T_BODY, "start"))
    canvas.add(Text(x + 91.0, y + 25.4, "DRG No.", L_TITLE, T_TINY, "start"))
    canvas.add(Text(x + 110.0, y + 25.4, str(info.get("ref", "")), L_TITLE, T_BODY, "start"))

    # --- bottom cell grid -------------------------------------------------
    cells = [
        ("SCALE", info.get("scale", "")),
        ("SIZE", info.get("size", "")),
        ("UNITS", info.get("units", "mm")),
        ("DATE", info.get("date", "")),
    ]
    cw = 88.0 / len(cells)
    for i, (label, value) in enumerate(cells):
        cxx = x + i * cw
        if i:
            canvas.add(Line(cxx, y + 29.0, cxx, y + TB_H, L_TITLE, LW_THIN))
        canvas.add(Text(cxx + 2.0, y + 32.6, label, L_TITLE, T_TINY, "start"))
        canvas.add(Text(cxx + 2.0, y + 37.4, str(value), L_TITLE, T_BODY, "start", bold=True))

    # --- sign-off block: drawn / checked / approved, with rev and sheet ----
    # APPROVED is a real field on an industrial title block and its absence was
    # conspicuous. It is never filled in by this engine: approval is a person's
    # signature, the same reason `Released Design` is unreachable from code.
    canvas.add(Line(x + 122.0, y + 29.0, x + 122.0, y + TB_H, L_TITLE, LW_THIN))
    rows = [
        ("DRAWN", info.get("drawn", ""), "REV", info.get("rev", "0"), False),
        ("CHECKED", info.get("checked", "") or "DRAFT",
         "STATUS", info.get("status", "DRAFT"), True),
        ("APPROVED", info.get("approved", "") or "\u2014",
         "SHEET", info.get("sheet", "1 OF 1"), False),
    ]
    row_h = (TB_H - 29.0) / len(rows)
    for i, (lab, val, rlab, rval, bold) in enumerate(rows):
        ry = y + 29.0 + i * row_h
        if i:
            canvas.add(Line(x + 88.0, ry, x + TB_W, ry, L_TITLE, LW_THIN))
        canvas.add(Text(x + 91.0, ry + 2.6, lab, L_TITLE, T_TINY, "start"))
        canvas.add(Text(x + 110.0, ry + 2.6, str(val), L_TITLE, T_DIM, "start"))
        canvas.add(Text(x + 125.0, ry + 2.6, rlab, L_TITLE, T_TINY, "start"))
        # RIGHT-ALIGNED to the cell AND shrunk to fit it. Left-aligned from a
        # fixed 138 mm, a value had 10 mm before the frame, so the first status
        # longer than "DRAFT" — "PRELIMINARY" — printed through the border.
        # Right-aligning alone then pushed it left into its own "STATUS" label.
        # A title-block cell is a fixed box: the only correct answer is to fit
        # the text to the box, so any future status stays legible and inside.
        canvas.add(Text(x + TB_W - 2.0, ry + 2.6, str(rval), L_TITLE,
                        _fit_size(str(rval), 13.0, T_DIM, bold), "end",
                        bold=bold))
