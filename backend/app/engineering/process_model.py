"""The PROCESS TRAIN: what is connected to what, and what flows between.

WHY THIS IS AN ENGINEERING MODULE AND NOT A DRAWING ONE. A train is an
engineering output, exactly like the envelope `geometry_service` resolves. It
used to be nowhere at all: every layer of this platform — profile, rules, spec
rows, BOM, GA, quotation — is built around ONE machine with ONE envelope and a
FLAT parts list, and nothing anywhere recorded that a scrubber's pump takes
suction from its own sump. Putting the train inside the renderer would repeat
the mistake `geometry_service`'s own docstring describes: the drawing would
decide the plant's connectivity by pattern-matching spec row labels, and the
BOM, the package layer and the quotation scope could never see it.

WHY DECLARING TOPOLOGY IS NOT INVENTION. A wet scrubber's gas path is inlet ->
tower -> demister -> ID fan -> stack, and its liquor loop is sump -> pump ->
header -> tower. That is what the machine IS, not an arrangement we chose — the
same argument `drawing/symbols.py::airflow` already makes for a flow arrow
("a fact of the machine type, not a position we invented"), and the same
knowledge `symbols.wet_scrubber` has been drawing since August, moved out of
230 lines of glyph code into declared data.

WHAT IS STILL REFUSED. A line SIZE, a FLOW, a SETPOINT and an instrument's
presence are numbers or scope claims, not facts of the machine type. Each
carries the origin it was resolved at, and anything the engineering did not
resolve prints TBD and lands in the unresolved schedule. Golden rule #2 is not
relaxed because a P&ID would look more finished with a plausible bore on it.

EXISTENCE VERSUS SIZE — the distinction the whole module turns on. A scrubber
tower exists whether or not anyone has computed its bore, so an unresolved
diameter makes the tower's LABEL read TBD; it does not delete the tower. Only a
node whose existence is genuinely conditional (a dry scrubber, a carbon bed —
equipment the specification either selects or does not) is dropped, and only
when the row that would have selected it did not resolve. Dropping a core node
because an attribute was missing would produce a wet-scrubber P&ID with no
scrubber on it, which is a worse lie than a TBD.
"""
from typing import Any, NamedTuple, Optional

from .. import values

# Only these origins may PRINT as a stated value. The set is deliberately the
# same one `geometry_service` trusts for a drawn dimension, for the same reason:
# `reused` describes a COMPARABLE machine, `consistent` and `assumed` describe
# our own inference, and none of the three describes THIS plant's pipe.
TRUSTED_ORIGINS = frozenset({"given", "rule", "requirement", "standard"})

TBD_TEXT = "TBD"


class Attr(NamedTuple):
    """One resolved attribute, carrying the provenance it was resolved at.

    Every printable value on a P&ID is one of these, so TBD propagates BY
    CONSTRUCTION rather than by each renderer remembering to check an origin.
    """
    value: Optional[str] = None
    origin: str = "tbd"
    basis: str = ""              # formula / source, for traceability
    source_label: str = ""       # the spec row label this came from

    @property
    def resolved(self) -> bool:
        return (values.is_resolved(self.value)
                and self.origin in TRUSTED_ORIGINS)

    @property
    def text(self) -> str:
        """What PRINTS. An untrusted origin prints TBD, never the value —
        printing a `reused` line size would put another plant's pipe on this
        sheet, under this plant's tag."""
        return str(self.value) if self.resolved else TBD_TEXT


TBD = Attr()


class Node(NamedTuple):
    """A tagged item of equipment on the diagram."""
    key: str                     # template-local id ("tower"); never printed
    tag: str                     # "SC-101" — the plant identity
    kind: str                    # a key in drawing.pid.symbols.PID_SYMBOLS
    label: str                   # "Wet scrubber tower"
    service: str = ""            # "Gas-liquid contact"
    col: int = 0                 # process step, left -> right
    lane: int = 0                # 0 = main process band, +n below, -n above
    attrs: tuple = ()            # ((caption, Attr), ...) printed under the tag
    boundary: bool = False       # an off-sheet connector, not equipment
    span: int = 1                # columns the symbol occupies
    inside: str = ""             # drawn INSIDE this node's box, when set
    at: float = 0.5              # fractional height within the host, if inside


class Stream(NamedTuple):
    """A process line between two nodes. THE thing a P&ID exists to state."""
    tag: str                     # "L-101"
    frm: str                     # Node.key
    to: str                      # Node.key
    from_port: str
    to_port: str
    medium: str
    service: str = ""
    size: Attr = TBD
    flow: Attr = TBD
    spec: Attr = TBD


