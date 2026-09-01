"""Place resolved equipment on a customer's site photograph.

The envelope comes from the SAME resolution the specification and the general
arrangement come from, so a siting view can never show a machine of a size the
spec does not describe. The scale comes from a rectangle the engineer measured
and marked. Nothing in this path invents a dimension: if the requirement does
not resolve to an envelope, or no reference was marked, the endpoint says so.
"""
import base64

from fastapi import APIRouter, Body

from ..observability import jobs as _jobs, trace as _obs
from ..siting.homography import SolveError, from_rectangle, height_scale
from ..siting.plan import fits_within, place
from ..siting.render import compose
from .support import _named_requirement, _spec_for_drawing, _spec_geometry, _tool_q

router = APIRouter()

_MAX_PHOTO_BYTES = 12 * 1024 * 1024


def _need(message: str, **extra) -> dict:
    return {"ok": False, "message": message, **extra}


@router.post("/api/siting/place", operation_id="place_equipment_on_site")
def place_on_site(payload: dict = Body(...)):
    """Photograph + marked reference + requirement -> an indicative siting view.

    Required in the payload:
      photo_base64, photo_mime, image_w, image_h
      reference: {points: [[x,y] x4 near-left, near-right, far-right, far-left],
                  width_m, depth_m}
      requirement (or an explicit envelope: {length_m, width_m, height_m})
    Optional:
      vertical: {base: [x,y], top: [x,y], height_m}   -> without it, footprint only
      position: {x_m, y_m, rotation_deg, clearance_m}
    """
    photo_b64 = payload.get("photo_base64") or ""
    if not photo_b64:
        return _need("No photograph was supplied.")
    try:
        photo = base64.b64decode(photo_b64, validate=True)
    except Exception:
        return _need("The photograph could not be decoded (expected base64).")
    if len(photo) > _MAX_PHOTO_BYTES:
        return _need(f"The photograph exceeds {_MAX_PHOTO_BYTES // (1024*1024)} MB.")

    ref = payload.get("reference") or {}
    points = ref.get("points") or []
    try:
        marks = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        marks = []
    if len(marks) != 4:
        return _need("Mark the four corners of a floor rectangle you have measured. "
                     "A photograph carries no scale until one real dimension is stated.",
                     need_reference=True)
    try:
        hom = from_rectangle(marks, float(ref.get("width_m") or 0),
                             float(ref.get("depth_m") or 0))
    except (SolveError, TypeError, ValueError) as exc:
        return _need(f"The marked reference could not be used: {exc}", need_reference=True)

    # --- the envelope: resolved, or explicitly given ------------------------
    env = payload.get("envelope") or {}
    equipment = str(payload.get("equipment") or "").strip()
    if not env:
        q = _tool_q(payload)
        if not _named_requirement(q):
            return _need("No equipment requirement was given. Say WHICH equipment and its "
                         "size, or pass an explicit envelope.", need_requirement=True)
        _obs.note(tool="place_equipment_on_site")
        spec = _spec_for_drawing(q)
        geom = _spec_geometry(spec) or {}
        mm = geom.get("envelope_mm") or {}
        if not (mm.get("length") and mm.get("width")):
            return _need("That requirement does not resolve to a footprint, so it cannot be "
                         "placed on a photograph. The specification will say which dimension "
                         "is outstanding.", envelope_mm=mm)
        env = {"length_m": mm["length"] / 1000.0, "width_m": mm["width"] / 1000.0,
               "height_m": (mm.get("height") or 0) / 1000.0 or None}
        equipment = equipment or spec.get("equipment") or "Equipment"

    equipment = equipment or "Equipment"

    # --- heights, only with a marked vertical -------------------------------
    hs = None
    vert = payload.get("vertical") or {}
    if vert.get("base") and vert.get("top") and vert.get("height_m"):
        try:
            hs = height_scale(hom, (float(vert["base"][0]), float(vert["base"][1])),
                              (float(vert["top"][0]), float(vert["top"][1])),
                              float(vert["height_m"]))
        except (TypeError, ValueError, IndexError):
            hs = None

    pos = payload.get("position") or {}
    ref_w = float(ref.get("width_m"))
    ref_d = float(ref.get("depth_m"))
    try:
        pl = place(hom,
                   length_m=float(env["length_m"]), width_m=float(env["width_m"]),
                   height_m=(float(env["height_m"]) if env.get("height_m") else None),
                   origin_m=(float(pos.get("x_m", ref_w / 2)),
                             float(pos.get("y_m", ref_d / 2))),
                   rotation_deg=float(pos.get("rotation_deg", 0)),
                   clearance_m=float(pos.get("clearance_m", 0)),
                   height_scale=hs)
    except (SolveError, KeyError, TypeError, ValueError) as exc:
        return _need(f"The machine could not be placed: {exc}")

    fits, problems = fits_within(hom, pl, ref_w, ref_d)

    job = _jobs.create("siting", requirement=_tool_q(payload) or equipment)
    size = f"{pl.length_m:g} x {pl.width_m:g}" + (f" x {pl.height_m:g}" if pl.height_m else "")
    svg = compose(photo, str(payload.get("photo_mime") or "image/jpeg"),
                  int(payload.get("image_w") or 0), int(payload.get("image_h") or 0), pl,
                  title=f"{equipment} {size} m - indicative siting",
                  equipment=equipment, fits=fits, problems=problems,
                  reference_note=(f"Scale from a marked {ref_w:.2f} x {ref_d:.2f} m floor "
                                  f"rectangle" + ("; heights from a "
                                  f"{float(vert['height_m']):.2f} m vertical reference."
                                  if hs else "; no vertical reference marked.")))
    _jobs.finish(job, equipment=equipment, summary={"fits": fits, "size_m": size})

    return {"ok": True, "svg": svg, "fits": fits, "problems": problems,
            "notes": list(pl.notes), "equipment": equipment,
            "envelope_m": {"length": pl.length_m, "width": pl.width_m,
                           "height": pl.height_m},
            "height_shown": pl.top_px is not None,
            "siting_markdown": "\n".join([
                f"**INDICATIVE SITING — {equipment}**", "",
                f"Envelope: {size} m",
                f"Placed at ({pl.origin_m[0]:g}, {pl.origin_m[1]:g}) m on the marked floor, "
                f"rotated {pl.rotation_deg:g}°"
                + (f", with {pl.clearance_m:g} m clearance" if pl.clearance_m else ""),
                "",
                ("**FITS** the measured floor area." if fits
                 else "**DOES NOT FIT** — " + "; ".join(problems)),
                "",
                *[f"- {n}" for n in pl.notes],
                "",
                "This is an indicative view for discussion, not a survey.",
            ])}
