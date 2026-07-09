"""Two-dimensional Biot-Savart magnetic field.

Unit convention: geometry coordinates are millimetres, currents are amperes,
and returned magnetic-field components are tesla.  Millimetre distances are
converted to metres inside the Biot-Savart calculation.

The public ``field_at`` function assumes the input sources are compact
first-quadrant sources for a no-iron, mirror-symmetric 2D dipole.  It expands
each source into the four-image orbit ``(x, y, I)``, ``(-x, y, -I)``,
``(-x, -y, -I)``, and ``(x, -y, I)`` internally.  Use
``field_at_explicit_sources`` when the source list already contains every
physical line current and no mirror construction should be applied.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from .sources import LineCurrentSource

MU0_OVER_2PI = 2.0e-7
MM_TO_M = 1.0e-3


class FieldSingularityError(ValueError):
    """Raised when a probe point coincides with a line-current source."""


def dipole_mirror_sources(source: LineCurrentSource) -> tuple[LineCurrentSource, ...]:
    """Return the four source images for the DOT 2D normal-dipole symmetry."""

    x = source.x_mm
    y = source.y_mm
    current = source.current_a
    return (
        source,
        LineCurrentSource(-x, y, -current),
        LineCurrentSource(-x, -y, -current),
        LineCurrentSource(x, -y, current),
    )


def field_at(
    sources: Iterable[LineCurrentSource],
    x_mm: float,
    y_mm: float,
) -> tuple[float, float]:
    """Return ``(Bx, By)`` in tesla using the dipole mirror construction."""

    expanded = (image for source in sources for image in dipole_mirror_sources(source))
    return field_at_explicit_sources(expanded, x_mm, y_mm)


def field_at_explicit_sources(
    sources: Iterable[LineCurrentSource],
    x_mm: float,
    y_mm: float,
) -> tuple[float, float]:
    """Return ``(Bx, By)`` in tesla from explicitly listed line currents."""

    _require_finite(x_mm, "x_mm")
    _require_finite(y_mm, "y_mm")
    bx_terms: list[float] = []
    by_terms: list[float] = []
    for source in sources:
        dx_m = (x_mm - source.x_mm) * MM_TO_M
        dy_m = (y_mm - source.y_mm) * MM_TO_M
        rho2_m2 = dx_m * dx_m + dy_m * dy_m
        if rho2_m2 == 0.0:
            raise FieldSingularityError("probe point coincides with a source")
        scale = MU0_OVER_2PI * source.current_a / rho2_m2
        bx_terms.append(-scale * dy_m)
        by_terms.append(scale * dx_m)
    return (math.fsum(bx_terms), math.fsum(by_terms))


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
