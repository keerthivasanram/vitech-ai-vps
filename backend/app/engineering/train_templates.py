"""DECLARED PROCESS TOPOLOGY, one template per equipment category.

WHY THIS IS DATA AND NOT CODE. `symbols.wet_scrubber` has been drawing a wet
scrubber's process chain since August — inlet low, contact stage, spray headers,
demister, outlet to the blower, sump below — inside 230 lines of glyph geometry
where nothing but the renderer could see it. The chain is not a drawing
decision; it is what the machine is. Declaring it here makes the same knowledge
readable, testable, and available to the BOM and the package layer.

WHAT A TEMPLATE AUTHOR MAY AND MAY NOT DO. You may declare that a scrubber has a
recirculation pump, because every vertical spray tower Vitech have ever built
has one. You may NOT declare what size its delivery line is: that is a number,
it belongs to the engineering rules, and if they did not compute it the sheet
says TBD. Every `attrs_from` entry names a spec row and inherits THAT ROW'S
ORIGIN — so naming a row is not the same as asserting its value, and a row that
resolved as `reused` or `assumed` still prints TBD.

EVERY ROW LABEL BELOW WAS TAKEN FROM A REAL RESOLUTION, not from the catalogue
profile. The two differ more than you would expect: a wet scrubber emits
`Blower motor hp`, while a paint booth emits `Exhaust blower motor (HP)`, and
neither emits the tidy label the profile suggests. When adding a category,
resolve a real requirement and read the rows before writing the template.

CLIENT-EXTENSION POINT: `TRAIN_TEMPLATES[category]`.
"""
from typing import Callable, NamedTuple, Optional

from .. import values
from .process_model import (MEDIUM_AIR, MEDIUM_DRAIN, MEDIUM_LIQUOR,
                            MEDIUM_WATER, MOUNT_FIELD, STATUS_MEASURED,
                            STATUS_PROPOSED, Attr, Inline, Train, resolve_train)


# --- declaration types ------------------------------------------------------
class NodeDecl(NamedTuple):
    key: str
    tag: str
    kind: str
    label: str
    service: str = ""
    col: int = 0
    lane: int = 0
    attrs_from: tuple = ()       # ((caption, (needle, ...), unit), ...)
    boundary: bool = False
    span: int = 1
    inside: str = ""
    at: float = 0.5
    # The row that SELECTS this item. Set only where existence is genuinely
    # conditional — a dry scrubber the spec may or may not include. A core node
    # leaves it empty and is always drawn, because a tower with an unknown bore
    # is still a tower.
    presence: tuple = ()


class StreamDecl(NamedTuple):
    tag: str
    frm: str
    to: str
    from_port: str
    to_port: str
    medium: str
    service: str = ""
    size_from: Optional[Callable] = None
    flow_from: Optional[Callable] = None
    spec_from: Optional[Callable] = None


class InstrumentDecl(NamedTuple):
    tag: str
    variable: str
    function: str
    loop: int
    on: str
    mounting: str = MOUNT_FIELD
    service: str = ""
    status: str = STATUS_PROPOSED
    status_from: Optional[Callable] = None


class Template(NamedTuple):
    id: str
    category: str
    label: str
    basis: str
    nodes: tuple
    streams: tuple
    instruments: tuple = ()
    inline: tuple = ()
    notes: tuple = ()
    equipment_type: str = ""     # gate on geometry.equipment_type, when set


def N(key, kind, tag, label, col=0, lane=0, service="", attrs_from=(),
      boundary=False, span=1, inside="", at=0.5, presence=()) -> NodeDecl:
    return NodeDecl(key, f"{tag[0]}-{tag[1]}", kind, label, service, col, lane,
                    tuple(attrs_from), boundary, span, inside, at,
                    tuple(presence))


def S(tag, frm, from_port, to, to_port, medium, service="",
      size_from=None, flow_from=None, spec_from=None) -> StreamDecl:
    return StreamDecl(f"{tag[0]}-{tag[1]}", frm, to, from_port, to_port,
                      medium, service, size_from, flow_from, spec_from)


