"""Bill of materials from the resolved engineering specification."""
from fastapi import APIRouter
from fastapi import Body
from ..observability import jobs as _jobs, trace as _obs
from .support import _named_requirement, _spec_for_drawing, _studio_spec, _tool_q

router = APIRouter()


@router.post("/api/bom", operation_id="generate_bom")
def bom_endpoint(payload: dict = Body(...)):
    """Requirement (or a pasted specification) -> bill of materials.

    Derived from the SAME resolved specification the spec and the drawing come
    from, so the three documents describe one machine. Quantities and weights
    are engineering; a line is priced only where the client's own rate card
    reaches it, and the total says plainly that it is partial.
    """
    from ..bom import build_bom
    from ..drawing.spec_parser import looks_like_spec, parse_spec

    text = str(payload.get("spec") or "").strip()
    if text and looks_like_spec(text):
        spec = parse_spec(text)
        if not spec:
            return {"ok": False, "error": "That specification could not be read."}
        return build_bom(spec)

    if payload.get("category"):
        spec, _, err = _studio_spec(payload)
        if err:
            return err
        return build_bom(spec)

    q = _tool_q(payload)
    if not _named_requirement(q):
        return {"ok": False, "need_requirement": True,
                "message": ("No equipment requirement was given. Ask the user WHICH equipment "
                            "and its size before listing any material.")}
    _obs.note(tool="generate_bom")
    job = _jobs.create("bom", requirement=q)
    bom = build_bom(_spec_for_drawing(q))
    _jobs.finish(job, equipment=bom.get("category") or "",
                 summary={"lines": len(bom.get("lines") or []),
                          "uncosted": len(bom.get("uncosted") or [])})
    return bom
