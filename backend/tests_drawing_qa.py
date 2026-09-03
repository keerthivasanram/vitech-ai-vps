"""Drawing QA gate: audit every sheet the engine can produce.

This is `app/drawing/qa.py` run as a suite. It builds each category in each
drawing state, at both sheet sizes, and fails on anything the audit reports.

WHY A GATE AND NOT A REPORT. Every drawing defect this engine has shipped was
invisible in the source and obvious on the paper, and each was found by a person
rendering one sheet and looking at it. That does not scale to fourteen
categories times three states times two sheet sizes, and it never catches the
sheet nobody thought to render. The audit reads the finished canvas and asks
what a checker would ask.

SPARSE VIEWS ARE DECLARED, NOT SUPPRESSED. Some views are legitimately thin —
a duct seen end-on IS its bore, and drawing more would be decoration. Those are
listed below WITH THEIR REASON, so the exception is reviewable. Any view that
becomes thin without being on this list fails, which is the behaviour that makes
the check worth having.
"""
import sys

from app.drawing import qa, states
from app.drawing.symbols import SYMBOLS

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# (category, view) -> why this view is thin AND correct.
SPARSE_BY_DESIGN = {
    ("conveyor", "side"):
        "an overhead conveyor seen end-on IS its track section and one hanger",
    ("ducting", "side"):
        "a duct run seen end-on IS its bore; there is nothing else to show",
}

# (sheet size, code) -> why this is an accepted consequence rather than a bug.
ACCEPTED_ON_SIZE = {
    ("A4", "schedule_truncated"):
        "A4 is 297x210 and these schedules need A3, which is the DEFAULT size. "
        "The rows that fit are printed, the sheet SAYS how many did not, and it "
        "names where the full list lives. The alternative - shrinking the type "
        "below the legible floor, or silently dropping rows - is worse. Note the "
        "UNRESOLVED schedule never truncates even here: it reserves its own "
        "notice line, which is why this stays a warning and not an error.",
}

ROWS = [
    {"label": "Illumination", "value": "40 W weatherproof LED 6 nos"},
    {"label": "Paint arresting filter", "value": "8 nos 600 x 600 x 50 mm"},
    {"label": "Blower motor (HP)", "value": "15"},
    {"label": "Blower airflow (CFM)", "value": "9000"},
    {"label": "Exhaust blower", "value": "CLP-4-15-14500"},
    {"label": "Zones", "value": "3"},
    {"label": "Conveyor", "value": "overhead 2 m/min"},
    {"label": "Exhaust duct", "value": "600 mm dia"},
    {"label": "Stages", "value": "5 stage"},
    {"label": "Tower diameter", "value": "750 mm"},
    {"label": "Insulation", "value": "100 mm rockwool"},
    {"label": "Capture point", "value": "5 nos"},
    {"label": "Blast media", "value": "steel grit"},
    {"label": "Solenoid valve", "value": "6 nos"},
    {"label": "Filter bags", "value": "48 nos"},
    {"label": "Rotary airlock", "value": "0.5 HP"},
    {"label": "Type", "value": "overhead chain"},
    {"label": "Heating source", "value": "electrical"},
    {"label": "Blower MOC", "value": "To be determined", "origin": "tbd"},
    # Composite powder-plant rows. Without them the powder glyph resolves no
    # stations and draws a bare arrow — which is CORRECT behaviour, so auditing
    # it would have reported the fixture's poverty as the glyph's defect.
    {"label": "Powder coating booth", "value": "inner size 3.0L x 2.0W x 2.5H",
     "parts": {"inner_size_m": "3.0L x 2.0W x 2.5H"}},
    {"label": "Curing oven", "value": "inner size 3.0L x 2.0W x 2.2H",
     "parts": {"inner_size_m": "3.0L x 2.0W x 2.2H"}},
    {"label": "Pretreatment", "value": "7 tank spray"},
    {"label": "Powder recovery", "value": "cyclone + cartridge"},
    {"label": "Material handling", "value": "overhead conveyor",
     "parts": {"track_length_m": "60"}},
]

ENVELOPES = {
    "full": {"length": 6000, "width": 3000, "height": 4000},
    "partial": {"length": 6000, "width": None, "height": 4000},
    "schematic": {"length": None, "width": None, "height": None},
}


def _allowed(cat: str, finding, size: str) -> bool:
    """True when a finding is a declared, reasoned exception."""
    if (size, finding.code) in ACCEPTED_ON_SIZE:
        return True
    if finding.code != "sparse_view":
        return False
    for (c, view), _reason in SPARSE_BY_DESIGN.items():
        if c == cat and f"{view} view" in finding.message:
            return True
    return False


