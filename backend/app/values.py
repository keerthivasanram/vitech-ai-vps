"""Reading engineering values out of specification rows.

Four small readers were copied between `bom.py`, `drawing/symbols.py`,
`drawing/spec_parser.py` and the package reports. They are the code that decides
whether "12 nos 600 x 600 x 50 mm" means twelve filters or six hundred, so they
are exactly the code that must not quietly diverge between the specification, the
BOM and the drawing — three documents that are supposed to describe one machine.

WHAT WAS NOT MERGED, and why. Three same-named functions elsewhere are different
functions, not copies, and merging them would have been a behaviour change:

  * `drawing/envelope._num(rows, *needles, trusted_only=True)` is a row LOOKUP
    that filters on provenance, not a number parser.
  * `engineering/engineering_planner._num(v)` is a type coercion — it accepts an
    already-numeric value and rejects strings, deliberately.
  * `specification_pdf._row(pdf, cols, widths)` draws a PDF table row.

Callers keep their own private names as thin adapters over these functions, so
the duplicated LOGIC is gone while every call site keeps its exact contract —
`bom` still gets `None` when a count is absent and `symbols` still gets `0`.
"""
import re
from typing import Any, Optional

# A count is only a count when the value SAYS so. A descriptive spec value is
# full of numbers that are not quantities: "flame proof LED 700-800 LUX" would
# otherwise be read as 700 luminaires, which is exactly the bug this rule was
# written for. Anything without an explicit nos/set marker returns the caller's
# default, so the drawing omits a symbol rather than inventing a count.
_COUNT_RE = re.compile(r"(\d+)\s*(?:nos?\b|no's|sets?\b)", re.I)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def first_number(text: Any, *, strip_commas: bool = True) -> Optional[float]:
    """The first number in a spec value, or None.

    `strip_commas` exists because the two original copies disagreed: the BOM
    stripped them (so "1,240 kg" reads as 1240) and the drawing's spec parser did
    not. Preserved as a parameter rather than unified, because changing either
    caller's reading of a comma would be a behaviour change, not a refactor.
    """
    raw = str(text or "")
    if strip_commas:
        raw = raw.replace(",", "")
    m = _NUMBER_RE.search(raw)
    return float(m.group()) if m else None


def stated_count(text: Any, default=None):
    """A COUNT, only where the value explicitly states one ('4 nos', '2 sets')."""
    m = _COUNT_RE.search(str(text or ""))
    return int(m.group(1)) if m else default


def first_integer(text: Any, default=None):
    """The first integer in a value, whether or not it is marked as a count.

    Narrower use than `stated_count`: only point it at a label that names a
    countable thing, never at a size row where the first integer is a dimension.
    """
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else default


def find_row(rows: Optional[list], *needles: str) -> Optional[dict]:
    """The first spec row whose label contains ALL the needles (case-insensitive)."""
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if all(n in label for n in needles):
            return r
    return None


def row_value(rows: Optional[list], *needles: str) -> Optional[Any]:
    """The value of the first matching row."""
    row = find_row(rows, *needles)
    return row.get("value") if row else None


# Values that mean "not answered". Kept here because the specification, the
# drawing and the package each need the same definition of an admitted gap.
TBD_VALUES = ("to be determined", "to be confirmed with the customer")


def is_resolved(value: Any) -> bool:
    """True when a value is a real answer rather than an admitted gap."""
    text = str(value or "").strip()
    return bool(text) and text.lower() not in TBD_VALUES


def clip(text: Any, limit: int = 60) -> str:
    """Shorten for a table cell, neutralising the markdown column separator."""
    text = str(text or "").replace("\n", " ").replace("|", "/")
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