def I(variable, function, loop, on, service, status=STATUS_PROPOSED,
      mounting=MOUNT_FIELD, status_from=None) -> InstrumentDecl:
    return InstrumentDecl(f"{variable}{function}-{loop}", variable, function,
                          loop, on, mounting, service, status, status_from)


def V(tag, kind, on, at, label) -> Inline:
    return Inline(f"{tag[0]}-{tag[1]}", kind, on, at, label)


# --- attribute resolvers ----------------------------------------------------
# Named functions rather than literals, so the mapping from a resolved spec to a
# line attribute lives in one testable place.
def DUTY_CMH(rows, params) -> Attr:
    """The duty every air line in the train carries.

    Read from the spec row rather than the raw parameter so the P&ID states the
    same number the specification does, converted the same way.
    """
    from .process_model import attr_from_row
    return attr_from_row(rows, ("air volume cmh",), "m3/h")


def ROW_CMH(*needles) -> Callable:
    def _f(rows, params) -> Attr:
        from .process_model import attr_from_row
        return attr_from_row(rows, needles)
    return _f


def DUCT_SIZE(*needles) -> Callable:
    """The BORE out of a duct row like '500 mm dia, GI, 15.3 m/s ...'."""
    def _f(rows, params) -> Attr:
        from .process_model import attr_from_row

        def bore(raw):
            n = values.first_number(str(raw).split(",")[0])
            return f"Ø{int(n)}" if n else ""
        a = attr_from_row(rows, needles, "", bore)
        return a if a.value else Attr()
    return _f


def DUCT_SPEC(*needles) -> Callable:
    """The MATERIAL and velocity out of the same row, minus the bore."""
    def _f(rows, params) -> Attr:
        from .process_model import attr_from_row

        def rest(raw):
            parts = [p.strip() for p in str(raw).split(",")[1:]]
            return ", ".join(p for p in parts if p)
        a = attr_from_row(rows, needles, "", rest)
        return a if a.value else Attr()
    return _f


def NFPA_INTERLOCK(rows, params) -> str:
    """A ventilation-proving switch is a STANDARD, not our proposal — but only
    when the fire-protection row actually resolved an interlocked shutdown.

    `design_standards.select_fire_protection` emits that only for a confirmed
    solvent process. Where the process is unstated the row is absent, and the
    device downgrades to PROPOSED rather than asserting a hazardous-area
    requirement nobody made.
    """
    row = values.find_row(rows, "fire extinguishing")
    if not row or str(row.get("origin")) != "standard":
        return STATUS_PROPOSED
    if "interlock" in str(row.get("value", "")).lower():
        return STATUS_MEASURED
    return STATUS_PROPOSED


TRAIN_TEMPLATES: dict = {}


