"""Orchestrator: a resolved specification becomes a P&ID sheet.

The counterpart of `drawing/drawing_service.py`, and deliberately its sibling
rather than a branch inside it: the GA's body is `choose_scale -> layout ->
classify -> draw_components`, and none of those four steps means anything here.
What the two share is the SHEET — frame, header, side column, title block,
revision strip — and the exporters, both of which are reached by returning the
same `(Canvas, payload)` pair the GA returns.

Its contract is the GA's contract: pure, deterministic, and no number reaches
the sheet that the engineering did not resolve.
"""
from datetime import date
from typing import Any, Optional

from ...engineering.process_model import STATUS_PROPOSED
from ...engineering.train_templates import train_for
from .. import sheet
from ..primitives import LAYER_LABELS, L_COMPONENT, L_TEXT, Canvas, Text
from ..style import T_BODY, T_CAPTION, T_SECTION, T_TINY
from . import layout as pid_layout
from . import ports as pid_ports
from . import route as pid_route
from . import schedules as pid_schedules
from . import states as pid_states
from . import symbols as pid_symbols

# The drawing types this module answers to. `drawing_service.compose` dispatches
# on membership here, so adding a variant needs no change there.
PID_TYPES = frozenset({"pid", "pfd"})

# A PFD is the same train with the instrumentation stripped. It is not a second
# engine: the instrument layer simply is not drawn, which is exactly what the
# studio's layer toggle already does for a reader.
PFD = "pfd"


def compose(spec: dict, sheet_size: str = sheet.DEFAULT_SIZE,
            client: str = "", ref: str = "", drawn_by: str = "",
            title_block: Optional[dict] = None,
            revisions: Optional[list] = None,
            drawing_type: str = "pid") -> tuple[Canvas, dict[str, Any]]:
    """Build the P&ID sheet and return both the canvas and the payload."""
    size = sheet_size if sheet_size in sheet.SHEET_SIZES else sheet.DEFAULT_SIZE
    sw, sh = sheet.SHEET_SIZES[size]
    canvas = Canvas(sw, sh)

    rows = spec.get("technical_details") or []
    geom = spec.get("geometry") or {}
    category = spec.get("category") or ""
    label = (spec.get("category_label")
             or category.replace("_", " ").title() or "Equipment")
    is_pfd = str(drawing_type or "").lower() == PFD
    doc = "Process Flow Diagram" if is_pfd else "Process & Instrumentation Diagram"

    train = train_for(category, rows, spec.get("parameters") or {}, geom)
    st = pid_states.classify(train)

    sheet.frame(canvas, sw, sh)
    sheet.column_divider(canvas, sw, sh)
    sheet.header(canvas, sw, f"{label} - {doc}",
                 "Deterministic diagram generated from the engineering "
                 "specification")

    ax, ay, aw, ah = sheet.drawing_area(sw, sh)

    placed: list = []
    line_rows: list = []
    instr_rows: list = []
    legend: list = []
    hop_count = 0

    if st.is_schematic:
        _refusal(canvas, ax, ay, aw, label, train)
    else:
        placed = pid_layout.layout(train.nodes, ax, ay, aw, ah)
        by_key = pid_layout.by_key(placed)
        hop_count = _draw_train(canvas, train, placed, by_key, aw, is_pfd)

        tags = {n.key: n.tag for n in train.nodes}
        line_rows = pid_schedules.line_rows(train, tags)
        instr_rows = [] if is_pfd else pid_schedules.instrument_rows(train)
        legend = ([(v["tag"], v["description"])
                   for v in pid_schedules.valve_rows(train)]
                  if not is_pfd else [])

        y = pid_layout.band_bottom(placed)
        y = _banner(canvas, ax, y, aw, st)
        limit = ay + ah - 4.0
        y = sheet.schedule_table(canvas, ax, y + 6.0, aw, "LINE SCHEDULE",
                                 pid_schedules.LINE_COLUMNS, line_rows, limit)
        if instr_rows:
            y = sheet.schedule_table(canvas, ax, y + 8.0, aw,
                                     "INSTRUMENT INDEX",
                                     pid_schedules.INSTRUMENT_COLUMNS,
                                     instr_rows, limit)

    unresolved = pid_states.unresolved(train, rows)
    tbd = [f"{u['parameter']} - {u['action']}" for u in unresolved]
    equipment = pid_schedules.equipment_rows(train) if train.ok else []
    design = _design_data(spec, train)

    reserve = (4.4 * len(revisions[-3:]) + 4.0) if revisions else 0.0
    # The unresolved schedule already prints in FULL on the refusal sheet, where
    # it IS the content; repeating a shorter copy in the side column would read
    # as two lists that happen to agree. Same argument the GA makes.
    sheet.side_column(canvas, sw, sh, legend,
                      pid_states.STANDING_NOTES,
                      [] if st.is_schematic else tbd,
                      equipment, design, reserve, [])

    info = {
        "title": f"{label} - {'PFD' if is_pfd else 'P&ID'}",
        "client": client or "TO BE CONFIRMED",
        "ref": ref or f"VT/PID/{date.today():%y%m%d}/DRAFT",
        # A P&ID is NEVER to scale. Printing a ratio here would invite the one
        # thing the sheet must not be used for.
        "scale": "NTS",
        "size": size, "units": "-",
        "date": f"{date.today():%d-%m-%Y}",
        "drawn": drawn_by or "Vitech AI",
        "checked": "", "rev": "0",
        "status": "PRELIM" if st.is_schematic else "DRAFT",
        "duty": _duty(train),
    }
    info.update({k: v for k, v in (title_block or {}).items()
                 if str(v or "").strip()})
    sheet.title(canvas, sw, sh, info)
    sheet.revision_block(canvas, sw, sh, revisions or [])

    present = canvas.layers_present()
    return canvas, {
        "ok": True,
        "category": category,
        "category_label": label,
        "drawing_type": "pfd" if is_pfd else "pid",
        "svg": canvas.svg(),
        "scale": "NTS",
        "sheet_size": size,
        "sheet_mm": {"width": sw, "height": sh},
        "ready": bool(train.ok),
        "views": [],
        "layers": [{"id": l, "label": LAYER_LABELS.get(l, l), "on": True}
                   for l in present],
        "legend": [{"tag": t, "description": d} for t, d in legend],
        "bom": equipment,
        "design_data": design,
        "key_dimensions": [],
        "line_schedule": line_rows,
        "instrument_index": instr_rows,
        "tbd": tbd,
        "state": st.state,
        "state_label": st.label,
        "state_notes": list(st.notes),
        "unresolved": unresolved,
        "missing_axes": [],
        "notes": pid_states.STANDING_NOTES + list(st.notes),
        "title_block": info,
        "template_id": train.template_id,
        "template_basis": train.basis,
        "hops": hop_count,
        "drawing_markdown": _markdown(label, doc, train, st, line_rows,
                                      instr_rows, size),
    }


