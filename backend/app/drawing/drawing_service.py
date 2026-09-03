"""Orchestrator: a resolved specification becomes a 2D GA drawing.

`build_drawing(spec)` is the one entry point `/api/tools/drawing` calls. It is
pure and deterministic — the same spec always produces byte-identical SVG, which
is what makes the drawing engine golden-testable like the spec engine.

The LLM contributes nothing here. It receives `drawing_markdown` (a short human
summary) and the studio receives the SVG; neither the model nor the canvas ever
invents a dimension.
"""
import re
from datetime import date
from typing import Any, Optional

from . import schematic as schematic_mod
from . import sheet, states, symbols, views
from .primitives import LAYER_LABELS, L_TEXT, Canvas, Text
from .style import T_BODY, T_CAPTION

# Stated on every sheet, because the component glyphs are schematic. Without
# this note a reader could mistake an indicative symbol for a set-out position.
STANDING_NOTES = [
    "All dimensions in millimetres unless noted otherwise.",
    "Component positions indicative; refer detailed GA for setting out.",
    "Engineer-reviewed draft - not released for construction.",
]


# Equipment whose FOOTPRINT is a circle, so its plan dimensions are a diameter
# and must be annotated as one. The type comes from the engineering layer's
# geometry model — the renderer never decides it from row labels.
_CIRCULAR_PLAN = {"vertical_spray_tower", "round_duct"}

DIA = "Ø"


def _dim_labels(env: dict, equipment_type: str = "") -> dict:
    """Axis -> printed dimension text. A missing axis prints TBD, never a
    number, so the drawing cannot imply a dimension nobody has computed.

    A circular footprint is dimensioned with the diameter symbol. "750" on the
    plan of a spray tower reads as a square 750 mm casing; the machine is a
    750 mm BORE, and on a drawing that difference is the whole shape. Which
    equipment this is comes from `geometry.equipment_type`, resolved once by
    the engineering layer.
    """
    circular = equipment_type in _CIRCULAR_PLAN
    out = {}
    for axis in ("length", "width", "height"):
        v = env.get(axis)
        if not (isinstance(v, (int, float)) and v):
            out[axis] = "TBD"
            continue
        # Height is a height on any equipment; only the plan axes are a bore.
        prefix = DIA if (circular and axis in ("length", "width")) else ""
        out[axis] = f"{prefix}{int(v)}"
    return out


# Dimensional values the ENGINE owns, worth scheduling beside the views. A row
# qualifies only when it carries a real dimension AND a trusted origin — a size
# reused from a historical offer describes a different machine and must never be
# presented as a dimension of this one.
_DIM_TRUSTED = {"given", "rule", "requirement", "standard"}
_DIM_LABELS = ("tower diameter", "duct", "filter", "collector size",
               "scrubber dimension", "inner size", "tank size", "job size")
# A value that actually states a size: "1800 mm dia", "600 x 600 x 50 mm",
# "2.15L x 1.15W x 4.95H". A bare integer ("19") is a count, not a dimension.
# The axis-suffixed form needs its own branch — the letter between the number
# and the separator defeats a plain "number x number".
_DIM_VALUE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:mm|m)\b)"
    r"|(\d+(?:\.\d+)?\s*[xX*]\s*\d+)"
    r"|(\d+(?:\.\d+)?\s*[LWHDlwhd]\s*[xX*])"
    r"|(\bdia\b)", re.I)


def _key_dimensions(spec: dict) -> list[dict]:
    """Engine-owned dimensions, formatted with the right symbol.

    These are values the specification ALREADY resolved — a duct bore from the
    client's own transport-velocity standard, a filter element size, a stated
    casing. Scheduling them puts real dimensions on the sheet without inventing
    a setting-out position for anything, which is the line golden rule #2 draws.
    """
    out = []
    for row in spec.get("technical_details") or []:
        label = str(row.get("label", ""))
        value = str(row.get("value", "")).strip()
        origin = str(row.get("origin", "")).lower()
        if not value or value.lower() == "to be determined":
            continue
        if not any(t in origin for t in _DIM_TRUSTED):
            continue
        low = label.lower()
        if not any(nd in low for nd in _DIM_LABELS):
            continue
        # The unit may sit in the VALUE ("1800 mm dia") or in the LABEL
        # ("Tower diameter (mm)" = "750"). Reading only the value dropped every
        # dimension the engine states the tidy way.
        unit_in_label = re.search(r"\((mm|m|cm)\)", low)
        if not _DIM_VALUE.search(value) and not (unit_in_label and re.match(r"^[\d.]+$", value)):
            continue
        if unit_in_label and re.match(r"^[\d.]+$", value):
            value = f"{value} {unit_in_label.group(1)}"
        # A bore is annotated once. "Ø 600 mm dia" says diameter twice, so the
        # redundant word goes when the symbol takes its place.
        if "dia" in low or "dia" in value.lower():
            if DIA not in value:
                value = re.sub(r"\s*\bdia\b\.?", "", value, flags=re.I).strip(" ,")
                value = f"{DIA}{value}"
        out.append({"label": label, "value": value})
    return out


