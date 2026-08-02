"""Sheet setup: border, frame, notes, legend and the TBD schedule.

Sheet sizes are ISO A-series in landscape. The TBD schedule is a FIRST-CLASS
sheet element, not an error state: a GA with honestly-declared gaps is a usable
drawing, whereas a GA with invented dimensions is a liability. That is the whole
philosophy of the platform expressed in drafting terms.
"""
from . import title_block as tb
from .primitives import (LW_MED, LW_THIN, L_BORDER, L_TEXT, Line, Rect, Text)

# (width, height) in mm, landscape.
SHEET_SIZES = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
}
DEFAULT_SIZE = "A3"

MARGIN = 10.0          # outer edge to frame
NOTE_W = 148.0         # notes/legend column width (matches the title block)


def frame(canvas, w: float, h: float) -> None:
    """Sheet edge and drawing frame."""
    canvas.add(Rect(0, 0, w, h, L_BORDER, LW_THIN))
    canvas.add(Rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN, L_BORDER, LW_MED))


def drawing_area(w: float, h: float) -> tuple[float, float, float, float]:
    """(x, y, width, height) available for the views — the frame minus the
    right-hand column that carries the notes, legend and title block."""
    x = MARGIN + 6.0
    y = MARGIN + 12.0
    return x, y, w - 2 * MARGIN - NOTE_W - 14.0, h - 2 * MARGIN - 24.0


def header(canvas, w: float, title: str, subtitle: str) -> None:
    canvas.add(Text(MARGIN + 4.0, MARGIN + 7.5, title, L_TEXT, 4.2, "start", bold=True))
    if subtitle:
        canvas.add(Text(w - MARGIN - 4.0, MARGIN + 7.5, subtitle, L_TEXT, 2.6, "end"))
    canvas.add(Line(MARGIN, MARGIN + 10.0, w - MARGIN, MARGIN + 10.0, L_BORDER, LW_THIN))


def _item_table(canvas, x: float, y: float, bom: list, limit: int = 8) -> float:
    """The parts list a real GA carries, so the sheet stands on its own.

    Reading a drawing should not require the studio panel beside it: an item
    table is how an engineer finds out WHAT the balloons refer to when the sheet
    is printed or emailed. Rows come from the resolved specification, so nothing
    here is drawing-only invention.
    """
    if not bom:
        return y
    line_h = 4.0
    canvas.add(Text(x, y, f"ITEM LIST ({len(bom)})", L_TEXT, 2.9, "start", bold=True))
    y += line_h + 1.0
    canvas.add(Line(x, y - 2.6, x + NOTE_W, y - 2.6, L_BORDER, LW_THIN))
    for i, row in enumerate(bom[:limit], 1):
        canvas.add(Text(x, y, str(i), L_TEXT, 2.3, "start"))
        canvas.add(Text(x + 6.0, y, str(row.get("item", ""))[:30], L_TEXT, 2.3, "start"))
        canvas.add(Text(x + 62.0, y, str(row.get("spec", ""))[:42], L_TEXT, 2.3, "start"))
        y += line_h
    if len(bom) > limit:
        canvas.add(Text(x + 6.0, y, f"... and {len(bom) - limit} more", L_TEXT, 2.2, "start"))
        y += line_h
    return y + 3.0


def revision_block(canvas, w: float, h: float, revisions: list) -> None:
    """The revision strip, sitting directly above the title block as on a real
    sheet. Every drawing is issued at SOME revision; stating which one, when and
    why is what makes a re-issued drawing safe to work from."""
    if not revisions:
        return
    rows = revisions[-3:]                      # the sheet has room for three
    line_h = 4.4
    x = w - MARGIN - tb.TB_W
    bottom = h - MARGIN - tb.TB_H - 2.0
    y = bottom - line_h * len(rows)
    canvas.add(Text(x, y - 3.0, "REVISIONS", L_TEXT, 2.4, "start", bold=True))
    canvas.add(Line(x, y - 1.6, x + tb.TB_W, y - 1.6, L_BORDER, LW_THIN))
    for r in rows:
        canvas.add(Text(x + 1.0, y + 2.6, str(r.get("rev", ""))[:4], L_TEXT, 2.2, "start"))
        canvas.add(Text(x + 12.0, y + 2.6, str(r.get("description", ""))[:52],
                        L_TEXT, 2.2, "start"))
        canvas.add(Text(x + tb.TB_W - 1.0, y + 2.6, str(r.get("date", ""))[:12],
                        L_TEXT, 2.2, "end"))
        y += line_h


def side_column(canvas, w: float, h: float, legend: list, notes: list,
                tbd: list, bom: list | None = None) -> None:
    """Legend, item list, general notes and the TBD schedule, stacked above the
    title block."""
    x = w - MARGIN - NOTE_W
    y = MARGIN + 16.0
    line_h = 4.0

    if legend:
        canvas.add(Text(x, y, "LEGEND", L_TEXT, 2.9, "start", bold=True))
        y += line_h + 1.0
        for tag, desc in legend:
            canvas.add(Text(x, y, f"{tag}.", L_TEXT, 2.4, "start", bold=True))
            canvas.add(Text(x + 7.0, y, str(desc)[:72], L_TEXT, 2.4, "start"))
            y += line_h
        y += 3.0

    if tbd:
        canvas.add(Text(x, y, f"TO BE DETERMINED ({len(tbd)})", L_TEXT, 2.9,
                        "start", bold=True))
        y += line_h + 1.0
        for item in tbd[:12]:
            canvas.add(Text(x, y, "—", L_TEXT, 2.4, "start"))
            canvas.add(Text(x + 5.0, y, str(item)[:70], L_TEXT, 2.4, "start"))
            y += line_h
        if len(tbd) > 12:
            canvas.add(Text(x + 5.0, y, f"... and {len(tbd) - 12} more", L_TEXT, 2.3, "start"))
            y += line_h
        y += 3.0

    y = _item_table(canvas, x, y, bom or [])

    if notes:
        canvas.add(Text(x, y, "NOTES", L_TEXT, 2.9, "start", bold=True))
        y += line_h + 1.0
        for i, note in enumerate(notes, 1):
            canvas.add(Text(x, y, f"{i}.", L_TEXT, 2.3, "start"))
            canvas.add(Text(x + 5.0, y, str(note)[:78], L_TEXT, 2.3, "start"))
            y += line_h


def title(canvas, w: float, h: float, info: dict) -> None:
    tb.draw(canvas, w, h, MARGIN, info)