def build_drawing(spec: dict, **kw) -> dict[str, Any]:
    return compose(spec, **kw)[1]


# --- drawing ---------------------------------------------------------------
def _draw_train(canvas, train, placed, by_key, aw: float,
                is_pfd: bool) -> int:
    """Symbols, lines, hops, inline elements, tags and instruments.

    Routed geometry is held in a LOCAL dict and handed to the passes that need
    it. Module-level state would be quicker to write and would make two sheets
    composed in one process able to see each other's lines — which for an engine
    whose whole contract is "same spec in, same bytes out" is not a risk worth
    taking for a saved parameter.
    """
    col_w, _top, _bh, _l0 = pid_layout.band_geometry(train.nodes, 0, 0, aw, 0)
    ks = pid_route.corridors(train.streams, by_key)

    routes: dict = {}
    routed: list = []
    for s in train.streams:
        a, b = by_key.get(s.frm), by_key.get(s.to)
        if not a or not b:
            continue                      # QA reports it; never draw a dangle
        pts = pid_route.route(s, a, b, ks.get(s.tag, 0), col_w)
        routes[s.tag] = (s, pts)
        routed.append((s.tag, s.medium, pid_route.segments(pts)))

    # Decide every hop BEFORE drawing any line, so a line is broken by all the
    # crossings it has rather than by whichever happened to be found first.
    hops: dict = {}
    for tag_a, med_a, _sa, tag_b, med_b, _sb, pt in pid_route.crossings(routed):
        loser = tag_a if pid_route.hop_owner(med_a, med_b) else tag_b
        hops.setdefault(loser, []).append(pt)

    for tag, (s, pts) in routes.items():
        pid_route.draw_line(canvas, pts, s.medium, hops.get(tag, []))
        _arrow_at_end(canvas, pts, s.medium)
        _label_line(canvas, pts, s)

    for v in train.inline:
        entry = routes.get(v.on)
        if entry:
            _draw_inline(canvas, v, entry[1])

    # Symbols AFTER lines, so a vessel sits over the run reaching it rather
    # than being crossed out by it.
    for p in placed:
        glyph = pid_symbols.PID_SYMBOLS.get(p.kind)
        if glyph:
            glyph(canvas, p.x, p.y, p.w, p.h, p.node)

    for p in placed:
        if p.node.inside:
            # AN INTERNAL IS STILL TAGGED. A demister drawn inside its tower but
            # left unlabelled is a shape the reader cannot name, while the
            # equipment schedule lists a DM-101 they cannot find - the schedule
            # and the drawing disagreeing, which is the failure this platform
            # exists to prevent. It is labelled beside its host, at its own
            # height, so it never collides with the host's own tag block.
            host = by_key.get(p.node.inside)
            hx = (host.x + host.w) if host else (p.x + p.w)
            canvas.add(Text(hx + 2.0, p.y + 1.2, p.tag, L_COMPONENT, T_TINY,
                            "start"))
            continue
        lines = [f"{c} {a.text}" for c, a in p.node.attrs]
        # A TALL vessel takes its tag BESIDE it, not under it. A tower's bottom
        # is where its drain leaves, so a tag block centred below one lands on
        # the drain line and on whatever that line runs to.
        if p.h > pid_layout.NODE_H * 1.5:
            pid_symbols.tag_text(canvas, p.x + p.w * 1.15, p.y + p.h * 0.62,
                                 p.tag, lines[:3])
        else:
            pid_symbols.tag_text(canvas, p.cx, p.y + p.h + 3.4, p.tag,
                                 lines[:3])

    if not is_pfd:
        _draw_instruments(canvas, train, by_key, routes)

    return sum(len(v) for v in hops.values())