def _partial_banner(canvas, ax: float, ay: float, aw: float, gstate,
                    drawing_type: str, placed: list) -> None:
    """State 2: say which extents are unresolved, and which views are absent.

    A partially dimensioned sheet is the easiest of the three to misread,
    because it LOOKS like a finished GA — the views that could be drawn are
    drawn to scale and dimensioned. What stops the misreading is naming the
    missing axis and, crucially, saying that a view is ABSENT rather than
    letting the reader assume the machine has no such aspect.
    """
    canvas.add(Text(ax + aw / 2, ay + 4.6,
                    "PARTIALLY DIMENSIONED - UNRESOLVED SIZES SHOWN AS TBD",
                    L_TEXT, T_BODY, "middle", bold=True))
    note = states.required_inputs_note(gstate)
    if note:
        canvas.add(Text(ax + aw / 2, ay + 9.0, note, L_TEXT, T_CAPTION, "middle"))

    wanted = list(views.VIEW_SETS.get(str(drawing_type or "ga").lower(),
                                      views.VIEW_SETS["ga"]))
    drawn = {v.key for v in placed}
    absent = [k for k in wanted if k not in drawn]
    if absent:
        canvas.add(Text(ax + aw / 2, ay + 13.0,
                        "View(s) omitted for want of a dimension: "
                        + ", ".join(absent),
                        L_TEXT, T_CAPTION, "middle"))


def _tbd_items(spec: dict) -> list[str]:
    """Everything the spec honestly could not resolve, for the sheet schedule."""
    out = []
    geom = spec.get("geometry") or {}
    env = geom.get("envelope_mm") or {}
    for axis in ("length", "width", "height"):
        if not env.get(axis):
            out.append(f"Overall {axis} - needs engineering input")
    for row in spec.get("technical_details") or []:
        if row.get("origin") == "tbd" or str(row.get("value", "")).strip().lower() == "to be determined":
            out.append(f"{row.get('label')} - needs engineering input")
    return out


def _bom(spec: dict) -> list[dict]:
    """Bill of material from the resolved spec rows that name real hardware.

    A row the engineer typed in by hand is always kept, whatever it names: they
    put it on the specification deliberately, and silently dropping it because
    it did not match a hardware keyword would lose stated information.
    """
    keep = ("blower", "filter", "pump", "motor", "tank", "nozzle", "demister",
            "illumination", "control panel", "duct")
    out = []
    for row in spec.get("technical_details") or []:
        label = str(row.get("label", ""))
        value = str(row.get("value", ""))
        if value.strip().lower() in ("", "to be determined"):
            continue
        if row.get("manual") or any(k in label.lower() for k in keep):
            out.append({"item": label, "spec": value, "origin": row.get("origin")})
    return out


def _design_data(spec: dict, bom: list[dict]) -> list[dict]:
    """The duty and construction rows: what the equipment is RATED for.

    A PARTITION of the resolved specification, not a selection. `_bom` takes the
    rows that name hardware; this takes everything else that resolved, so each
    value appears on the sheet exactly once and none is silently dropped. A TBD
    is excluded because the sheet already schedules it separately — printing it
    in both places would read as two different gaps.

    Nothing is computed here. Every value was resolved by the engineering engine
    and is reproduced verbatim.
    """
    in_bom = {str(r.get("item", "")) for r in bom}
    out = []
    for row in spec.get("technical_details") or []:
        label = str(row.get("label", ""))
        value = str(row.get("value", "")).strip()
        if not label or label in in_bom:
            continue
        if row.get("origin") == "tbd" or value.lower() in ("", "to be determined"):
            continue
        out.append({"label": label, "value": value, "origin": row.get("origin")})
    return out


# What this machine is rated FOR, taken from the spec's own rows. Used in the
# title block so a GA says which wet scrubber it is, not merely that it is one.
_DUTY_LABELS = ("exhaust airflow", "air volume", "airflow", "exhaust air volume",
                "heating capacity", "filter area", "track length")


