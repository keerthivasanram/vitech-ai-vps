"""The 2D general-arrangement drawing studio endpoints."""
from fastapi import APIRouter
from fastapi import Body
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from .support import _named_requirement, _spec_for_drawing, _studio_spec, _title_block, _tool_q

router = APIRouter()


@router.get("/api/drawing/catalog")
def drawing_catalog():
    """Everything the Drawing Studio needs to build its form, as DATA.

    The UI does not hard-code equipment types or their input fields — it renders
    whatever this returns, so adding a category to `catalog.py` makes it
    selectable in the studio with no frontend change. Categories that carry a
    component glyph are flagged so the studio can show the depth on offer.
    """
    from ..catalog import CATEGORY_PROFILES
    from ..drawing import sheet
    from ..drawing.symbols import SYMBOLS

    from ..drawing import fields as fieldspec

    cats = []
    for key, profile in CATEGORY_PROFILES.items():
        req = fieldspec.describe(profile, "required_inputs")
        opt = fieldspec.describe(profile, "optional_inputs")
        # Categories specified by duty rather than size (dust collector,
        # conveyor, ducting) get optional overall-size inputs so the studio can
        # actually produce a dimensioned sheet; blank leaves them TBD.
        size = fieldspec.size_fields(profile)
        cats.append({
            "key": key,
            "label": profile.get("label") or key.replace("_", " ").title(),
            "has_symbols": key in SYMBOLS,
            "dimension_keys": (profile.get("dimension_keys") or []
                               or [f["key"] for f in size]),
            "fields": req + opt + size,
        })
    cats.sort(key=lambda c: (not c["has_symbols"], c["label"]))

    return {
        "categories": cats,
        # Which views the engine can produce. Third-angle GA is the default;
        # the others are the same engine with a restricted view set.
        "drawing_types": [
            {"key": "ga", "label": "General Arrangement (3 views)",
             "description": "Plan, front and side elevation in third angle"},
            {"key": "plan", "label": "Plan only",
             "description": "Footprint / layout view"},
            {"key": "elevation", "label": "Elevations only",
             "description": "Front and side elevation"},
        ],
        "sheet_sizes": [{"key": k, "label": f"{k} ({int(w)} x {int(h)} mm)"}
                        for k, (w, h) in sheet.SHEET_SIZES.items()],
        "default_sheet": sheet.DEFAULT_SIZE,
    }

@router.post("/api/drawing/render")
def drawing_render(payload: dict = Body(...)):
    """Studio entry point: explicit category + field values -> GA drawing.

    Distinct from the agent tool below, which parses a natural-language
    requirement. Here the studio has already collected structured inputs, so
    they are passed straight through as the requirement text the engine
    resolves — keeping ONE resolution path rather than a parallel one that
    could drift from the spec engine.
    """
    from ..drawing.drawing_service import build_drawing

    spec, question, err = _studio_spec(payload)
    if err:
        return err

    drawing = build_drawing(
        spec,
        sheet_size=str(payload.get("sheet_size") or "A3"),
        client=str(payload.get("client") or ""),
        ref=str(payload.get("ref") or ""),
        drawn_by=str(payload.get("drawn_by") or ""),
        title_block=_title_block(payload),
        revisions=payload.get("revisions") or [],
        drawing_type=str(payload.get("drawing_type") or "ga"),
    )
    drawing["requirement"] = question
    return drawing


@router.post("/api/drawing/export")
def drawing_export(payload: dict = Body(...)):
    """The same sheet as a downloadable SVG, DXF (CAD) or PDF (print).

    Takes either the studio's structured input (`category` + `values`) or a
    natural-language `question`, and rebuilds the drawing through the SAME
    resolver as `/api/drawing/render` — an export is never a second rendering
    path that could disagree with what the engineer approved on screen.
    """
    from ..drawing.drawing_service import compose
    from ..drawing import export as exporter

    fmt = str(payload.get("format") or "svg").lower().strip()
    if fmt not in ("svg", "dxf", "pdf"):
        return JSONResponse({"ok": False, "error": f"Unsupported format '{fmt}'."},
                            status_code=400)

    if payload.get("spec"):
        from ..drawing.spec_parser import parse_spec
        spec = parse_spec(str(payload["spec"]))
        if not spec:
            return JSONResponse(
                {"ok": False, "error": "That does not look like a generated specification."},
                status_code=400)
    elif payload.get("category"):
        spec, _, err = _studio_spec(payload)
        if err:
            return JSONResponse(err, status_code=400)
    else:
        q = _tool_q(payload)
        if not _named_requirement(q):
            return JSONResponse(
                {"ok": False, "error": "No equipment requirement was given."},
                status_code=400)
        spec = _spec_for_drawing(q)

    canvas, drawing = compose(
        spec,
        sheet_size=str(payload.get("sheet_size") or "A3"),
        client=str(payload.get("client") or ""),
        ref=str(payload.get("ref") or ""),
        drawn_by=str(payload.get("drawn_by") or ""),
        title_block=_title_block(payload),
        revisions=payload.get("revisions") or [],
        drawing_type=str(payload.get("drawing_type") or "ga"),
    )
    stem = (drawing.get("category_label") or "drawing").replace(" ", "-").lower()
    name = f"{stem}-GA.{fmt}"
    media, body = {
        "svg": ("image/svg+xml", drawing["svg"].encode("utf-8")),
        "dxf": ("application/dxf", exporter.to_dxf(canvas).encode("utf-8")),
        "pdf": ("application/pdf", exporter.to_pdf(canvas)),
    }[fmt]
    return Response(content=body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        # so the studio can show what it just downloaded without a second call
        "X-Drawing-Scale": str(drawing.get("scale") or ""),
        "X-Drawing-Tbd": str(len(drawing.get("tbd") or [])),
    })

@router.post("/api/drawing/from-spec")
def drawing_from_spec(payload: dict = Body(...)):
    """A pasted engineering specification -> its general-arrangement drawing.

    Draws THE specification the engineer is holding rather than re-resolving the
    original requirement, so every reviewed value and every accepted TBD carries
    through to the sheet unchanged.
    """
    from ..drawing.drawing_service import build_drawing
    from ..drawing.spec_parser import parse_spec

    text = str(payload.get("spec") or payload.get("question") or "").strip()
    if not text:
        return {"ok": False, "error": "Paste an engineering specification to draw."}
    spec = parse_spec(text)
    if not spec:
        return {"ok": False, "error": ("That does not look like a generated engineering "
                                       "specification. Paste the specification table, or "
                                       "describe the equipment and its size instead.")}

    drawing = build_drawing(
        spec,
        sheet_size=str(payload.get("sheet_size") or "A3"),
        client=str(payload.get("client") or ""),
        ref=str(payload.get("ref") or ""),
        drawn_by=str(payload.get("drawn_by") or ""),
        title_block=_title_block(payload),
        revisions=payload.get("revisions") or [],
        drawing_type=str(payload.get("drawing_type") or "ga"),
    )
    drawing["from_specification"] = True
    return drawing
