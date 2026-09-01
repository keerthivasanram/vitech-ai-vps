"""2D General-Arrangement drawing engine.

Turns the spec engine's deterministic mm envelope into a dimensioned GA sheet.
Mirrors the `engineering/` package split so the client extends it the same way:

  primitives.py     - mm-space vector model + byte-stable SVG emit
  views.py          - third-angle projection + standard scale selection
  symbols.py        - per-category component glyphs (CLIENT-EXTENSION POINT)
  title_block.py    - Vitech title block, sharing the letterhead constants
  sheet.py          - sheet sizes, frame, legend, notes, TBD schedule
  drawing_service.py- orchestrator: build_drawing(spec) -> drawing package

Every dimension originates in the spec engine; an unknown one is drawn as a TBD
callout, never a guessed line (golden rule #2).
"""
