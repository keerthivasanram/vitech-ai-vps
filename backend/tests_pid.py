"""Guards for the process train model (`app/engineering/process_model.py`,
`app/engineering/train_templates.py`).

The train is what a P&ID is drawn from: which equipment exists, what connects to
what, and what each line carries. Its contract is the spec engine's contract
applied to connectivity — declared topology is a fact of the equipment type and
may be asserted, while every NUMBER on it must trace to a trusted spec row or
print TBD.

These tests pin that boundary, plus the two behaviours that are easy to get
silently wrong: a dropped node must never leave a dangling line, and a tag must
never move because some unrelated component failed to resolve.

Run after any change to either module, or after adding a template.
"""
import json
import os
import subprocess
import sys

from app.engineering import train_templates as tt
from app.engineering.process_model import (TRUSTED_ORIGINS, Attr,
                                           attr_from_row, resolve_train)
from app.engineering.train_templates import TRAIN_TEMPLATES, train_for

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# Rows as the engine really emits them for the platform's anchor scrubber case
# ("wet scrubber 800 cfm 750mm tower dia 4 nos"), captured 2026-09-10. Held as a
# literal so the model is testable without standing up the resolver — the same
# reason `tests_drawing.py` keeps BOOTH as a literal.
SCRUBBER_ROWS = [
    {"label": "Air volume cfm", "value": "800", "origin": "given"},
    {"label": "Air volume cmh", "value": "1359", "origin": "given"},
    {"label": "Scrubber chamber", "value": "SS-304 2mm", "origin": "consistent"},
    {"label": "Scrubber tank", "value": "SS-304 2mm", "origin": "reused"},
    {"label": "Spray nozzles (nos)", "value": "19", "origin": "rule"},
    {"label": "Spray nozzle material", "value": "SS-304", "origin": "reused"},
    {"label": "Pump capacity (HP)", "value": "1", "origin": "rule"},
    {"label": "Pump make", "value": "ANALA", "origin": "consistent"},
    {"label": "Eliminator / demister", "value": "PP 250mm", "origin": "reused"},
    {"label": "Tank capacity (litre)", "value": "300", "origin": "rule"},
    {"label": "Blower type", "value": "centrifugal", "origin": "consistent"},
    {"label": "Blower motor hp", "value": "3", "origin": "reused"},
    {"label": "Tower diameter (mm)", "value": "750", "origin": "given"},
    {"label": "Tower height (m)", "value": "4", "origin": "rule"},
]

BOOTH_ROWS = [
    {"label": "Type of paint booth", "value": "Dry Filter Cross Draft", "origin": "rule"},
    {"label": "Exhaust airflow", "value": "10800 m3/h", "origin": "rule"},
    {"label": "Inlet air volume", "value": "9720 m3/h", "origin": "rule"},
    {"label": "Construction material", "value": "MS panels", "origin": "advisory"},
    {"label": "Paint arresting filter", "value": "9 nos 600 x 600 x 50 mm", "origin": "assumed"},
    {"label": "Air intake filter", "value": "10 micron velcro type", "origin": "reused"},
    {"label": "Dry scrubber", "value": "To be determined", "origin": "tbd"},
    {"label": "Exhaust ducts", "value": "500 mm dia, GI, 15.3 m/s transport velocity",
     "origin": "rule"},
    {"label": "Fire extinguishing system",
     "value": "Flameproof components, ABC extinguishers, Interlocked shutdown",
     "origin": "standard"},
]

GEO_TOWER = {"equipment_type": "vertical_spray_tower"}
scrub = train_for("wet_scrubber", SCRUBBER_ROWS, {}, GEO_TOWER)
booth = train_for("paint_booth", BOOTH_ROWS, {}, {})

# --- the anchor train resolves ---------------------------------------------
check(scrub.ok and scrub.template_id == "ws-vertical-spray-tower-v1",
      "the anchor scrubber resolves its declared template")