class Instrument(NamedTuple):
    """An ISA-5.1 bubble.

    `status` is the honest half. MEASURED means the resolved specification names
    this device, or a standard mandates it. PROPOSED means it is good practice
    and Vitech have not confirmed their instrument scope — it is drawn DASHED,
    listed in the index as TO BE CONFIRMED, and appears in the unresolved
    schedule. Drawing a proposed device solid would invent a scope of supply;
    omitting it entirely would ship a P&ID with no instrumentation, which is not
    a P&ID.
    """
    tag: str                     # "PDI-102" — variable + function + loop
    variable: str                # ISA first letter:      P T F L A S
    function: str                # ISA succeeding letters: I T IC SL DI
    loop: int
    on: str                      # a Node.key or a Stream.tag
    mounting: str = "field"
    service: str = ""
    setpoint: Attr = TBD
    status: str = "proposed"


class Inline(NamedTuple):
    """A valve or damper ON a line, drawn at a fraction along its run.

    Kept out of `Node` because it occupies no grid cell — the router has to
    place it along a routed polyline, and it carries no equipment schedule row.
    """
    tag: str                     # "DMP-201"
    kind: str                    # valve_gate | valve_check | valve_control | damper
    on: str                      # Stream.tag
    at: float = 0.5              # 0..1 along the routed polyline
    label: str = ""
    fail_action: Attr = TBD      # "FC" / "FO" — TBD until Vitech state it
    status: str = "proposed"


class Train(NamedTuple):
    """The resolved process train.

    `ok=False` means no template applied to this category, which the renderer
    turns into the SCHEMATIC sheet — the one that draws no train at all and
    carries the unresolved schedule as its content.
    """
    ok: bool
    category: str
    template_id: str = ""
    label: str = ""
    basis: str = ""
    nodes: tuple = ()
    streams: tuple = ()
    instruments: tuple = ()
    inline: tuple = ()
    dropped: tuple = ()          # ((key, reason), ...)
    notes: tuple = ()


# --- media ------------------------------------------------------------------
MEDIUM_AIR = "air"           # contaminated / clean process air — the MAIN line
MEDIUM_LIQUOR = "liquor"     # recirculating scrubbing liquor
MEDIUM_WATER = "water"       # fresh make-up
MEDIUM_DRAIN = "drain"       # blowdown / effluent
MEDIUM_SIGNAL = "signal"     # instrument signal — never a process line

# WHEN TWO LINES CROSS, THE HIGHER RANK HOPS. A main air line is never broken by
# a utility line: that is the drafting convention, and ranking by MEDIUM makes
# it deterministic rather than a consequence of emission order.
MEDIUM_RANK = {MEDIUM_AIR: 0, MEDIUM_LIQUOR: 1, MEDIUM_WATER: 2,
               MEDIUM_DRAIN: 3, MEDIUM_SIGNAL: 4}

STATUS_MEASURED = "measured"
STATUS_PROPOSED = "proposed"

MOUNT_FIELD = "field"              # plain circle
MOUNT_LOCAL_PANEL = "local_panel"  # circle in a square
MOUNT_PANEL = "panel"              # circle with a solid horizontal bar


# --- reading the specification ---------------------------------------------
def attr_from_row(rows: list, needles: tuple, unit: str = "",
                  fmt=None) -> Attr:
    """One spec row -> an Attr carrying that row's ORIGIN.

    Read through `values.find_row`, the SAME reader the BOM uses, so a P&ID and
    a BOM can never disagree about what a row said. A template author therefore
    cannot assert a value merely by naming a row: if the row resolved at an
    untrusted origin, the Attr refuses to print it.
    """
    row = values.find_row(rows, *needles)
    if not row:
        return TBD
    raw = row.get("value")
    if not values.is_resolved(raw):
        return TBD
    text = fmt(raw) if fmt else str(raw).strip()
    if unit and text and not text.lower().endswith(unit.lower()):
        text = f"{text} {unit}"
    return Attr(text, str(row.get("origin") or "tbd"),
                str(row.get("basis") or ""), str(row.get("label") or ""))


def _resolved_row(rows: list, needles: tuple) -> bool:
    """Does the row that would SELECT a conditional item actually name one?

    Presence is a weaker test than `Attr.resolved` on purpose. A dry scrubber
    the specification carried over from a comparable booth is still a dry
    scrubber this booth has — the ORIGIN governs whether we may print its
    description, not whether the equipment is there.
    """
    row = values.find_row(rows, *needles)
    return bool(row) and values.is_resolved(row.get("value"))