def _duty(spec: dict) -> str:
    for needle in _DUTY_LABELS:
        for row in spec.get("technical_details") or []:
            label = str(row.get("label", "")).lower()
            value = str(row.get("value", "")).strip()
            if needle in label and value and value.lower() != "to be determined":
                return f"{row['label']}: {value}"[:40]
    return ""


def compose(spec: dict, sheet_size: str = sheet.DEFAULT_SIZE,
            client: str = "", ref: str = "", drawn_by: str = "",
            title_block: Optional[dict] = None,
            revisions: Optional[list] = None,
            drawing_type: str = "ga") -> tuple[Canvas, dict[str, Any]]:
    """Build the sheet and return BOTH the canvas and the drawing package.

    The canvas is what the non-SVG exporters (DXF, PDF) need — they consume the
    same shape list the SVG is emitted from, so an exported drawing can never
    drift from the one on screen.
    """
    size = sheet_size if sheet_size in sheet.SHEET_SIZES else sheet.DEFAULT_SIZE
    sw, sh = sheet.SHEET_SIZES[size]
    canvas = Canvas(sw, sh)

    geom = spec.get("geometry") or {}
    env = geom.get("envelope_mm") or {}
    rows = spec.get("technical_details") or []
    category = spec.get("category") or ""
    label = spec.get("category_label") or category.replace("_", " ").title() or "Equipment"

    sheet.frame(canvas, sw, sh)
    sheet.column_divider(canvas, sw, sh)
    sheet.header(canvas, sw, f"{label} - General Arrangement",
                 "Deterministic drawing generated from the engineering specification")

    ax, ay, aw, ah = sheet.drawing_area(sw, sh)
    scale = views.choose_scale(env, aw, ah)
    placed = views.layout(env, ax, ay, aw, ah, scale, drawing_type)

    # WHICH OF THE THREE STATES THIS SHEET IS. Decided from the resolved
    # envelope, never from equipment type, so every category behaves the same.
    gstate = states.classify(env)
    # A sheet with a resolved axis that still places no view is PARTIAL, not
    # schematic: the dimension exists, it simply does not complete a view (a
    # height with no length draws nothing in third angle). Saying "schematic"
    # there would discard a real engineered number.
    schematic = not placed

    legend: list = []
    if placed:
        labels = _dim_labels(env, str(geom.get("equipment_type") or ""))
        for v in placed:
            # A view that shows the machine's insides is a SECTION, and saying
            # so is more correct than calling it an elevation — the caption
            # comes from the glyph's own declaration, never from a guess here.
            views.draw_view(canvas, v, labels,
                            caption=symbols.view_caption(category, v.key, v.label))
        legend = symbols.draw_components(canvas, category,
                                         {v.key: v for v in placed}, rows)
        if gstate.state == states.PARTIAL:
            _partial_banner(canvas, ax, ay, aw, gstate, drawing_type, placed)
    else:
        # STATE 3. A preliminary schematic, not an empty sheet: the reader still
        # gets the machine, the reason, and what to send back. Nothing here
        # asserts a size — see `schematic.py` for why that holds.
        placed = schematic_mod.layout(ax, ay, aw, ah)
        schematic_mod.draw(canvas, placed, ax, ay, aw, ah)
        # The glyph still runs. Its views carry model_w/model_h of None, so
        # every routine needing true millimetres disables itself and what is
        # left is the equipment SYMBOL — which is information we genuinely have.
        legend = symbols.draw_components(canvas, category,
                                         {v.key: v for v in placed}, rows)
        # The COMPLETE schedule of what is missing, in the band the nominal
        # views deliberately left free. On this sheet it is the content.
        table_top = max(v.y + v.h for v in placed) + 26.0
        sheet.unresolved_table(canvas, ax, table_top, aw,
                               states.unresolved(env, rows), ay + ah - 2.0)

    tbd = _tbd_items(spec)
    # The same gaps as `tbd`, but classified and carrying the action that
    # clears each one. `tbd` stays as it was because the agent summary and the
    # studio both read it; this is the richer form the sheet schedules.
    unresolved = states.unresolved(env, rows)
    bom = _bom(spec)
    data = _design_data(spec, bom)
    key_dims = _key_dimensions(spec)
    # Reserve the strip the revision block occupies so the column stops above it
    # rather than printing through it.
    reserve = (4.4 * len(revisions[-3:]) + 4.0) if revisions else 0.0
    # ON A SCHEMATIC SHEET the drawing area already carries the COMPLETE
    # schedule with the action that clears each row, so repeating a shorter,
    # actionless copy in the side column says the same thing twice and reads as
    # two different lists that happen to agree.
    sheet.side_column(canvas, sw, sh, legend, STANDING_NOTES,
                      [] if schematic else tbd, bom, data, reserve, key_dims)
    # Anything the caller states wins; everything else is derived. The block
    # still invents nothing — an unstated field simply keeps its default.
    info = {
        "title": f"{label} - GA",
        # Never invented: an unknown client is stated as unknown, in the
        # wording a real title block uses.
        "client": client or "TO BE CONFIRMED",
        "ref": ref or f"VT/GA/{date.today():%y%m%d}/DRAFT",
        "scale": f"1:{scale}" if not schematic else "NTS",
        "size": size,
        "units": "mm",
        "date": f"{date.today():%d-%m-%Y}",
        "drawn": drawn_by or "Vitech AI",
        "checked": "",
        "rev": "0",
        # The status is the sheet's own claim about itself. A schematic that
        # said "DRAFT" alongside a normal GA would be indistinguishable from
        # one at a glance, which is exactly the confusion to prevent.
        # ABBREVIATED because a title-block cell is ~13 mm wide and the full
        # word only fits by shrinking below a legible drafting size. "PRELIM"
        # is the ordinary drafting abbreviation, and nothing is lost: the sheet
        # carries "PRELIMINARY SCHEMATIC - NOT FOR FABRICATION" in bold across
        # the drawing area, and the payload's `state` is the unabbreviated form.
        "status": "PRELIM" if schematic else "DRAFT",
    }
    info.setdefault("duty", _duty(spec))
    info.update({k: v for k, v in (title_block or {}).items() if str(v or "").strip()})
    sheet.title(canvas, sw, sh, info)
    sheet.revision_block(canvas, sw, sh, revisions or [])

    present = canvas.layers_present()
    return canvas, {
        "ok": True,
        "category": category,
        "category_label": label,
        "svg": canvas.svg(),
        "scale": f"1:{scale}" if not schematic else "NTS",
        "scale_divisor": scale,
        "sheet_size": size,
        "sheet_mm": {"width": sw, "height": sh},
        "envelope_mm": env,
        "ready": bool(geom.get("ready")),
        "views": [{"key": v.key, "label": v.label} for v in placed],
        "layers": [{"id": l, "label": LAYER_LABELS.get(l, l), "on": True} for l in present],
        "legend": [{"tag": t, "description": d} for t, d in legend],
        "bom": bom,
        "design_data": data,
        "key_dimensions": key_dims,
        "tbd": tbd,
        # The state, and the unresolved schedule with the action that clears
        # each row, so every consumer (studio, agent, PDF) can say the same
        # thing about the same sheet rather than each inferring it.
        "state": gstate.state,
        "state_label": gstate.label,
        "state_notes": list(gstate.notes),
        "unresolved": unresolved,
        "missing_axes": list(gstate.missing),
        "notes": STANDING_NOTES + list(gstate.notes),
        "title_block": info,
        "drawing_markdown": _markdown(label, env, scale, placed, tbd, size),
    }


