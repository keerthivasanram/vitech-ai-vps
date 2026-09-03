"""Per-glyph byte digest — the safety net for a drawing refactor.

WHY THIS EXISTS. `tests_api_contract.py` fingerprints only TWO of the fourteen
equipment glyphs (the booth and the scrubber), so the other twelve can be
changed, or broken, with every suite still green. This renders every category's
GA sheet from one fixed spec and digests the SVG, which is what lets a change
meant to be purely presentational be PROVEN byte-identical rather than assumed.

It is a TOOL, not a test — it takes a baseline you record deliberately, so it
is not part of the suite run and CI does not gate on it.

    .venv/bin/python tools_glyph_digest.py             -> print digests
    .venv/bin/python tools_glyph_digest.py --save F    -> record a baseline
    .venv/bin/python tools_glyph_digest.py --diff F    -> compare, exit 1 on any change

TYPICAL USE: `--save` before touching `app/drawing/`, `--diff` after. A glyph
that moves when you expected nothing to is the whole point; a glyph that moves
when you MEANT it to should then be RENDERED and looked at, because a digest
says something changed and never says whether it got better.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.drawing.drawing_service import build_drawing
from app.drawing.symbols import SYMBOLS

# Rows chosen to light up as much of each glyph as possible: counts, models,
# doors, ducts, motors. A thin fixture would digest a nearly empty sheet and
# prove nothing about the components being migrated.
ROWS = [
    {"label": "Filters", "value": "9 (dry)"},
    {"label": "Paint arresting filter", "value": "12 nos 600 x 600"},
    {"label": "Exhaust blower", "value": "CLP-4-15-14500"},
    {"label": "Exhaust blower (nos)", "value": "2"},
    {"label": "Blower motor (HP)", "value": "15"},
    {"label": "Blower airflow (CFM)", "value": "9000"},
    {"label": "Exhaust airflow", "value": "21600 m3/h"},
    {"label": "Illumination", "value": "40 W weatherproof LED 18 nos"},
    {"label": "Exhaust duct", "value": "1800 mm dia"},
    {"label": "Booth type", "value": "dry filter cross draft"},
    {"label": "Construction material", "value": "MS 18 SWG sheet"},
    {"label": "Tower diameter", "value": "750 mm"},
    {"label": "Operating temperature", "value": "180 C"},
    {"label": "Conveyor speed", "value": "2 m/min"},
    {"label": "Cleaning system", "value": "pulse jet 6 nos solenoid"},
    {"label": "Access door", "value": "2 nos"},
    {"label": "Blower MOC", "value": "To be determined", "origin": "tbd"},
]

CASES = {}
for cat in sorted(SYMBOLS):
    CASES[cat] = {
        "category": cat, "category_label": cat.replace("_", " ").title(),
        "geometry": {"envelope_mm": {"length": 6000, "width": 3000, "height": 4000},
                     "ready": True},
        "technical_details": ROWS,
    }
# A narrow machine exercises the small-view collision paths the previous
# session found defects in (labels colliding on a ~30 mm wide tower).
CASES["wet_scrubber_narrow"] = {
    "category": "wet_scrubber", "category_label": "Wet Scrubber",
    "geometry": {"envelope_mm": {"length": 750, "width": 750, "height": 4000},
                 "ready": True},
    "technical_details": ROWS,
}
# No dimensions at all: the honest-gap path.
CASES["oven_no_dims"] = {
    "category": "hot_air_oven", "category_label": "Hot Air Oven",
    "geometry": {"envelope_mm": {"length": None, "width": None, "height": None},
                 "ready": False},
    "technical_details": [{"label": "Chamber", "value": "To be determined",
                           "origin": "tbd"}],
}


def digests():
    out = {}
    for name, spec in CASES.items():
        d = build_drawing(spec)
        svg = d["svg"]
        out[name] = {
            "sha": hashlib.sha256(svg.encode()).hexdigest()[:16],
            "bytes": len(svg),
            "legend": len(d["legend"]),
            "views": len(d.get("views", []) or []),
        }
    return out


if __name__ == "__main__":
    now = digests()
    if "--save" in sys.argv:
        path = sys.argv[sys.argv.index("--save") + 1]
        json.dump(now, open(path, "w"), indent=1, sort_keys=True)
        print(f"saved {len(now)} digests -> {path}")
    elif "--diff" in sys.argv:
        path = sys.argv[sys.argv.index("--diff") + 1]
        was = json.load(open(path))
        moved = [k for k in now if was.get(k) != now[k]]
        for k in sorted(now):
            a, b = was.get(k), now[k]
            flag = "SAME " if a == b else "MOVED"
            extra = ""
            if a and a != b:
                extra = (f"  bytes {a['bytes']}->{b['bytes']}"
                         f"  legend {a['legend']}->{b['legend']}")
            print(f"{flag} {k:26} {b['sha']}{extra}")
        print(f"\n{len(now) - len(moved)}/{len(now)} byte-identical")
        sys.exit(1 if moved else 0)
    else:
        for k in sorted(now):
            v = now[k]
            print(f"{k:26} {v['sha']}  {v['bytes']:>7} bytes  "
                  f"legend {v['legend']:>2}  views {v['views']}")