def _arrow_at_end(canvas, pts, medium: str) -> None:
    (bx, by), (tx, ty) = pts[-2], pts[-1]
    pid_symbols.arrow(canvas, tx, ty, tx - bx, ty - by,
                      pid_route.pen_for(medium))


def _label_line(canvas, pts, s) -> None:
    """The line tag, and its bore where one is resolved, above the longest run.

    Only the SIZE joins the tag on the diagram: a flow and a spec belong in the
    schedule, and three values stacked over every line would bury the process
    under its own annotation.
    """
    best, blen = None, 0.0
    for x1, y1, x2, y2 in pid_route.segments(pts):
        d = abs(x2 - x1) + abs(y2 - y1)
        if d > blen:
            best, blen = (x1, y1, x2, y2), d
    if not best or blen < 8.0:
        return
    x1, y1, x2, y2 = best
    text = s.tag + (f"  {s.size.text}" if s.size.resolved else "")
    if abs(y1 - y2) < 0.01:
        canvas.add(Text((x1 + x2) / 2, y1 - 1.4, text, L_COMPONENT, T_TINY,
                        "middle"))
    else:
        canvas.add(Text(x1 + 1.2, (y1 + y2) / 2, text, L_COMPONENT, T_TINY,
                        "middle", rotate=-90))


def _draw_inline(canvas, v, pts) -> None:
    """Place a valve at its fraction along the routed polyline, by arc length,
    and rotate it to the segment it lands on."""
    segs = pid_route.segments(pts)
    total = sum(abs(b - a) + abs(d - c) for a, c, b, d in
                [(s[0], s[1], s[2], s[3]) for s in segs]) or 1.0
    want = total * max(0.05, min(0.95, v.at))
    run = 0.0
    for x1, y1, x2, y2 in segs:
        d = abs(x2 - x1) + abs(y2 - y1)
        if run + d >= want and d > 0:
            t = (want - run) / d
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            ang = 0.0 if abs(y1 - y2) < 0.01 else 1.5707963
            pid_symbols.inline_symbol(canvas, v.kind, cx, cy, ang)
            canvas.add(Text(cx, cy - 4.4, v.tag, L_COMPONENT, T_TINY,
                            "middle"))
            return
        run += d