# --- wet scrubber -----------------------------------------------------------
# Rows this category really emits (resolved 2026-09-10, anchor case
# "wet scrubber 800 cfm 750mm tower dia 4 nos"):
#   Tower diameter (mm)  given | Tower height (m)     rule
#   Spray nozzles (nos)  rule  | Pump capacity (HP)   rule
#   Tank capacity (litre) rule | Air volume cmh       given
#   Scrubber chamber consistent| Scrubber tank        reused
#   Eliminator / demister reused| Blower type         consistent
#   Blower motor hp      reused| Spray nozzle material reused
# Only the first six are trusted origins, so the rest correctly print TBD.
TRAIN_TEMPLATES["wet_scrubber"] = Template(
    id="ws-vertical-spray-tower-v1",
    category="wet_scrubber",
    label="Wet scrubber — vertical spray tower with liquor recirculation",
    equipment_type="vertical_spray_tower",
    basis=("Vitech's archived vertical spray towers, and the chain "
           "`drawing/symbols.py::wet_scrubber` has drawn since August: gas "
           "enters low, passes the contact stage and spray headers, leaves "
           "through the demister to the induced-draught blower and stack; the "
           "liquor recirculates sump -> pump -> header -> tower."),
    notes=("Process topology per equipment type; line sizes and instrument "
           "scope as scheduled.",),
    nodes=(
        N("src", "connector", ("XC", 101), "Process / booth exhaust connection",
          col=0, lane=0, service="Contaminated air", boundary=True),
        N("tower", "scrub_tower", ("SC", 101), "Wet scrubber tower",
          col=1, lane=0, service="Gas-liquid contact",
          attrs_from=(("Ø", ("tower diameter",), "mm"),
                      ("H", ("tower height",), "m"),
                      ("MOC", ("scrubber chamber",), ""))),
        N("demister", "demister", ("DM", 101), "Eliminator / demister",
          col=1, lane=0, inside="tower", at=0.14,
          attrs_from=(("Type", ("eliminator",), ""),)),
        N("header", "spray_header", ("SH", 101), "Spray nozzle header",
          col=1, lane=0, inside="tower", at=0.44,
          attrs_from=(("Nos", ("spray nozzles",), "nos"),
                      ("MOC", ("spray nozzle material",), ""))),
        N("sump", "tank_open", ("TK", 101), "Recirculation tank / sump",
          col=1, lane=1,
          attrs_from=(("Cap", ("tank capacity",), "L"),
                      ("MOC", ("scrubber tank",), ""))),
        N("strainer", "strainer_y", ("STR", 201), "Pump suction strainer",
          col=2, lane=1),
        # COL 3, WITH THE FAN MOVED TO 4. A centrifugal pump discharges
        # vertically, so a pump directly under the blower sends its delivery
        # line straight up through the blower's symbol.
        N("pump", "pump_centrifugal", ("P", 101), "Recirculation pump",
          col=3, lane=1,
          attrs_from=(("Motor", ("pump capacity",), "HP"),
                      ("Make", ("pump make",), ""))),
        N("fan", "fan_centrifugal", ("BL", 101), "Induced draught blower",
          col=4, lane=0,
          attrs_from=(("Type", ("blower type",), ""),
                      ("Motor", ("blower motor",), "HP"))),
        N("stack", "stack", ("STK", 101), "Discharge stack",
          col=5, lane=0, service="Clean air to atmosphere"),
        N("mkup", "connector", ("XC", 102), "Fresh water make-up",
          col=0, lane=1, boundary=True),
        # LANE 2, NOT LANE 1. Sharing the recirculation lane forced the drain
        # to run from the sump, through the strainer and the pump, to get here
        # - and a line crossing a symbol reads as a connection into it. Lanes
        # are how this engine makes that impossible; using one is the fix.
        N("eff", "connector", ("XC", 103), "Blowdown to effluent treatment",
          col=5, lane=2, boundary=True),
    ),
    streams=(
        S(("L", 101), "src", "out", "tower", "in_low", MEDIUM_AIR,
          "Contaminated air from process", flow_from=DUTY_CMH),
        S(("L", 102), "tower", "out_top", "fan", "suction", MEDIUM_AIR,
          "Scrubbed air to induced draught blower", flow_from=DUTY_CMH),
        S(("L", 103), "fan", "discharge", "stack", "in", MEDIUM_AIR,
          "Clean air to atmosphere", flow_from=DUTY_CMH),
        S(("L", 201), "tower", "drain", "sump", "in_top", MEDIUM_LIQUOR,
          "Gravity liquor return"),
        S(("L", 202), "sump", "out_low", "strainer", "in", MEDIUM_LIQUOR,
          "Pump suction"),
        S(("L", 203), "strainer", "out", "pump", "suction", MEDIUM_LIQUOR,
          "Pump suction"),
        S(("L", 204), "pump", "discharge", "header", "in", MEDIUM_LIQUOR,
          "Liquor delivery to spray header"),
        S(("L", 301), "mkup", "out", "sump", "in_top", MEDIUM_WATER,
          "Fresh water make-up"),
        S(("L", 302), "sump", "drain", "eff", "in", MEDIUM_DRAIN,
          "Blowdown / tank drain"),
    ),
    inline=(
        V(("DMP", 201), "damper", "L-101", 0.55, "Inlet isolation damper"),
        V(("V", 202), "valve_gate", "L-202", 0.50, "Pump suction isolation"),
        V(("V", 203), "valve_check", "L-204", 0.22, "Delivery non-return"),
        V(("V", 204), "valve_gate", "L-301", 0.50, "Make-up isolation"),
        V(("V", 205), "valve_gate", "L-302", 0.50, "Drain isolation"),
    ),
    instruments=(
        I("L", "SH", 101, "sump",
          "Sump level switch — make-up / low-level cutout"),
        I("P", "DI", 102, "tower", "Tower differential pressure"),
        I("P", "I", 103, "L-204", "Spray header delivery pressure"),
        I("F", "SL", 104, "L-102", "Exhaust airflow proving switch"),
    ),
)


