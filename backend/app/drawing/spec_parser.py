"""Read a generated engineering specification back into a drawable spec.

The Engineering Agent hands the user a `spec_markdown` table. The natural next
sentence is "now draw that" — so the Drawing Studio accepts the specification
itself as input, not just a fresh requirement.

WHY PARSE RATHER THAN RE-RESOLVE. Re-running the resolver on the original
requirement would produce a drawing of a spec that *resembles* the one on the
engineer's screen. Parsing the actual document draws THE spec they are holding,
including every value they reviewed and every TBD they accepted. That is the
difference between a drawing of the design and a drawing of another design with
the same inputs.

This is only safe because the document is OURS: `main._spec_markdown` emits it,
so the shape is a contract, not a guess. Anything that does not match the
contract returns None and the caller falls back to resolving a requirement —
this never tries to salvage arbitrary prose into geometry.
"""
import re
from typing import Any, Optional

_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_EQUIPMENT = re.compile(r"^\s*equipment\s*:\s*(.+?)\s*(?:\|.*)?$", re.I | re.M)
_HEADING = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")

# Basis wording -> the origin tag the drawing engine and the TBD schedule use.
# Matched in order; the first hit wins.
_ORIGIN_BY_BASIS = [
    ("to be determined", "tbd"),
    ("calculated", "rule"),
    ("engineering standard", "standard"),
    ("recommended", "advisory"),
    ("customer decision", "customer_decision"),
    ("from requirement", "given"),
    ("historical consensus", "consistent"),
    ("scaled", "scaled"),
    ("inferred", "interpolated"),
    ("reused", "reused"),
]

_DIM_KEYS = {"length": "length_m", "width": "width_m", "height": "height_m"}


def looks_like_spec(text: str) -> bool:
    """Cheap gate: is this our specification document rather than a request?"""
    t = (text or "").lower()
    return ("engineering specification" in t
            or ("| parameter | value" in t and "|" in t and t.count("|") > 8))


def _origin_for(basis: str, value: str) -> str:
    if str(value).strip().lower() == "to be determined":
        return "tbd"
    b = str(basis or "").lower()
    for needle, origin in _ORIGIN_BY_BASIS:
        if needle in b:
            return origin
    return "reused"


def _num(text) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def _to_mm(value: float, unit_hint: str) -> Optional[int]:
    """A dimension in the units the spec states it in."""
    u = (unit_hint or "").lower()
    if "mm" in u:
        return round(value)
    if "cm" in u:
        return round(value * 10)
    return round(value * 1000)          # metres, the spec's default


def _envelope(given: dict, rows: list) -> dict:
    """L/W/H in mm from the requirement table, else from a Dimensions row.

    Only real stated numbers are used. An axis the document does not carry stays
    None so the sheet prints TBD, exactly as it would on the resolver path.
    """
    env: dict[str, Optional[int]] = {"length": None, "width": None, "height": None}
    for axis, key in (("length", "length_m"), ("width", "width_m"), ("height", "height_m")):
        entry = given.get(key)
        if entry:
            env[axis] = _to_mm(entry["value"], entry["unit"])

    if not all(env.values()):
        for r in rows:
            if "dimension" not in str(r.get("label", "")).lower():
                continue
            nums = re.findall(r"\d+(?:\.\d+)?", str(r.get("value", "")))
            if len(nums) >= 3:
                unit = str(r.get("value", ""))
                for axis, n in zip(("length", "width", "height"), nums[:3]):
                    if env[axis] is None:
                        env[axis] = _to_mm(float(n), unit)
                break
    return env


def _category_for(label: str) -> tuple[str, str]:
    """The catalog key whose label the document names."""
    from ..catalog import CATEGORY_PROFILES

    want = (label or "").strip().lower()
    for key, prof in CATEGORY_PROFILES.items():
        if str(prof.get("label", "")).lower() == want:
            return key, prof["label"]
    for key, prof in CATEGORY_PROFILES.items():          # tolerate "Paint Booth GA"
        if want and (want in str(prof.get("label", "")).lower()
                     or str(prof.get("label", "")).lower() in want):
            return key, prof["label"]
    return "", label.strip()


def parse_spec(text: str) -> Optional[dict[str, Any]]:
    """A pasted specification -> the dict `build_drawing` consumes, or None."""
    if not looks_like_spec(text):
        return None

    eq = _EQUIPMENT.search(text or "")
    category, label = _category_for(eq.group(1) if eq else "")

    section = ""
    given: dict[str, dict] = {}
    rows: list[dict] = []
    for line in (text or "").splitlines():
        if (h := _HEADING.match(line)):
            section = h.group(1).strip().lower()
            continue
        if _SEP.match(line) or not line.strip().startswith("|"):
            continue
        # Cells are split rather than regex-grouped because the two tables have
        # DIFFERENT widths: the requirement table is Parameter|Value and the
        # technical one is Parameter|Value|Basis. A fixed three-group pattern
        # silently skipped every requirement row, so no dimension was ever read
        # and a fully dimensioned spec drew as an NTS blank.
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        while len(cells) < 3:
            cells.append("")
        head = cells[0].lower()
        if head in ("parameter", "item") or not cells[0]:
            continue                                     # the table's own header

        if "requirement" in section:
            # "Length m | 5" — the unit lives in the parameter name.
            base = re.sub(r"\b(m|mm|cm)\b\s*$", "", head).strip()
            key = _DIM_KEYS.get(base)
            val = _num(cells[1])
            if key and val is not None:
                given[key] = {"value": val, "unit": head[len(base):].strip() or "m"}
            rows.append({"label": cells[0], "value": cells[1], "origin": "given",
                         "kind": "geometry" if key else None, "source": "requirement"})
        else:
            rows.append({"label": cells[0], "value": cells[1],
                         "origin": _origin_for(cells[2], cells[1]), "kind": None})

    spec_rows = [r for r in rows if r.get("source") != "requirement"]
    if not spec_rows:
        return None

    env = _envelope(given, spec_rows)
    if not all(env.values()) and category:
        # Same last resort the resolver path uses: a category that never states
        # L x W x H may still have a fully determined envelope.
        from .envelope import derive_envelope
        params = {k: v["value"] for k, v in given.items()}
        derived = derive_envelope(category, spec_rows, params)
        if derived:
            env = derived

    return {
        "category": category,
        "category_label": label or "Equipment",
        "geometry": {"envelope_mm": env,
                     "envelope_source": "specification",
                     "ready": all(env.values()),
                     "fields": [r for r in rows if r.get("kind") == "geometry"]},
        "technical_details": spec_rows,
        "from_specification": True,
    }
