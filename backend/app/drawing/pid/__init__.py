"""The P&ID renderer: a resolved process train becomes a sheet.

A P&ID answers a different question from a GA. The GA says how big the machine
is and where its faces are; the P&ID says WHAT IS CONNECTED TO WHAT, what flows
through each line, and what measures it. So this package shares the GA's sheet
furniture — frame, header, title block, side column, exporters — and none of its
geometry: there is no scale, no projection and no view set here, because a P&ID
is not a picture of the plant.

    ports.py       where a line may attach to a symbol, as pure data
    symbols.py     the ISA-5.1 glyph set, and PID_SYMBOLS
    layout.py      nodes onto a declared column/lane grid
    route.py       orthogonal routing, corridor allocation, hop marks
    schedules.py   the line schedule and instrument index rows
    states.py      what this sheet is allowed to claim
    service.py     compose() - the orchestrator

WHAT THIS PACKAGE MAY ASSERT. The topology, because it was declared as an
engineering fact of the equipment type (see `engineering/process_model.py`).
Nothing else: every printed size, flow, spec and setpoint arrives as an `Attr`
that already decided whether it may print, and a P&ID emits NO dimension layer
at all — there is nothing on the sheet claiming a distance.

THE ONE THING THIS PACKAGE IS NOT ALLOWED TO DO is draw a plausible train for a
category that has no template. That sheet exists (see `states.py`), and it is
deliberately empty of process: a generic booth -> fan -> stack chain invented to
fill the page would be the P&ID's version of a fabricated dimension.
"""
