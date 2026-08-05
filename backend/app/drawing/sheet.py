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
# Characters that fit one legend/TBD line at 2.4 mm text in a 148 mm column.
# Measured off a render rather than assumed: the previous hard cut of 72 left
# roughly a third of the column empty AND still sliced words in half.
LEGEND_CHARS = 96


def _wrap(text: str, limit: int, max_lines: int = 2) -> list[str]:
    """Break a description at SPACES so a sheet never cuts a word in half.

    The column used to hard-slice at a fixed character count, which printed
    legend rows reading "... confirm booth s" and "Inner size (m): 3L x 1" —
    a truncated engineering value looks like a wrong one. Wrapping is capped at
    `max_lines` so a long row cannot push the notes off the bottom of the sheet;
    anything still over runs out with an ellipsis, which reads as "continues"
    rather than as a value.
    """
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for i, word in enumerate(words):
        while len(word) > limit:               # a single unbreakable long token
            if cur:
                lines.append(cur)
                cur = ""
            if len(lines) >= max_lines:
                break
            lines.append(word[:limit])
            word = word[limit:]
        if len(lines) >= max_lines:
            break
        candidate = f"{cur} {word}".strip()
        if len(candidate) <= limit:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                cur = ""
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    used = len(" ".join(lines).split())
    if used < len(words):
        tail = lines[-1]
        lines[-1] = (tail if len(tail) + 4 <= limit else tail[:limit - 4].rstrip()) + " ..."
    return lines or [""]


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


def _item_table(canvas, x: float, y: float, bom: list,
                limit_y: float = 1e9) -> float:
    """The parts list a real GA carries, so the sheet stands on its own.

    Reading a drawing should not require the studio panel beside it: an item
    table is how an engineer finds out WHAT the balloons refer to when the sheet
    is printed or emailed. Rows come from the resolved specification, so nothing
    here is drawing-only invention.

    The row count is bounded by the SPACE LEFT rather than a fixed cap. A hard
    cap of 8 silently dropped a third of a paint booth's 12 parts; letting the
    sheet decide prints every row that fits and says how many did not.
    """
    if not bom:
        return y
    line_h = 4.0
    if y + line_h * 3 > limit_y:
        return y
    canvas.add(Text(x, y, f"ITEM LIST ({len(bom)})", L_TEXT, 2.9, "start", bold=True))
    y += line_h + 1.0
    canvas.add(Line(x, y - 2.6, x + NOTE_W, y - 2.6, L_BORDER, LW_THIN))
    shown = 0
    for i, row in enumerate(bom, 1):
        if y + line_h > limit_y:
            break
        canvas.add(Text(x, y, str(i), L_TEXT, 2.3, "start"))
        canvas.add(Text(x + 6.0, y, str(row.get("item", ""))[:42], L_TEXT, 2.3, "start"))
        canvas.add(Text(x + 62.0, y, str(row.get("spec", ""))[:62], L_TEXT, 2.3, "start"))
        y += line_h
        shown += 1
    if shown < len(bom) and y + line_h <= limit_y:
        canvas.add(Text(x + 6.0, y, f"... and {len(bom) - shown} more",
                        L_TEXT, 2.2, "start"))
        y += line_h
    return y + 3.0


def _kv_block(canvas, x: float, y: float, heading: str, data: list,
              limit_y: float) -> float:
    """A titled label/value table — DESIGN DATA and KEY DIMENSIONS share this.

    A production GA states its duty on the sheet (airflow, static pressure,
    motor rating, material, finish) and schedules the dimensions the engine
    owns, so the drawing can be read without the specification beside it. Every
    value was already resolved by the engineering engine; this composes, it
    never computes.

    An EMPTY block draws nothing at all — a heading over no rows reads as data
    that failed to load, which is worse than not offering the block.
    """
    if not data:
        return y
    line_h = 4.0
    if y + line_h * 3 > limit_y:            # no room for a header + a row
        return y
    canvas.add(Text(x, y, heading, L_TEXT, 2.9, "start", bold=True))
    y += line_h + 1.0
    canvas.add(Line(x, y - 2.6, x + NOTE_W, y - 2.6, L_BORDER, LW_THIN))
    shown = 0
    for row in data:
        if y + line_h > limit_y:
            break
        canvas.add(Text(x, y, str(row.get("label", ""))[:34], L_TEXT, 2.3, "start"))
        canvas.add(Text(x + 60.0, y, str(row.get("value", ""))[:56], L_TEXT, 2.3, "start"))
        y += line_h
        shown += 1
    if shown < len(data) and y + line_h <= limit_y:
        canvas.add(Text(x, y, f"... and {len(data) - shown} more (see specification)",
                        L_TEXT, 2.2, "start"))
        y += line_h
    return y + 3.0


