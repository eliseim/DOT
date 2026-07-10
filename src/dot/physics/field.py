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
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from .sources import LineCurrentSource

MU0_OVER_2PI = 2.0e-7
MM_TO_M = 1.0e-3


class FieldSingularityError(ValueError):
    """Raised when a probe point coincides with a line-current source."""


@dataclass(frozen=True, slots=True)
class LineCurrentSourceArray:
    """Array-backed explicitly listed line-current sources."""

    x_mm: np.ndarray
    y_mm: np.ndarray
    current_a: np.ndarray

    @classmethod
    def from_arrays(
        cls,
        x_mm: ArrayLike,
        y_mm: ArrayLike,
        current_a: ArrayLike,
    ) -> "LineCurrentSourceArray":
        return cls(
            np.asarray(x_mm, dtype=np.float64),
            np.asarray(y_mm, dtype=np.float64),
            np.asarray(current_a, dtype=np.float64),
        )

    @classmethod
    def from_sources(cls, sources: Iterable[LineCurrentSource]) -> "LineCurrentSourceArray":
        source_tuple = tuple(sources)
        return cls(
            np.fromiter((source.x_mm for source in source_tuple), dtype=np.float64),
            np.fromiter((source.y_mm for source in source_tuple), dtype=np.float64),
            np.fromiter((source.current_a for source in source_tuple), dtype=np.float64),
        )

    @classmethod
    def from_compact_dipole_sources(
        cls,
        sources: Iterable[LineCurrentSource],
    ) -> "LineCurrentSourceArray":
        compact = cls.from_sources(sources)
        return cls(
            np.concatenate((compact.x_mm, -compact.x_mm, -compact.x_mm, compact.x_mm)),
            np.concatenate((compact.y_mm, compact.y_mm, -compact.y_mm, -compact.y_mm)),
            np.concatenate((compact.current_a, -compact.current_a, -compact.current_a, compact.current_a)),
        )

    def __post_init__(self) -> None:
        if self.x_mm.shape != self.y_mm.shape or self.x_mm.shape != self.current_a.shape:
            raise ValueError("source arrays must have matching shapes")
        if self.x_mm.ndim != 1:
            raise ValueError("source arrays must be one-dimensional")
        if (
            not np.all(np.isfinite(self.x_mm))
            or not np.all(np.isfinite(self.y_mm))
            or not np.all(np.isfinite(self.current_a))
        ):
            raise ValueError("source arrays must be finite")


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

    return field_at_explicit_sources(LineCurrentSourceArray.from_compact_dipole_sources(sources), x_mm, y_mm)


def field_at_explicit_sources(
    sources: Iterable[LineCurrentSource] | LineCurrentSourceArray,
    x_mm: float,
    y_mm: float,
) -> tuple[float, float]:
    """Return ``(Bx, By)`` in tesla from explicitly listed line currents."""

    _require_finite(x_mm, "x_mm")
    _require_finite(y_mm, "y_mm")
    source_array = sources if isinstance(sources, LineCurrentSourceArray) else LineCurrentSourceArray.from_sources(sources)
    bx_t, by_t = field_at_many_explicit_sources(source_array, (x_mm,), (y_mm,))
    return (float(bx_t[0]), float(by_t[0]))


def field_at_many(
    sources: Iterable[LineCurrentSource] | LineCurrentSourceArray,
    x_mm: ArrayLike,
    y_mm: ArrayLike,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(Bx, By)`` arrays using the dipole mirror construction."""

    source_array = sources if isinstance(sources, LineCurrentSourceArray) else LineCurrentSourceArray.from_compact_dipole_sources(sources)
    return field_at_many_explicit_sources(source_array, x_mm, y_mm)


def field_at_many_explicit_sources(
    sources: Iterable[LineCurrentSource] | LineCurrentSourceArray,
    x_mm: ArrayLike,
    y_mm: ArrayLike,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(Bx, By)`` arrays from explicitly listed line currents."""

    source_array = sources if isinstance(sources, LineCurrentSourceArray) else LineCurrentSourceArray.from_sources(sources)
    x_probe = np.asarray(x_mm, dtype=np.float64)
    y_probe = np.asarray(y_mm, dtype=np.float64)
    if x_probe.shape != y_probe.shape:
        raise ValueError("x_mm and y_mm must have matching shapes")
    if not np.all(np.isfinite(x_probe)) or not np.all(np.isfinite(y_probe)):
        raise ValueError("probe coordinates must be finite")

    probe_shape = x_probe.shape
    dx_m = (x_probe.reshape(-1, 1) - source_array.x_mm.reshape(1, -1)) * MM_TO_M
    dy_m = (y_probe.reshape(-1, 1) - source_array.y_mm.reshape(1, -1)) * MM_TO_M
    rho2_m2 = dx_m * dx_m + dy_m * dy_m
    if np.any(rho2_m2 == 0.0):
        raise FieldSingularityError("probe point coincides with a source")
    scale = MU0_OVER_2PI * source_array.current_a.reshape(1, -1) / rho2_m2
    bx_t = np.sum(-scale * dy_m, axis=1)
    by_t = np.sum(scale * dx_m, axis=1)
    return (bx_t.reshape(probe_shape), by_t.reshape(probe_shape))


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
