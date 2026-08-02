"""Orchestrator: a resolved specification becomes a 2D GA drawing.

`build_drawing(spec)` is the one entry point `/api/tools/drawing` calls. It is
pure and deterministic — the same spec always produces byte-identical SVG, which
is what makes the drawing engine golden-testable like the spec engine.

The LLM contributes nothing here. It receives `drawing_markdown` (a short human
summary) and the studio receives the SVG; neither the model nor the canvas ever
invents a dimension.
"""
from datetime import date
from typing import Any, Optional

from . import sheet, symbols, views
from .primitives import LAYER_LABELS, L_TEXT, Canvas, Text

# Stated on every sheet, because the component glyphs are schematic. Without
# this note a reader could mistake an indicative symbol for a set-out position.
STANDING_NOTES = [
    "All dimensions in millimetres unless noted otherwise.",
    "Component positions indicative; refer detailed GA for setting out.",
    "Engineer-reviewed draft - not released for construction.",
]


def _dim_labels(env: dict) -> dict:
    """Axis -> printed dimension text. A missing axis prints TBD, never a
    number, so the drawing cannot imply a dimension nobody has computed."""
    out = {}
    for axis in ("length", "width", "height"):
        v = env.get(axis)
        out[axis] = f"{int(v)}" if isinstance(v, (int, float)) and v else "TBD"
    return out


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
    sheet.header(canvas, sw, f"{label} - General Arrangement",
                 "Deterministic drawing generated from the engineering specification")

    ax, ay, aw, ah = sheet.drawing_area(sw, sh)
    scale = views.choose_scale(env, aw, ah)
    placed = views.layout(env, ax, ay, aw, ah, scale, drawing_type)

    legend: list = []
    if placed:
        labels = _dim_labels(env)
        for v in placed:
            views.draw_view(canvas, v, labels)
        legend = symbols.draw_components(canvas, category,
                                         {v.key: v for v in placed}, rows)
    else:
        # Nothing dimensionable. Say so on the sheet rather than drawing a box.
        canvas.add(Text(ax + aw / 2, ay + ah / 2,
                        "NO DIMENSIONED VIEWS - overall sizes not yet determined",
                        L_TEXT, 4.0, "middle", bold=True))
        canvas.add(Text(ax + aw / 2, ay + ah / 2 + 7.0,
                        "Supply the equipment dimensions to generate the general arrangement.",
                        L_TEXT, 2.6, "middle"))

    tbd = _tbd_items(spec)
    bom = _bom(spec)
    sheet.side_column(canvas, sw, sh, legend, STANDING_NOTES, tbd, bom)
    # Anything the caller states wins; everything else is derived. The block
    # still invents nothing — an unstated field simply keeps its default.
    info = {
        "title": f"{label} - GA",
        "client": client or "(to be completed)",
        "ref": ref or f"VT/GA/{date.today():%y%m%d}/DRAFT",
        "scale": f"1:{scale}" if placed else "NTS",
        "size": size,
        "units": "mm",
        "date": f"{date.today():%d-%m-%Y}",
        "drawn": drawn_by or "Vitech AI",
        "checked": "",
        "rev": "0",
        "status": "DRAFT",
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
        "scale": f"1:{scale}" if placed else "NTS",
        "scale_divisor": scale,
        "sheet_size": size,
        "sheet_mm": {"width": sw, "height": sh},
        "envelope_mm": env,
        "ready": bool(geom.get("ready")),
        "views": [{"key": v.key, "label": v.label} for v in placed],
        "layers": [{"id": l, "label": LAYER_LABELS.get(l, l), "on": True} for l in present],
        "legend": [{"tag": t, "description": d} for t, d in legend],
        "bom": bom,
        "tbd": tbd,
        "notes": STANDING_NOTES,
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