# --- paint booth ------------------------------------------------------------
# Rows this category really emits (resolved 2026-09-10, "paint booth 4m x 3m x
# 3m solvent based, 12 components per shift"):
#   Type of paint booth  rule | Exhaust airflow      rule
#   Inlet air volume     rule | Exhaust ducts        rule  <- a REAL bore
#   Construction material advisory | Paint arresting filter assumed
#   Air intake filter  reused | Dry scrubber          tbd
#   Exhaust blower (+ motor/drive/nos/CFM) tbd
#   Fire extinguishing system standard
TRAIN_TEMPLATES["paint_booth"] = Template(
    id="pb-dry-filter-extract-v1",
    category="paint_booth",
    label="Paint booth — dry filter extract",
    basis=("The booth's own resolved arrangement: make-up air is drawn through "
           "an intake filter, the enclosure runs under suction, extract passes "
           "the paint-arresting filter bank, then the dry scrubber WHERE THE "
           "SPECIFICATION SELECTS ONE, into the duct `select_duct` sized, the "
           "selected blower, and the stack. Nothing here chooses a component "
           "the specification did not already choose."),
    notes=("Process topology per equipment type; line sizes and instrument "
           "scope as scheduled.",),
    nodes=(
        N("intake", "filter_panel", ("F", 101), "Air intake filter",
          col=0, lane=0, service="Make-up air",
          attrs_from=(("Type", ("air intake filter",), ""),)),
        N("booth", "booth_enclosure", ("PB", 101), "Paint booth enclosure",
          col=1, lane=0, span=2,
          attrs_from=(("Type", ("type of paint booth",), ""),
                      ("MOC", ("construction material",), ""),
                      ("Lights", ("illumination",), ""))),
        N("bank", "filter_bank", ("F", 102), "Paint arresting filter bank",
          col=3, lane=0,
          attrs_from=(("Cells", ("paint arresting filter",), ""),)),
        N("dry", "filter_panel", ("F", 103), "Dry scrubber",
          col=4, lane=0, presence=("dry scrubber",),
          attrs_from=(("Type", ("dry scrubber",), ""),)),
        N("fan", "fan_centrifugal", ("BL", 101), "Exhaust blower",
          col=5, lane=0,
          attrs_from=(("Model", ("exhaust blower",), ""),
                      ("Rated", ("blower airflow",), ""),
                      ("Motor", ("blower motor",), ""))),
        N("stack", "stack", ("STK", 101), "Discharge stack",
          col=6, lane=0, service="Clean air to atmosphere"),
        N("mcc", "panel", ("CP", 101), "Control panel",
          col=5, lane=-1,
          attrs_from=(("Rating", ("control panel",), ""),)),
    ),
    streams=(
        S(("L", 101), "intake", "out", "booth", "in_face", MEDIUM_AIR,
          "Filtered make-up air", flow_from=ROW_CMH("inlet air volume")),
        S(("L", 102), "booth", "out_extract", "bank", "in", MEDIUM_AIR,
          "Overspray-laden extract", flow_from=ROW_CMH("exhaust airflow")),
        S(("L", 103), "bank", "out", "dry", "in", MEDIUM_AIR,
          "Filtered extract", flow_from=ROW_CMH("exhaust airflow")),
        # THE LINE WITH A REAL, CALCULATED BORE. `select_duct` resolves it at
        # the client's own transport velocity and the spec states it verbatim.
        S(("L", 104), "dry", "out", "fan", "suction", MEDIUM_AIR,
          "Exhaust duct to blower",
          size_from=DUCT_SIZE("exhaust ducts"),
          flow_from=ROW_CMH("exhaust airflow"),
          spec_from=DUCT_SPEC("exhaust ducts")),
        S(("L", 105), "fan", "discharge", "stack", "in", MEDIUM_AIR,
          "Clean air to atmosphere",
          size_from=DUCT_SIZE("exhaust ducts"),
          flow_from=ROW_CMH("exhaust airflow")),
    ),
    inline=(
        V(("DMP", 201), "damper", "L-101", 0.55, "Make-up air volume damper"),
    ),
    instruments=(
        I("P", "DI", 101, "bank", "Filter bank differential pressure"),
        I("F", "SL", 102, "L-102",
          "Ventilation proving switch — interlocked with spray application",
          status_from=NFPA_INTERLOCK),
        I("P", "I", 103, "booth", "Booth static pressure indicator"),
    ),
)


