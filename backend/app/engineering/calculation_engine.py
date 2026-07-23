"""Generic numeric primitives shared by the formulas.

Pure math, no engineering knowledge — that lives in formula_service. Kept
separate so every formula rounds / counts / snaps the same way, and so the
rounding policy can be audited in one place.
"""
import math


def round_to_step(value: float, step: int = 10) -> int:
    """Round to the nearest multiple of `step` (e.g. airflow to the nearest
    10 m3/h). Returns an int — these are catalogue/display quantities."""
    return int(round(value / step) * step)


def count_ceil(value: float) -> int:
    """Smallest whole count that COVERS `value` (fans, filters — you cannot buy
    a fraction, and rounding down would under-provision). Never below 1."""
    return max(1, math.ceil(value))


def count_round(value: float) -> int:
    """Nearest whole count where over/under by a fraction is acceptable (spray
    nozzles balanced across a header). Never below 1."""
    return max(1, round(value))


def snap_to_nearest(value: float, options) -> float:
    """Nearest value from a set of standard sizes (e.g. standard tank litres).
    Returns `value` unchanged when no options are given."""
    if not options:
        return value
    return min(options, key=lambda s: abs(s - value))
