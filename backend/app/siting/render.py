"""Compose the siting view: the photograph, the machine, and the caveats.

SVG rather than a pixel composite, for the same reason the GA engine emits SVG:
it is byte-stable, so the same inputs give the same file and the artifact digest
in `data/jobs/` stays meaningful; it stays sharp when someone prints it; and the
overlay remains separable from the photograph underneath, which matters because
**this is a photograph with an engineering claim drawn on top of it, and a
reader must always be able to tell which is which.**

The photo is embedded as a data URI so the sheet is one self-contained file that
survives being emailed - the same reason the GA sheet carries its own title
block instead of relying on a template.
"""
import base64
from typing import Optional

from .plan import Placement

# Deliberately not the drawing engine's palette. A GA sheet is black on white
# and reads as issued engineering; this is an indicative overlay on a
# photograph, and it should not be mistaken for one at a glance.
ACCENT = "#0d5a82"
FOOT = "#0d5a82"
CLEAR = "#c2410c"
INK = "#0f172a"
PAPER = "#ffffff"


def _poly(points, fill: str, stroke: str, width: float, dash: str = "",
          opacity: float = 1.0) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity}" '
            f'stroke="{stroke}" stroke-width="{width}"{d} />')


def _line(p1, p2, stroke: str, width: float, dash: str = "") -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
            f'stroke="{stroke}" stroke-width="{width}"{d} />')


def _text(x: float, y: float, s: str, size: float = 13, weight: str = "normal",
          fill: str = INK, anchor: str = "start") -> str:
    esc = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}">{esc}</text>')


def compose(photo_bytes: bytes,
            photo_mime: str,
            image_w: int,
            image_h: int,
            placement: Placement,
            title: str,
            equipment: str,
            fits: bool,
            problems: list[str],
            reference_note: str) -> str:
    """The siting sheet, as one self-contained SVG."""
    band = 132                     # caption band under the photograph
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{image_w}" '
           f'height="{image_h + band}" viewBox="0 0 {image_w} {image_h + band}">',
           f'<rect width="{image_w}" height="{image_h + band}" fill="{PAPER}"/>']

    b64 = base64.b64encode(photo_bytes).decode("ascii")
    out.append(f'<image x="0" y="0" width="{image_w}" height="{image_h}" '
               f'xlink:href="data:{photo_mime};base64,{b64}" '
               f'href="data:{photo_mime};base64,{b64}" />')

    # --- clearance first, so the machine sits on top of it -----------------
    if placement.clearance_px:
        out.append(_poly(placement.clearance_px, CLEAR, CLEAR, 2, dash="10 6",
                         opacity=0.10))

    # --- the machine -------------------------------------------------------
    out.append(_poly(placement.footprint_px, FOOT, FOOT, 3, opacity=0.22))
    if placement.top_px:
        for base, top in zip(placement.footprint_px, placement.top_px):
            out.append(_line(base, top, FOOT, 2.5))
        out.append(_poly(placement.top_px, FOOT, FOOT, 2.5, opacity=0.10))

    # --- the label ---------------------------------------------------------
    # Anchored to the NEAREST corner (largest image y) so it sits at the front
    # of the machine rather than behind it, and CLAMPED into the frame. The
    # first version anchored to the smallest y - which on a tall machine is a
    # TOP corner - and ran the caption off the right edge, where a reader would
    # have seen "Paint Booth 5 x 3 x 4 " and no unit. A clipped engineering
    # value looks like a wrong one; that lesson is already written into
    # `sheet._wrap`, and it applies here too.
    size = f"{placement.length_m:g} x {placement.width_m:g}"
    if placement.height_m and placement.top_px:
        size += f" x {placement.height_m:g}"
    caption = f"{equipment}  {size} m"
    box_w = len(caption) * 7.4 + 20
    near = max(placement.footprint_px, key=lambda p: p[1])
    lx = min(max(6.0, near[0] - box_w / 2), image_w - box_w - 6.0)
    ly = min(near[1] + 30, image_h - 10)
    out.append(f'<rect x="{lx:.1f}" y="{ly - 20:.1f}" width="{box_w:.0f}" '
               f'height="26" rx="3" fill="{ACCENT}" fill-opacity="0.92"/>')
    out.append(_text(lx + 10, ly - 2, caption, 13, "bold", PAPER))

    # --- caption band ------------------------------------------------------
    y = image_h + 26
    out.append(_line((0, image_h), (image_w, image_h), "#cbd5e1", 1))
    out.append(_text(18, y, title, 15, "bold"))
    out.append(_text(18, y + 20, reference_note, 11.5, "normal", "#475569"))

    verdict = ("FITS the measured floor area" if fits
               else "DOES NOT FIT: " + "; ".join(problems))
    out.append(_text(18, y + 40, verdict, 12.5, "bold",
                     "#166534" if fits else "#b91c1c"))

    notes = list(placement.notes)
    # THE STANDING CAVEAT IS RESERVED FIRST, never last. The same lesson as the
    # GA sheet's standing notes: drawn last, it is the first thing a crowded
    # sheet drops - and losing "this is not a survey" from a photo-realistic
    # overlay is a golden-rule-#3 failure, not a layout nicety.
    caveat = ("INDICATIVE SITING VIEW - not a survey. Scale is derived from the "
              "marked reference only; position is the engineer's, not the platform's.")
    out.append(_text(18, y + 78, caveat, 11, "bold", "#b45309"))
    for i, n in enumerate(notes[:2]):
        out.append(_text(18, y + 58 + i * 15, n[:150], 11, "normal", "#475569"))

    out.append("</svg>")
    return "\n".join(out)
