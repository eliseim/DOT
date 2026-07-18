"""Analytic accelerator multipoles from line-current sources."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .field import MM_TO_M, MU0_OVER_2PI
from .sources import LineCurrentSource


def multipole_coefficients(
    sources: Iterable[LineCurrentSource],
    order: int,
    r_ref_mm: float,
) -> tuple[tuple[float, float], ...]:
    """Return relative ``(b_n, a_n)`` coefficients through ``order``.

    The convention is ``B_y + i B_x = sum(C_n * (z / r_ref) ** (n - 1))``.
    ``b_n`` and ``a_n`` are the real and imaginary parts of ``C_n / C_1`` in
    CERN/European relative units, i.e. multiplied by ``1e4``.  Therefore
    ``b_1`` is ``10000`` for a normal dipole and skew terms are ``a_n``.
    """

    source_tuple = tuple(sources)
    _validate_inputs(source_tuple, order, r_ref_mm)
    absolute = _absolute_coefficients(source_tuple, order, r_ref_mm)
    main = absolute[0].real
    if main == 0.0 or not math.isfinite(main):
        raise ValueError("main normal dipole coefficient must be finite and nonzero")
    relative: list[tuple[float, float]] = []
    for coefficient in absolute:
        b_n = 1.0e4 * coefficient.real / main
        a_n = 1.0e4 * coefficient.imag / main
        if not math.isfinite(b_n) or not math.isfinite(a_n):
            raise ValueError("multipole coefficient must be finite")
        relative.append((b_n, a_n))
    return tuple(relative)


def absolute_multipole_coefficients(
    sources: Iterable[LineCurrentSource],
    order: int,
    r_ref_mm: float,
) -> tuple[complex, ...]:
    """Return absolute complex ``C_n`` coefficients in tesla."""

    source_tuple = tuple(sources)
    _validate_inputs(source_tuple, order, r_ref_mm)
    return _absolute_coefficients(source_tuple, order, r_ref_mm)


def _absolute_coefficients(
    sources: tuple[LineCurrentSource, ...],
    order: int,
    r_ref_mm: float,
) -> tuple[complex, ...]:
    r_ref_m = r_ref_mm * MM_TO_M
    coefficients: list[complex] = []
    for harmonic in range(1, order + 1):
        # The four-image normal-dipole orbit makes every even and every skew
        # coefficient cancel analytically. For odd n its sum is exactly four
        # times the real part of the compact first-quadrant contribution.
        # Exploiting that identity avoids allocating 4 * sources * orders
        # temporary LineCurrentSource objects while retaining math.fsum's
        # stable accumulation for the physically non-zero terms.
        if harmonic % 2 == 0:
            coefficients.append(0.0j)
            continue
        scale = -4.0 * MU0_OVER_2PI * (r_ref_m ** (harmonic - 1))
        normal = math.fsum(
            (
                source.current_a
                / complex(source.x_mm * MM_TO_M, source.y_mm * MM_TO_M) ** harmonic
            ).real
            for source in sources
        )
        coefficients.append(complex(scale * normal, 0.0))
    return tuple(coefficients)


def _validate_inputs(
    sources: tuple[LineCurrentSource, ...],
    order: int,
    r_ref_mm: float,
) -> None:
    if not sources:
        raise ValueError("at least one source is required")
    if isinstance(order, bool) or not isinstance(order, int) or order < 1:
        raise ValueError("order must be a positive integer")
    if not math.isfinite(r_ref_mm) or r_ref_mm <= 0.0:
        raise ValueError("r_ref_mm must be positive and finite")
    min_radius = min(source.radius_mm for source in sources)
    if min_radius == 0.0:
        raise ValueError("sources must not be at the expansion origin")
    if r_ref_mm >= min_radius:
        raise ValueError("r_ref_mm must be smaller than every source radius")
