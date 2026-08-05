"""The engineering PACKAGE layer: individual artifacts become one reviewable set.

The platform already produces a specification, a GA drawing, a bill of materials
and a budgetary quotation. Each is correct on its own and each was produced by
its own deterministic engine. What an engineer actually receives for review,
though, is a PACKAGE — and a package is more than a folder of files:

  * it says WHAT TO READ FIRST (the review report, not the specification),
  * it keeps assumptions OUT of the specification while still stating them,
  * it lets any number be traced back to the project or rule it came from, and
  * it uses ONE set of identifiers, so a balloon on the drawing, a BOM line and
    a quotation item are recognisably the same thing.

Nothing here re-engineers anything. Every value is read from the resolved
analysis that `agent_router.prepare` already produced; this layer composes,
classifies and cross-references. If a module in here ever computes an
engineering number, it is in the wrong place (golden rule #2).
"""
