"""Backward-compatibility shim.

The engineering rule engine was decomposed into the `app/engineering/` package
(formula_service + unit_converter + calculation_engine + standards_service +
material_service). This module re-exports the two public formula entry points so
existing imports (`from .rules import compute_spec, compute_wet_scrubber`) keep
working. New code should import from `app.engineering` directly.
"""
from .engineering.formula_service import compute_spec, compute_wet_scrubber

__all__ = ["compute_spec", "compute_wet_scrubber"]
