"""Unit conversion — the single source of truth for engineering unit bases.

Formulas work in SI-ish engineering units (m3/h for airflow, m for length),
so conversions live HERE, not sprinkled through the formulas. Adding a client
unit = one entry in `_FACTORS`; nothing else changes.
"""
from typing import Optional

# ft3/min -> m3/h. 1 CFM = 1.699 CMH (the value llama3.1 kept inventing wrong,
# which is exactly why it is pinned in code, not left to the model).
CFM_TO_CMH = 1.699

# (from_unit, to_unit) -> multiply source value by this factor to get target.
# The client extends this table with any additional unit pairs they use.
_FACTORS: dict[tuple[str, str], float] = {
    ("cfm", "cmh"): CFM_TO_CMH,
}


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert `value` from one unit to another using the factor table.
    Raises KeyError for an unregistered pair, so a missing conversion fails
    loudly rather than silently returning a wrong number."""
    if from_unit == to_unit:
        return float(value)
    return float(value) * _FACTORS[(from_unit, to_unit)]


def air_cmh(params: dict) -> Optional[float]:
    """Airflow in m3/h from the requirement, accepting either unit basis:
    a direct `air_volume_cmh`, else `air_volume_cfm` converted. None if neither
    is present (the caller then cannot size airflow-driven equipment)."""
    q = params.get("air_volume_cmh")
    if isinstance(q, (int, float)):
        return float(q)
    cfm = params.get("air_volume_cfm")
    return convert(cfm, "cfm", "cmh") if isinstance(cfm, (int, float)) else None
