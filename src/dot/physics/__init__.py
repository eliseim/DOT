"""Physics utilities for DOT."""

from .field import (
    FieldSingularityError,
    dipole_mirror_sources,
    field_at,
    field_at_explicit_sources,
)
from .multipoles import absolute_multipole_coefficients, multipole_coefficients
from .sources import LineCurrentSource, place_line_current_sources

__all__ = [
    "FieldSingularityError",
    "LineCurrentSource",
    "absolute_multipole_coefficients",
    "dipole_mirror_sources",
    "field_at",
    "field_at_explicit_sources",
    "multipole_coefficients",
    "place_line_current_sources",
]