check(len(scrub.nodes) == 11 and len(scrub.streams) == 9,
      f"scrubber train is 11 nodes / 9 streams (got {len(scrub.nodes)}/{len(scrub.streams)})")
_tags = [n.tag for n in scrub.nodes]
check(_tags == ["XC-101", "SC-101", "DM-101", "SH-101", "TK-101", "STR-201",
                "P-101", "BL-101", "STK-101", "XC-102", "XC-103"],
      f"scrubber equipment tags are exactly as declared ({_tags})")
check([s.tag for s in scrub.streams] == ["L-101", "L-102", "L-103", "L-201",
                                         "L-202", "L-203", "L-204", "L-301", "L-302"],
      "scrubber line tags are exactly as declared")

# --- THE HONESTY CONTRACT --------------------------------------------------
# A row the engine resolved at an untrusted origin may not print its value, no
# matter that the value is there and looks plausible.


def attrs_of(train, tag) -> dict:
    """The caption -> Attr map for one tagged node, so a check reads as the
    sheet does: look up the equipment by its tag, then read a field off it."""
    return {c: a for c, a in next(n for n in train.nodes if n.tag == tag).attrs}


_attrs = attrs_of(scrub, "SC-101")
check(_attrs["Ø"].text == "750 mm", "a `given` diameter prints its millimetres")
check(_attrs["H"].text == "4 m", "a `rule` height prints its metres")
check(_attrs["MOC"].value == "SS-304 2mm" and _attrs["MOC"].text == "TBD",
      "a `consistent` material carries its value but PRINTS TBD")
_pump = attrs_of(scrub, "P-101")
check(_pump["Make"].text == "TBD", "a `consistent` pump make prints TBD")
_fan = attrs_of(scrub, "BL-101")
check(_fan["Motor"].text == "TBD", "a `reused` blower motor rating prints TBD")
check(all(o in TRUSTED_ORIGINS for o in ("given", "rule", "standard", "requirement")),
      "the trusted-origin set is the four the spec engine also trusts")
check(Attr("900", "reused").text == "TBD" and Attr("900", "rule").text == "900",
      "Attr.text is decided by origin alone")
check(attr_from_row(SCRUBBER_ROWS, ("nothing at all",)).text == "TBD",
      "a row that does not exist yields TBD rather than raising")
check(attr_from_row([{"label": "X", "value": "To be determined", "origin": "rule"}],
                    ("x",)).text == "TBD",
      "an admitted gap prints TBD even at a trusted origin")

# --- every air line carries the stated duty --------------------------------
_air = [s for s in scrub.streams if s.medium == "air"]
check(len(_air) == 3 and all(s.flow.text == "1359 m3/h" for s in _air),
      "every scrubber air line carries the duty the specification states")
check(all(s.size.text == "TBD" for s in scrub.streams),
      "NO scrubber line states a size — nothing computes one today (B13)")

# --- absence stability: the reason tags are declared, not allocated ---------
_no_pump = [r for r in SCRUBBER_ROWS if "Pump capacity" not in r["label"]]
_t2 = train_for("wet_scrubber", _no_pump, {}, GEO_TOWER)
check([n.tag for n in _t2.nodes] == _tags,
      "dropping a resolved value renumbers NOTHING — a tag is an identity")
check(next(n for n in _t2.nodes if n.tag == "P-101").attrs[0][1].text == "TBD",
      "the pump survives with a TBD rating; a missing number never deletes equipment")

# --- conditional equipment, and the re-link ---------------------------------
check(booth.dropped == (("dry", "dry scrubber not specified"),),
      f"an unspecified dry scrubber is dropped, with its reason ({booth.dropped})")
check("F-103" not in [n.tag for n in booth.nodes],
      "the dropped node's tag does not appear")
check([n.tag for n in booth.nodes] == ["F-101", "PB-101", "F-102", "BL-101",
                                       "STK-101", "CP-101"],
      "every surviving booth tag is unchanged by the drop")