total_findings = 0
for size in ("A3", "A4"):
    for state_name, env in ENVELOPES.items():
        for cat in sorted(SYMBOLS):
            spec = {"category": cat, "category_label": cat.replace("_", " ").title(),
                    "geometry": {"envelope_mm": env,
                                 "ready": all(v for v in env.values())},
                    "technical_details": ROWS}
            findings = [f for f in qa.audit(spec, sheet_size=size)
                        if not _allowed(cat, f, size)]
            total_findings += len(findings)
            check(not findings,
                  f"{size} {state_name:9} {cat:22} {qa.summarise(findings)}"
                  + ("" if not findings else "\n        " +
                     "\n        ".join(str(f) for f in findings[:4])))

# The audit must be able to FAIL, or it proves nothing. Each detector is
# exercised against a canvas built to trip it, because a suite of checks that
# have never fired is indistinguishable from a suite of checks that cannot.
from app.drawing.primitives import Canvas, Dim, Rect, Text
from app.drawing.style import L_COMPONENT, L_DIM, L_TEXT

_c = Canvas(420, 297); _c.add(Dim(0, 0, 100, 0, "600"))
check(len(qa._check_dims_true(_c, 50, False)) == 1,
      "detector fires: a dimension reading 600 across 5000 mm of geometry")
_c = Canvas(420, 297); _c.add(Dim(0, 0, 100, 0, "5000"))
check(not qa._check_dims_true(_c, 50, False),
      "detector is quiet: the same span dimensioned truthfully")
_c = Canvas(420, 297); _c.add(Dim(0, 0, 100, 0, "TBD"))
check(not qa._check_dims_true(_c, 50, False),
      "detector is quiet: a TBD claims nothing, so it cannot be untrue")

_c = Canvas(420, 297); _c.add(Text(10, 10, "TOO SMALL", L_TEXT, 1.4))
check(len(qa._check_text_legible(_c)) == 1, "detector fires: text below the legible floor")

_c = Canvas(420, 297)
_c.add(Text(50, 50, "5000", L_DIM, 2.2, "middle"), Text(51, 50, "3000", L_DIM, 2.2, "middle"))
check(len(qa._check_dim_overlap(_c)) == 1, "detector fires: two dimensions printed over each other")

_c = Canvas(420, 297); _c.add(Text(50, 50, "SECTION A-A", L_TEXT, 3.0, "middle", bold=True))
check(len(qa._check_section_planes(_c)) == 1,
      "detector fires: a section caption with no cutting plane")
_c.add(Text(10, 20, "A", L_TEXT, 3.0), Text(90, 20, "A", L_TEXT, 3.0))
check(not qa._check_section_planes(_c), "detector is quiet once the plane is marked")

for _txt, _sev in (("3 further item(s) listed in the specification - sheet space "
                    "exhausted", "error"),
                   ("... and 5 more unresolved item(s) - see specification", "error"),
                   ("... and 4 more item(s) - see BOM", "warning"),
                   ("... and 2 more (see specification)", "warning")):
    _c = Canvas(420, 297); _c.add(Text(10, 10, _txt, L_TEXT, 2.3))
    _f = qa._check_truncation(_c, {})
    check(len(_f) == 1 and _f[0].severity == _sev,
          f"detector fires on truncation wording {_txt[:28]!r} as {_sev}")

_c = Canvas(420, 297); _c.add(Rect(400, 10, 60, 20, L_COMPONENT, 0.3))
check(len(qa._check_bounds(_c, 420, 297, 12, 12, 220, 250)) == 1,
      "detector fires: geometry off the sheet")
_c = Canvas(420, 297); _c.add(Rect(260, 100, 30, 20, L_COMPONENT, 0.3))
check(len(qa._check_bounds(_c, 420, 297, 12, 12, 220, 250)) == 1,
      "detector fires: equipment inside the reserved notes column")

# Every declared exception must still BE an exception. A reason left in the list
# after the view was filled out is a stale excuse, and the next thin view hides
# behind it.
for (cat, view), reason in sorted(SPARSE_BY_DESIGN.items()):
    spec = {"category": cat, "category_label": cat,
            "geometry": {"envelope_mm": ENVELOPES["full"], "ready": True},
            "technical_details": ROWS}
    still = [f for f in qa.audit(spec)
             if f.code == "sparse_view" and f"{view} view" in f.message]
    check(bool(still),
          f"{cat}.{view} is still genuinely sparse, so its exception is not stale")

if FAILS:
    print(f"\n{len(FAILS)} DRAWING QA FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print(f"\nALL DRAWING QA PASS ({total_findings} unexplained findings)")
