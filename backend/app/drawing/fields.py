"""The input-field contract shared by the studio form and the render endpoint.

ONE definition of "is this field a number?", used both by
`GET /api/drawing/catalog` (which tells the UI what to render) and by
`POST /api/drawing/render` (which coerces what comes back). They previously
disagreed: the catalog typed fields from the key's unit suffix, while render
coerced anything that merely *looked* numeric — so a text field given a numeric
answer (paint process "10") arrived at the material engine as a float and
crashed it with `'float' object has no attribute 'lower'`.

Keeping both sides on this module makes that class of drift impossible.
"""
from typing import Any

# Suffix -> unit shown beside the field label. The suffix is also what marks a
# field as numeric, because every dimensional input in the catalog carries one.
_UNIT_BY_SUFFIX = {
    "_m": "m",
    "_mm": "mm",
    "_cfm": "CFM",
    "_cmh": "m3/h",
    "_kg": "kg",
    "_c": "°C",
}

# Numeric fields with no unit suffix.
_UNITLESS_NUMBERS = {"qty", "ach"}


def unit_for(key: str) -> str:
    """Unit string for an input key, or "" when it carries none."""
    for suffix, unit in _UNIT_BY_SUFFIX.items():
        if key.endswith(suffix):
            return unit
    return ""


def is_number(key: str) -> bool:
    """True when this input must be sent to the engine as a number.

    Driven by the key, never by the value: a text field stays text even when the
    user happens to type digits into it.
    """
    return bool(unit_for(key)) or key in _UNITLESS_NUMBERS


def describe(profile: dict, group: str) -> list[dict]:
    """The catalog description of one input group, for the studio form."""
    out = []
    for key, label in profile.get(group) or []:
        out.append({
            "key": key,
            "label": label,
            "unit": unit_for(key),
            "type": "number" if is_number(key) else "text",
            "required": group == "required_inputs",
        })
    return out


def coerce(values: dict) -> dict[str, Any]:
    """Turn submitted form values into engine parameters.

    Only declared-numeric keys become floats, and a numeric field holding
    something unparseable is DROPPED rather than passed through as text — the
    engine would otherwise receive a string where it expects a number. Empty
    values are omitted so they surface as honest TBDs instead of zeroes.
    """
    out: dict[str, Any] = {}
    for key, val in (values or {}).items():
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        if is_number(key):
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                continue        # unparseable number -> treat as not supplied
        else:
            out[key] = val if isinstance(val, str) else str(val)
    return out
