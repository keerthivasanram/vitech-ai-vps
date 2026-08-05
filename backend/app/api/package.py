"""The engineering package: many documents resolved from ONE analysis."""
from fastapi import APIRouter
from ..agent_router import prepare as _prepare
from ..quotation import build_quotation
from ..understand import understand
from fastapi import Body
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from .support import _named_requirement, _spec_bom, _spec_for_drawing, _spec_geometry, _spec_markdown, _spec_text, _title_block, _tool_q

router = APIRouter()


def _build_package(payload: dict):
    """Resolve ONCE, then compose every document in the package from that result.

    The single resolution is the point: the specification, the drawing, the BOM,
    the quotation and the review all read the same analysis, so they cannot
    disagree with each other. Returns (package, error_response).
    """
    from ..package import builder
    from ..drawing.drawing_service import build_drawing

    q = _tool_q(payload)
    if not _named_requirement(q):
        return None, {"ok": False, "need_requirement": True,
                      "message": ("No equipment requirement was given. Ask the user WHICH "
                                  "equipment and its size before building a package. Do NOT "
                                  "invent any equipment or number the user did not state.")}

    hits, a, _ = _prepare(q, top_k=8, history=[])

    # The specification, exactly as `/api/tools/spec` renders it, so the package
    # carries the same document the agent and the studio show.
    spec_resp = {
        "category": a.get("category"),
        "category_label": a.get("category_label"),
        "mode": a.get("spec_mode"),
        "confidence_pct": a.get("confidence_pct"),
        "confidence_label": a.get("confidence_label"),
        "given_data": a.get("given_data") or [],
        "technical_details": [
            {"label": t.get("label"), "value": t.get("value"),
             "origin": t.get("origin_label") or t.get("origin"),
             "source": t.get("source"), "reason": t.get("reason")}
            for t in (a.get("technical_details") or [])
        ],
        "validation": a.get("validation") or [],
        "release": a.get("release") or {},
    }

    geometry = _spec_geometry(a)
    drawing_spec = _spec_for_drawing(q)
    options = {"sheet_size": str(payload.get("sheet_size") or "A3"),
               "client": str(payload.get("client") or ""),
               "ref": str(payload.get("ref") or ""),
               "drawn_by": str(payload.get("drawn_by") or ""),
               "title_block": _title_block(payload)}
    drawing = build_drawing(drawing_spec, **options)
    # Carried so the exporter can re-compose the identical sheet for DXF/PDF
    # rather than opening a second, drifting rendering path.
    drawing["_source"] = {"spec": drawing_spec, "options": options}

    quote = build_quotation(a, dict(understand(q).parameters)) or None

    pkg = builder.build(
        a, question=q, hits=hits, drawing=drawing, bom=_spec_bom(a),
        quotation=quote, geometry=geometry,
        spec_markdown=_spec_markdown(spec_resp) or _spec_text(a),
        revision=str(payload.get("revision") or "0"),
        project=str(payload.get("project") or payload.get("title") or ""),
        client=str(payload.get("client") or ""),
        ref=str(payload.get("ref") or ""),
        drawn_by=str(payload.get("drawn_by") or ""),
    )
    return pkg, None


@router.post("/api/package", operation_id="generate_engineering_package")
def package_build(payload: dict = Body(...)):
    """Requirement -> the complete engineering package, as structured data.

    Seven documents (requirement summary, specification, GA drawing, BOM,
    quotation, assumptions, review) plus the traceability and cross-reference
    that tie them together. Each carries its own revision and confidence.
    """
    pkg, err = _build_package(payload)
    if err:
        return err
    # `_source` is how the exporter re-composes the identical sheet; it is an
    # internal detail (and a second copy of the whole spec), so it never leaves
    # the process. The SVG is large and is for the canvas, so it is opt-in.
    drop = {"_source"} if payload.get("include_svg") else {"_source", "svg"}
    return {**pkg, "drawing": {k: v for k, v in (pkg.get("drawing") or {}).items()
                               if k not in drop}}


@router.post("/api/package/export")
def package_export(payload: dict = Body(...)):
    """The same package as a downloadable project folder (.zip), or written to disk.

    `write: true` also organises it under PACKAGE_DIR, which is what "generated
    outputs are filed automatically" means in practice.
    """
    from ..package import export as pkg_export

    pkg, err = _build_package(payload)
    if err:
        return JSONResponse(err, status_code=400)

    if payload.get("write"):
        return pkg_export.write_package(pkg, payload.get("root") or None)

    data, name = pkg_export.zip_package(pkg)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
