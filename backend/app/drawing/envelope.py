"""Compatibility shim — the geometry model now lives in the ENGINEERING package.

Deriving an envelope here meant the RENDERER decided what kind of machine it was
looking at, by pattern-matching specification row labels. That let the drawing
and the specification reach different conclusions about one resolved spec, and it
hid each category's geometry rule from every consumer that is not the drawing.

The model moved to `app/engineering/geometry_service.py`, which also resolves the
equipment TYPE (a wet scrubber is a vertical spray tower or a horizontal baffle
unit, and they are not the same shape). Import from there for new work; this
wrapper stays so existing callers and tests keep working.
"""
from ..engineering.geometry_service import (  # noqa: F401
    TRUSTED_ORIGINS as _TRUSTED_ORIGINS,
    derive_envelope,
    resolve_geometry,
)

__all__ = ["derive_envelope", "resolve_geometry"]