def _data_table(canvas, x: float, y: float, data: list, limit_y: float) -> float:
    """The DESIGN DATA block. See `_kv_block`."""
    return _kv_block(canvas, x, y, "DESIGN DATA", data, limit_y)


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
                tbd: list, bom: list | None = None, data: list | None = None,
                reserve: float = 0.0, key_dims: list | None = None) -> None:
    """Legend, design data, item list, general notes and the TBD schedule.

    EVERY SECTION IS BOUNDED. The column used to advance `y` with no reference
    to the title block, so on an A4 sheet the notes printed straight over it —
    verified, 6 stray text elements on a dust collector. The bound matters more
    now that the column carries a design-data table too: an unbounded column
    would turn a fuller sheet into an unreadable one.
    """
    x = w - MARGIN - NOTE_W
    y = MARGIN + 16.0
    line_h = 4.0
    # Everything must finish above the title block (and the revision strip that
    # sits on top of it, when there is one).
    bottom = h - MARGIN - tb.TB_H - 2.0 - reserve
    # THE NOTES ARE NOT OPTIONAL. They carry the standing engineering statements
    # — that positions are indicative, and that the sheet is a draft not released
    # for construction (golden rule #3). Drawn last, they were the first thing a
    # full column dropped. Their space is therefore reserved UP FRONT and the
    # schedules above them absorb the truncation instead.
    notes_h = (line_h * (len(notes) + 1) + 4.0) if notes else 0.0
    limit_y = bottom - notes_h

    def room(need: float = line_h) -> bool:
        return y + need <= limit_y

    if legend:
        if room(line_h * 2):
            canvas.add(Text(x, y, "LEGEND", L_TEXT, 2.9, "start", bold=True))
            y += line_h + 1.0
            dropped = 0
            for tag, desc in legend:
                parts = _wrap(desc, LEGEND_CHARS)
                if not room(line_h * len(parts)):
                    dropped += 1
                    continue
                canvas.add(Text(x, y, f"{tag}.", L_TEXT, 2.4, "start", bold=True))
                for part in parts:
                    canvas.add(Text(x + 7.0, y, part, L_TEXT, 2.4, "start"))
                    y += line_h
            if dropped and room():
                canvas.add(Text(x + 7.0, y, f"... and {dropped} more item(s)",
                                L_TEXT, 2.3, "start"))
                y += line_h
            y += 3.0

    if tbd and room(line_h * 2):
        canvas.add(Text(x, y, f"TO BE DETERMINED ({len(tbd)})", L_TEXT, 2.9,
                        "start", bold=True))
        y += line_h + 1.0
        shown = 0
        for item in tbd:
            parts = _wrap(item, LEGEND_CHARS)
            if not room(line_h * len(parts)):
                break
            canvas.add(Text(x, y, "—", L_TEXT, 2.4, "start"))
            for part in parts:
                canvas.add(Text(x + 5.0, y, part, L_TEXT, 2.4, "start"))
                y += line_h
            shown += 1
        if shown < len(tbd) and room():
            canvas.add(Text(x + 5.0, y, f"... and {len(tbd) - shown} more",
                            L_TEXT, 2.3, "start"))
            y += line_h
        y += 3.0

    y = _kv_block(canvas, x, y, "KEY DIMENSIONS", key_dims or [], limit_y)
    y = _data_table(canvas, x, y, data or [], limit_y)
    y = _item_table(canvas, x, y, bom or [], limit_y)

    if notes:
        # Into the reserved strip: every standing note prints, always.
        y = max(y, bottom - notes_h)
        canvas.add(Text(x, y, "NOTES", L_TEXT, 2.9, "start", bold=True))
        y += line_h + 1.0
        for i, note in enumerate(notes, 1):
            canvas.add(Text(x, y, f"{i}.", L_TEXT, 2.3, "start"))
            canvas.add(Text(x + 5.0, y, str(note)[:78], L_TEXT, 2.3, "start"))
            y += line_h


def title(canvas, w: float, h: float, info: dict) -> None:
    tb.draw(canvas, w, h, MARGIN, info)