def resolve_train(template, rows: list, params: Optional[dict] = None,
                  geometry: Optional[dict] = None) -> Train:
    """A declared template, filled from the resolved specification.

    Nodes whose existence is conditional are dropped when the row that selects
    them did not resolve, and every stream that referenced a dropped node is
    RE-LINKED THROUGH to the next surviving node rather than left dangling — a
    booth with no dry scrubber still has a duct from its filter bank to its fan.
    """
    rows = rows or []
    params = params or {}

    kept: list = []
    dropped: list = []
    for decl in template.nodes:
        if decl.presence and not _resolved_row(rows, decl.presence):
            dropped.append((decl.key, f"{' '.join(decl.presence)} not specified"))
            continue
        kept.append(Node(
            key=decl.key, tag=decl.tag, kind=decl.kind, label=decl.label,
            service=decl.service, col=decl.col, lane=decl.lane,
            attrs=tuple((cap, attr_from_row(rows, nd, unit))
                        for cap, nd, unit in decl.attrs_from),
            boundary=decl.boundary, span=decl.span,
            inside=decl.inside, at=decl.at,
        ))

    alive = tuple(n.key for n in kept)
    streams = _relink_dropped(template.streams, alive, template.nodes)

    out_streams = tuple(
        Stream(tag=s.tag, frm=s.frm, to=s.to, from_port=s.from_port,
               to_port=s.to_port, medium=s.medium, service=s.service,
               size=s.size_from(rows, params) if s.size_from else TBD,
               flow=s.flow_from(rows, params) if s.flow_from else TBD,
               spec=s.spec_from(rows, params) if s.spec_from else TBD)
        for s in streams)

    live_tags = tuple(s.tag for s in out_streams)
    instruments = tuple(
        Instrument(tag=i.tag, variable=i.variable, function=i.function,
                   loop=i.loop, on=i.on, mounting=i.mounting,
                   service=i.service, setpoint=TBD,
                   status=(i.status_from(rows, params) if i.status_from
                           else i.status))
        for i in template.instruments
        if i.on in alive or i.on in live_tags)

    inline = tuple(v for v in template.inline if v.on in live_tags)

    return Train(ok=True, category=template.category,
                 template_id=template.id, label=template.label,
                 basis=template.basis, nodes=tuple(kept),
                 streams=out_streams, instruments=instruments,
                 inline=inline, dropped=tuple(dropped),
                 notes=tuple(template.notes))


def _relink_dropped(streams, alive: tuple, declared) -> tuple:
    """Re-terminate streams whose endpoints were dropped; never leave a dangle.

    A dropped node is a component the plant does not have, not a break in the
    process: air still flows from whatever fed it to whatever it fed. So the
    stream INTO a dropped node is carried forward to that node's own downstream
    destination, and the now-duplicated stream out of it is discarded. Walking
    forward (rather than deleting both) is what keeps the line schedule honest —
    the connection is real, only the intermediate box is not.

    THE MERGED LINE TAKES THE TAIL'S ATTRIBUTES WHERE THE HEAD DECLARES NONE.
    A booth with no dry scrubber runs filter bank -> blower, and that run IS the
    exhaust duct `select_duct` sized: the head segment (bank -> dry scrubber)
    never declared a bore because the sized duct was the segment beyond it. Keep
    only the head's resolvers and the merged line would print TBD against a duct
    the engineering actually computed — dropping a real number, which is as
    wrong as inventing one. The head names the line; the tail describes what
    reaches the destination.
    """
    onward: dict = {}
    for s in streams:
        onward.setdefault(s.frm, s)

    out: list = []
    seen: list = []
    for s in streams:
        if s.frm not in alive:
            continue                      # its predecessor already carried it
        to, to_port, tail = s.to, s.to_port, s
        guard = 0
        while to not in alive and guard < len(declared) + 1:
            nxt = onward.get(to)
            if not nxt:
                to = ""
                break
            to, to_port, tail = nxt.to, nxt.to_port, nxt
            guard += 1
        if not to or to not in alive or to == s.frm:
            continue
        if (s.frm, to) in seen:
            continue
        seen.append((s.frm, to))
        merged = s._replace(to=to, to_port=to_port)
        if tail is not s:
            merged = merged._replace(
                service=tail.service or s.service,
                size_from=s.size_from or tail.size_from,
                flow_from=s.flow_from or tail.flow_from,
                spec_from=s.spec_from or tail.spec_from)
        out.append(merged)
    return tuple(out)
