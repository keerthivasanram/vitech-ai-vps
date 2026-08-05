"""Customer-facing document rendering: quotation, specification, data sheets."""
from fastapi import APIRouter
from ..datasheet_pdf import available_forms
from ..datasheet_pdf import render_datasheet_pdf
from ..datasheet_pdf import resolve_form
from ..quotation_pdf import render_quotation_pdf
from ..specification_pdf import render_specification_pdf
from fastapi import Body
from fastapi import HTTPException
from fastapi.responses import Response

router = APIRouter()


@router.post("/api/quotation/pdf")
def quotation_pdf(quote: dict = Body(...)):
    """Render a quotation object (from a quotation-intent response) to a
    downloadable Vitech-format PDF. Deterministic — adds no numbers of its own."""
    data = render_quotation_pdf(quote)
    ref = str(quote.get("ref") or "quotation").replace(" ", "_")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{ref}.pdf"'})


@router.post("/api/specification/pdf")
def specification_pdf(spec: dict = Body(...)):
    """Render a specification object (from a generate_specification response, as
    surfaced by the chat) to a downloadable Vitech-format PDF. Deterministic —
    it prints the engineered rows, adding no numbers of its own. Accepts either
    the structured payload or a {text: "..."} fallback."""
    data = render_specification_pdf(spec)
    name = str(spec.get("category_label") or "specification").replace(" ", "_")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}_specification.pdf"'})


@router.get("/api/datasheet/forms", operation_id="list_datasheets")
def datasheet_forms():
    """The enquiry data sheets that can be generated, for a UI picker."""
    return {"forms": available_forms()}


@router.post("/api/datasheet/pdf")
def datasheet_pdf(payload: dict = Body(...)):
    """Render a Vitech enquiry DATA SHEET (the customer requirement-capture
    form) as a downloadable PDF, blank or prefilled.

    Body: {"category": "paint_booth", "prefill": {"<label>": "<value>", ...}}
    A bare label fills its first occurrence; qualify with "<section>::<label>"
    to reach a repeated one. Nothing is inferred — only supplied values print.
    """
    category = payload.get("category") or payload.get("equipment_type") or ""
    key = resolve_form(category)
    if key is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data sheet for {category!r}. Available: "
                   + ", ".join(f["category"] for f in available_forms()))
    prefill = payload.get("prefill") or {}
    if not isinstance(prefill, dict):
        raise HTTPException(status_code=422, detail="prefill must be an object")
    data = render_datasheet_pdf(key, prefill)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{key}_data_sheet.pdf"'})