def _draw_instruments(canvas, train, by_key, routes) -> None:
    """Bubbles, alternating above then below what they measure.

    Alternating by INDEX WITHIN THE TARGET is what keeps two devices on one line
    apart, deterministically, without a collision test.
    """
    per_target: dict = {}
    for i in train.instruments:
        n = per_target.get(i.on, 0)
        per_target[i.on] = n + 1
        anchor = by_key.get(i.on)
        if anchor is not None:
            px, py = anchor.cx, anchor.y
        else:
            entry = routes.get(i.on)
            if not entry:
                continue
            # Two thirds along the LONGEST segment, not the polyline midpoint:
            # a midpoint often falls on the stub right beside the vessel the
            # line leaves, which put the bubble on top of that vessel.
            best, blen = None, -1.0
            for x1, y1, x2, y2 in pid_route.segments(entry[1]):
                d = abs(x2 - x1) + abs(y2 - y1)
                if d > blen:
                    best, blen = (x1, y1, x2, y2), d
            px = best[0] + (best[2] - best[0]) * 0.66
            py = best[1] + (best[3] - best[1]) * 0.66
        # OFFSET SIDEWAYS off the centreline. A bubble placed on a node's
        # centre sits exactly where that node's top or bottom port is, so the
        # signal line ran along the process line and the bubble landed on the
        # vessel. Alternating left/right keeps two devices on one item apart
        # without a collision test, the same way lanes keep nodes apart.
        side = -1.0 if n % 2 == 0 else 1.0
        if anchor is not None:
            # Beside the item, with the signal running DOWN then IN to its
            # edge. A purely vertical signal from an offset bubble stopped in
            # open space and touched nothing, which on a P&ID says the device
            # measures nothing.
            edge = anchor.x if side < 0 else anchor.x + anchor.w
            px = edge + side * 12.0
            ty = anchor.y + anchor.h * 0.30
            cy = ty - 14.0 - 9.0 * (n // 2)
            pid_symbols.signal(canvas, px, cy + pid_symbols.BUBBLE_R, px, ty)
            pid_symbols.signal(canvas, px, ty, edge, ty)
        else:
            # On a LINE: step perpendicular off the run, so the bubble never
            # sits on the line it is measuring.
            cy = py - 14.0 - 9.0 * (n // 2)
            px = px + side * 8.0
            pid_symbols.signal(canvas, px, cy + pid_symbols.BUBBLE_R, px, py)
            pid_symbols.signal(canvas, px, py, px - side * 8.0, py)
        pid_symbols.instrument(canvas, px, cy, i.tag, i.mounting,
                               i.status == STATUS_PROPOSED)


def _banner(canvas, ax: float, y: float, aw: float, st) -> float:
    for note in st.notes:
        canvas.add(Text(ax + aw / 2, y, note, L_TEXT, T_CAPTION, "middle",
                        bold=True))
        y += 3.4
    return y


def _refusal(canvas, ax: float, ay: float, aw: float, label: str,
             train) -> None:
    """The sheet for a category with no template.

    It draws NO process. A plausible generic chain invented to fill the page
    would be the P&ID's version of a fabricated dimension — and unlike a wrong
    number, a wrong connection cannot be spotted by checking it against
    anything.
    """
    cx = ax + aw / 2
    y = ay + 26.0
    canvas.add(Text(cx, y, f"{label.upper()}", L_TEXT, T_SECTION, "middle",
                    bold=True))
    canvas.add(Text(cx, y + 7.0, "PROCESS TOPOLOGY NOT ESTABLISHED",
                    L_TEXT, T_SECTION, "middle", bold=True))
    y += 14.0
    for note in (train.notes or ()):
        canvas.add(Text(cx, y, str(note), L_TEXT, T_BODY, "middle"))
        y += 4.0
    canvas.add(Text(cx, y + 2.0,
                    "No process diagram is drawn: a generic arrangement would "
                    "assert connections this plant may not have.",
                    L_TEXT, T_CAPTION, "middle"))


def _design_data(spec: dict, train) -> list:
    """The duty rows a reader needs beside the diagram.

    A partition of the resolved specification, exactly as the GA does it, minus
    anything already carried by a node's tag block — so a value appears on the
    sheet once.
    """
    on_diagram = set()
    for n in train.nodes:
        for _c, a in n.attrs:
            if a.source_label:
                on_diagram.add(a.source_label)
    out = []
    for row in spec.get("technical_details") or []:
        label = str(row.get("label", ""))
        value = str(row.get("value", "")).strip()
        if not label or label in on_diagram:
            continue
        if row.get("origin") == "tbd" or value.lower() in (
                "", "to be determined"):
            continue
        out.append({"label": label, "value": value,
                    "origin": row.get("origin")})
    return out[:14]


def _duty(train) -> str:
    for s in train.streams:
        if s.flow.resolved:
            return f"Duty: {s.flow.text}"[:40]
    return ""


def _markdown(label: str, doc: str, train, st, lines: list, instr: list,
              size: str) -> str:
    """The short summary the agent narrates. The CANVAS carries the diagram, and
    the schedules are on the sheet — so this stays a summary."""
    L = [f"**{label} — {doc} (DRAFT)**", ""]
    if not train.ok:
        L.append("No process template exists for this equipment, so no "
                 "diagram is drawn.")
        for n in train.notes or ():
            L.append(f"- {n}")
        return "\n".join(L)
    L.append(f"Sheet {size}, NOT TO SCALE. {len(train.nodes)} tagged items, "
             f"{len(lines)} lines, {len(instr)} instruments.")
    sized = sum(1 for s in train.streams if s.size.resolved)
    L.append(f"{sized} of {len(train.streams)} lines carry an engineered size; "
             f"the remainder are scheduled as TBD.")
    if st.proposed_instruments:
        L.append(f"{st.proposed_instruments} instrument(s) are PROPOSED — "
                 f"scope to be confirmed.")
    L += ["", "_Engineer-reviewed draft — not released for construction._"]
    return "\n".join(L)