def build_drawing(spec: dict, sheet_size: str = sheet.DEFAULT_SIZE,
                  client: str = "", ref: str = "", drawn_by: str = "",
                  title_block: Optional[dict] = None,
                  revisions: Optional[list] = None,
                  drawing_type: str = "ga") -> dict[str, Any]:
    """Resolved spec -> GA drawing package.

    Returns svg, the layer list the studio toggles, the chosen scale, the BOM,
    the TBD schedule and a short markdown summary for the agent to narrate.
    """
    return compose(spec, sheet_size, client, ref, drawn_by, title_block,
                   revisions, drawing_type)[1]


def _markdown(label: str, env: dict, scale: int, placed: list, tbd: list,
              size: str) -> str:
    """Short human summary for the agent. The CANVAS carries the drawing, so
    this stays a summary — never the raw SVG."""
    L = [f"**{label} — General Arrangement (DRAFT)**", ""]
    dims = " x ".join(str(env.get(a)) for a in ("length", "width", "height")
                      if env.get(a))
    if dims:
        L.append(f"Envelope: {dims} mm")
    L.append(f"Sheet {size}, scale {'1:' + str(scale) if placed else 'NTS'}, "
             f"{len(placed)} view(s): {', '.join(v.label.lower() for v in placed) or 'none'}")
    if tbd:
        L += ["", f"**{len(tbd)} item(s) to be determined:**"]
        L += [f"- {t}" for t in tbd[:8]]
        if len(tbd) > 8:
            L.append(f"- ... and {len(tbd) - 8} more")
    L += ["", "_Engineer-reviewed draft — not released for construction._"]
    return "\n".join(L)