# --- validation -------------------------------------------------------------
def _validate(t: Template) -> None:
    """Raise on a duplicate tag, an unknown node key, or a stream to nowhere.

    A template is DATA, and a duplicate tag in it is a source error rather than
    a runtime condition — so it must fail at IMPORT. A backend that will not
    start is found in a second; a sheet carrying two P-101s is found by a
    fabricator.
    """
    keys = [n.key for n in t.nodes]
    dupe_keys = [k for k in keys if keys.count(k) > 1]
    if dupe_keys:
        raise ValueError(f"{t.id}: duplicate node key {sorted(set(dupe_keys))}")

    tags = ([n.tag for n in t.nodes] + [s.tag for s in t.streams]
            + [i.tag for i in t.instruments] + [v.tag for v in t.inline])
    dupes = sorted({x for x in tags if tags.count(x) > 1})
    if dupes:
        raise ValueError(f"{t.id}: duplicate tag {dupes}")

    for s in t.streams:
        for end in (s.frm, s.to):
            if end not in keys:
                raise ValueError(f"{t.id}: stream {s.tag} names unknown node "
                                 f"{end!r}")
    stream_tags = [s.tag for s in t.streams]
    for n in t.nodes:
        if n.inside and n.inside not in keys:
            raise ValueError(f"{t.id}: node {n.key} sits inside unknown "
                             f"node {n.inside!r}")
    for i in t.instruments:
        if i.on not in keys and i.on not in stream_tags:
            raise ValueError(f"{t.id}: instrument {i.tag} measures unknown "
                             f"{i.on!r}")
    for v in t.inline:
        if v.on not in stream_tags:
            raise ValueError(f"{t.id}: inline {v.tag} sits on unknown stream "
                             f"{v.on!r}")


for _t in TRAIN_TEMPLATES.values():
    _validate(_t)


def train_for(category: str, rows: list, params: Optional[dict] = None,
              geometry: Optional[dict] = None) -> Train:
    """The resolved train for a category, or an `ok=False` Train when none.

    A category with no template is not a failure to be papered over: the
    renderer turns it into the sheet that draws no train and schedules what
    would establish one. Drawing a plausible generic chain instead would be the
    P&ID equivalent of a fabricated dimension.
    """
    t = TRAIN_TEMPLATES.get(str(category or ""))
    if not t:
        return Train(ok=False, category=str(category or ""))
    want = t.equipment_type
    got = str((geometry or {}).get("equipment_type") or "")
    if want and got and want != got:
        return Train(ok=False, category=t.category,
                     notes=(f"No process template for a {got.replace('_', ' ')}.",))
    return resolve_train(t, rows, params, geometry)