_alive = [n.key for n in booth.nodes]
check(all(s.frm in _alive and s.to in _alive for s in booth.streams),
      "NO stream dangles: every endpoint is a drawn node")
_l103 = next(s for s in booth.streams if s.tag == "L-103")
check(_l103.frm == "bank" and _l103.to == "fan",
      "the line into the dropped node is carried through to what it fed")
check(_l103.size.text == "Ø500",
      "the merged run keeps the bore the engineering computed for it")
check(_l103.spec.text.startswith("GI"), "and keeps its material / velocity spec")
check(len({s.tag for s in booth.streams}) == len(booth.streams),
      "the re-link produces no duplicate line")

# --- a real, sourced instrument versus a proposed one ----------------------
_fsl = next(i for i in booth.instruments if i.tag == "FSL-102")
check(_fsl.status == "measured",
      "a confirmed solvent process makes the NFPA 33 interlock a STANDARD, not a proposal")
_no_fire = [r for r in BOOTH_ROWS if "Fire exting" not in r["label"]]
_t3 = train_for("paint_booth", _no_fire, {}, {})
check(next(i for i in _t3.instruments if i.tag == "FSL-102").status == "proposed",
      "with no resolved fire-protection row it downgrades to PROPOSED, asserting nothing")
check(all(i.setpoint.text == "TBD" for i in scrub.instruments + booth.instruments),
      "EVERY setpoint is TBD — none exists anywhere in the platform (B15)")

# --- instruments and valves follow what survives ---------------------------
check(all(i.on in _alive or i.on in [s.tag for s in booth.streams]
          for i in booth.instruments),
      "every instrument measures something that is actually drawn")
check(all(v.on in [s.tag for s in booth.streams] for v in booth.inline),
      "every valve sits on a line that is actually drawn")

# --- no template is an honest refusal, not a generic train -----------------
_none = train_for("cleaning_room", [], {}, {})
check(not _none.ok and not _none.nodes,
      "a category with no template yields NO train rather than a plausible one")
_wrong = train_for("wet_scrubber", SCRUBBER_ROWS, {},
                   {"equipment_type": "horizontal_baffle"})
check(not _wrong.ok and _wrong.notes,
      "a scrubber that is not a spray tower is refused, with the reason stated")

# --- templates are valid data ----------------------------------------------
for _key, _t in sorted(TRAIN_TEMPLATES.items()):
    _all = ([n.tag for n in _t.nodes] + [s.tag for s in _t.streams]
            + [i.tag for i in _t.instruments] + [v.tag for v in _t.inline])
    check(len(_all) == len(set(_all)), f"{_key}: every tag in the template is unique")
    check(_t.category == _key, f"{_key}: template names its own category")
    check(bool(_t.basis), f"{_key}: template states the basis for its topology")

_broken = tt.Template(
    id="x", category="x", label="x", basis="x",
    nodes=(tt.N("a", "stack", ("P", 101), "A"), tt.N("b", "stack", ("P", 101), "B")),
    streams=())
try:
    tt._validate(_broken)
    check(False, "_validate rejects a duplicate tag")
except ValueError as e:
    check("duplicate tag" in str(e), "_validate rejects a duplicate tag")

_dangling = tt.Template(
    id="x", category="x", label="x", basis="x",
    nodes=(tt.N("a", "stack", ("P", 101), "A"),),
    streams=(tt.S(("L", 1), "a", "out", "ghost", "in", "air"),))
try:
    tt._validate(_dangling)
    check(False, "_validate rejects a stream to a node that does not exist")
except ValueError as e:
    check("unknown node" in str(e), "_validate rejects a stream to a node that does not exist")

# --- determinism, including across a process restart -----------------------
check(resolve_train(TRAIN_TEMPLATES["wet_scrubber"], SCRUBBER_ROWS, {})
      == resolve_train(TRAIN_TEMPLATES["wet_scrubber"], SCRUBBER_ROWS, {}),
      "resolving twice yields an identical train")

