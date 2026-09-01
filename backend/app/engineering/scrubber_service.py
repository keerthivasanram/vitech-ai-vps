"""Wet-scrubber tower and duct diameter from airflow.

Source: the client's own workbook `Vertical Scrubber - Diameter calculation.xlsx`
(delivered 2026-09-01), transcribed in `docs/client-calculation-sheets.md` §1.

    Q (m3/s) = airflow (m3/h) / 3600
    A (m2)   = Q / velocity
    r (m)    = sqrt(A / 3.14)          # the sheet uses 3.14, not pi
    D (mm)   = r x 1000 x 2

Until now the tower diameter could only come from the customer — nothing in the
engine derived it — so a requirement that stated an airflow and no tower size
had no diameter, and therefore (since `geometry_service` builds a spray tower's
footprint from it) no drawable envelope.

THE STANDARD-SIZE STEP IS NOT IMPLEMENTED, ON PURPOSE. The sheet's rounding row
is stale: at 6750 m3/h it computes 1545 mm and the row beneath reads "~ 950",
which corresponds to roughly 2550 m3/h — a hand-typed leftover from an earlier
run, not a rounding of 1545. Vitech's standard-diameter ladder and rounding
direction are open question DQ-3, and a fabricated ladder would put a tower size
we invented onto a general-arrangement drawing. `standard_diameter_mm` therefore
stays None and the result says why.
"""
import math
from typing import NamedTuple, Optional

from . import standards_service as std

# The sheet's own value of pi. Kept deliberately: reproducing the client's
# number exactly matters more here than the fourth significant figure.
SHEET_PI = 3.14

# Velocities, from the workbook.
TOWER_VELOCITY_MS = 1.0     # across the scrubber tower  (D6)
DUCT_VELOCITY_MS = 15.0     # inlet and exhaust ducts    (D19 / D33)

_DQ3 = ("standard-size rounding not applied: Vitech's diameter ladder and "
        "rounding direction are outstanding (DQ-3)")


class Diameter(NamedTuple):
    """A computed bore, and an explicit statement about the standard size."""
    diameter_mm: Optional[float]
    area_m2: Optional[float]
    velocity_ms: float
    airflow_cmh: Optional[float]
    standard_diameter_mm: Optional[int] = None   # None until DQ-3 is answered
    note: str = _DQ3
    trail: tuple = ()


def _diameter(airflow_cmh: Optional[float], velocity_ms: float, what: str) -> Diameter:
    if airflow_cmh is None or float(airflow_cmh) <= 0 or velocity_ms <= 0:
        return Diameter(None, None, velocity_ms, airflow_cmh, None,
                        "not computed: a positive airflow is required", ())
    q = float(airflow_cmh) / 3600.0
    area = q / velocity_ms
    radius_m = math.sqrt(area / SHEET_PI)
    d_mm = radius_m * 1000.0 * 2.0
    trail = ((f"{what} diameter", f"{round(d_mm)} mm",
              f"{float(airflow_cmh):g} m3/h / 3600 = {q:g} m3/s / {velocity_ms:g} m/s "
              f"= {area:g} m2, d = 2 x sqrt(A / 3.14)",
              std.CLIENT_SCRUBBER_DIAMETER_CALC),)
    return Diameter(d_mm, area, velocity_ms, float(airflow_cmh), None, _DQ3, trail)


def tower_diameter(airflow_cmh: Optional[float],
                   velocity_ms: float = TOWER_VELOCITY_MS) -> Diameter:
    """Scrubber tower bore for a given airflow, at 1.0 m/s across the tower.

    Anchor (the sheet's own worked example): 6750 m3/h -> 1545 mm."""
    return _diameter(airflow_cmh, velocity_ms, "Tower")


def duct_diameter(airflow_cmh: Optional[float],
                  velocity_ms: float = DUCT_VELOCITY_MS) -> Diameter:
    """Inlet / exhaust duct bore for a given airflow, at 15 m/s transport velocity.

    Anchor (the sheet's own worked example): 6750 m3/h -> 399 mm."""
    return _diameter(airflow_cmh, velocity_ms, "Duct")
