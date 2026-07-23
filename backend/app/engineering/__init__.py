"""Engineering Intelligence layer.

The deterministic core that turns a requirement into engineering values — every
number traceable to a formula, a governing standard, and a unit basis. The LLM
never computes here; it only narrates what this package produces (golden rule #2).

Sub-services (client-extensible — the client supplies the domain details, each
slots into one clearly-named place):
  unit_converter      — unit bases + conversion factors (e.g. CFM -> CMH)
  calculation_engine  — generic numeric primitives (rounding, counts, snapping)
  standards_service   — the governing standards each rule cites
  material_service     — material / filtration selection by process
  formula_service     — design constants + the per-equipment formulas that
                         COMPOSE the four services above
  engineering_planner — orchestrator: requirement -> traceable spec values

NOTE: this __init__ deliberately imports NOTHING. `engineering_planner` pulls in
`catalog`, which imports `rules`, which re-exports from `formula_service` here —
so an eager re-export in this file creates a circular import at package init.
Import the submodule you need directly (e.g.
`from app.engineering.formula_service import compute_spec`).
"""