# A set iteration would be stable within one process and vary between runs,
# because string hashing is randomised per process. Rendering twice in one
# process cannot catch that, so the check has to cross a process boundary.
#
# THE SUBPROCESS MUST NOT IMPORT THIS MODULE. A test file in this house style
# executes its checks at import, so `from tests_pid import ...` inside the child
# re-runs the whole suite — including this block — and each child spawns three
# more. That is a fork bomb, and it took the machine down once. The rows are
# handed over as JSON instead, so the child imports only the code under test.
_prog = (
    "import json, sys;"
    "sys.path.insert(0, %r);"
    "from app.engineering.train_templates import train_for;"
    "t = train_for('wet_scrubber', json.loads(sys.argv[1]), {},"
    "              {'equipment_type': 'vertical_spray_tower'});"
    "print('|'.join([n.tag for n in t.nodes] + [s.tag for s in t.streams]))"
) % os.path.dirname(os.path.abspath(__file__))

_env = dict(os.environ)
_runs = set()
for _seed in ("0", "1", "2"):
    _env["PYTHONHASHSEED"] = _seed
    _runs.add(subprocess.run(
        [sys.executable, "-c", _prog, json.dumps(SCRUBBER_ROWS)],
        capture_output=True, text=True, env=_env, timeout=120).stdout.strip())
check(len(_runs) == 1 and next(iter(_runs)).startswith("XC-101|"),
      f"tag order is identical under three different hash seeds ({len(_runs)} distinct)")


# --- the P&ID layers must be INERT on a GA sheet ---------------------------
# Adding a layer name to LAYER_ORDER is only safe because `Canvas.layers_present`
# filters it by the shapes actually present. That is the entire basis for
# calling the style change zero-risk, so it is pinned rather than asserted in a
# commit message.
import re  # noqa: E402

from app.drawing.drawing_service import build_drawing  # noqa: E402
from app.drawing.style import LAYER_LABELS, LAYER_ORDER  # noqa: E402
from app.drawing.symbols import SYMBOLS  # noqa: E402

_PID_LAYERS = ("process", "utility", "instrument")
check(all(l in LAYER_ORDER for l in _PID_LAYERS),
      "the three P&ID layers are declared in the drafting standard")
check(all(l in LAYER_LABELS for l in LAYER_ORDER),
      "every layer in LAYER_ORDER carries a studio label")

_leaked, _misordered = [], []
for _cat in sorted(SYMBOLS):
    _svg = build_drawing({
        "category": _cat, "category_label": _cat,
        "geometry": {"envelope_mm": {"length": 6000, "width": 3000,
                                     "height": 4000}, "ready": True},
        "technical_details": [{"label": "Illumination", "value": "LED 6 nos"}],
    })["svg"]
    _g = re.findall(r'<g id="layer-([a-z]+)"', _svg)
    _leaked += [(_cat, l) for l in _PID_LAYERS if l in _g]
    if _g != [l for l in LAYER_ORDER if l in _g]:
        _misordered.append(_cat)
check(not _leaked, f"no GA sheet emits a P&ID layer group ({_leaked[:3]})")
check(not _misordered,
      f"every GA sheet still emits its layers in canonical order ({_misordered[:3]})")

from app.drawing.export import _ACI  # noqa: E402
check(all(l in _ACI for l in LAYER_ORDER),
      "every layer has a DXF colour - a missing one exports as an "
      "indistinguishable 7")


# --- the renderer ----------------------------------------------------------
from app.drawing.pid import route as pid_route  # noqa: E402
from app.drawing.pid import service as pid_service  # noqa: E402

SPEC = {"category": "wet_scrubber", "category_label": "Wet Scrubber",
        "geometry": {"equipment_type": "vertical_spray_tower",
                     "envelope_mm": {"length": 750, "width": 750,
                                     "height": 4000}, "ready": True},
        "technical_details": SCRUBBER_ROWS}

_a = build_drawing(SPEC, drawing_type="pid")
_b = build_drawing(SPEC, drawing_type="pid")
check(_a["svg"] == _b["svg"], "identical spec produces byte-identical P&ID SVG")
check(len(_a["svg"]) > 20000, f"the sheet has real content ({len(_a['svg'])} bytes)")

# THE HONESTY ASSERTION, in its strongest form. A P&ID states no distance, so
# it emits no dimension layer at all - which cannot be satisfied by a dimension
# that merely looks odd.
check('<g id="layer-dimension"' not in _a["svg"],
      "a P&ID emits NO dimension layer - it claims no distance anywhere")
check(_a["scale"] == "NTS" and _a["title_block"]["scale"] == "NTS",
      "the sheet and its title block both say NOT TO SCALE")

_groups = re.findall(r'<g id="layer-([a-z]+)"', _a["svg"])
check(_groups == [l for l in LAYER_ORDER if l in _groups],
      f"P&ID layers are emitted in canonical order ({_groups})")
check(len(_groups) == len(set(_groups)), "each layer appears exactly once")
for _need in ("process", "utility", "instrument"):
    check(_need in _groups, f"the {_need} layer is drawn")

# --- the schedule must AGREE with the drawing ------------------------------
_sched = {r["line"] for r in _a["line_schedule"]}
_drawn = {s.tag for s in scrub.streams}
check(_sched == _drawn,
      "the line schedule lists exactly the lines that are drawn, both ways")
check({r["tag"] for r in _a["instrument_index"]}
      == {i.tag for i in scrub.instruments},
      "the instrument index lists exactly the instruments that are drawn")
for _t in list(_drawn) + [n.tag for n in scrub.nodes]:
    check(_a["svg"].count(f">{_t}<") >= 1, f"{_t} is printed on the sheet")
check(all(r["status"] == "TO BE CONFIRMED" for r in _a["instrument_index"]),
      "every proposed instrument is declared TO BE CONFIRMED in the index")

# --- routing correctness ---------------------------------------------------
# A line leaving a top port must depart UPWARDS. This is the defect that drew
# a tower's outlet straight back down through the tower.
check(pid_route.outward("scrub_tower", "out_top") == (0.0, -1.0),
      "a top port departs upwards")
check(pid_route.outward("pump_centrifugal", "discharge") == (0.0, -1.0),
      "a pump discharges vertically")
check(pid_route.outward("scrub_tower", "in_low") == (-1.0, 0.0),
      "a side port departs sideways")
check(_a["hops"] >= 1,
      f"the crossing between the liquor delivery and the main air line is "
      f"hopped, not drawn as a tee ({_a['hops']} hop(s))")

# --- the refusal sheet ------------------------------------------------------
_no = build_drawing({"category": "cleaning_room", "category_label": "Cleaning Room",
                     "geometry": {}, "technical_details": []},
                    drawing_type="pid")
check(_no["state"] == "schematic", "a category with no template is SCHEMATIC")
check(not _no["line_schedule"] and not _no["bom"],
      "the refusal sheet draws no train and schedules no equipment")
check("NOT ESTABLISHED" in _no["svg"],
      "the refusal sheet says plainly that the topology is not established")
check('<g id="layer-process"' not in _no["svg"],
      "NO process line is drawn for a category we have no template for")

# --- exports carry the new layers ------------------------------------------
from app.drawing.drawing_service import compose as _compose  # noqa: E402
_canvas, _pkg = _compose(SPEC, drawing_type="pid")
from app.drawing.export import to_dxf, to_pdf  # noqa: E402
_d = to_dxf(_canvas)
for _lay in ("process", "utility", "instrument"):
    check(_lay in _d, f"the DXF export carries the {_lay} layer")
check(to_pdf(_canvas)[:4] == b"%PDF", "the sheet exports as a valid PDF")

# --- the GA is untouched by any of this ------------------------------------
check(build_drawing(SPEC, drawing_type="ga")["scale"] != "NTS",
      "the same spec still renders a normal, scaled GA")


if FAILS:
    print(f"{len(FAILS)} PID TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL PID TESTS PASS")
