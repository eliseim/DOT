from __future__ import annotations

import math

import pytest

from dot.physics import LineCurrentSource, multipole_coefficients
from dot.physics.field import MM_TO_M, MU0_OVER_2PI


def expected_relative_multipoles(
    sources: tuple[LineCurrentSource, ...],
    order: int,
    r_ref_mm: float,
) -> tuple[tuple[float, float], ...]:
    r_ref_m = r_ref_mm * MM_TO_M
    absolute: list[complex] = []
    for harmonic in range(1, order + 1):
        total = 0.0j
        for source in sources:
            x = source.x_mm * MM_TO_M
            y = source.y_mm * MM_TO_M
            current = source.current_a
            images = (
                (complex(x, y), current),
                (complex(-x, y), -current),
                (complex(-x, -y), -current),
                (complex(x, -y), current),
            )
            for z0_m, image_current in images:
                total += (
                    -MU0_OVER_2PI
                    * image_current
                    * (r_ref_m ** (harmonic - 1))
                    / (z0_m**harmonic)
                )
        absolute.append(total)
    main = absolute[0].real
    return tuple((1.0e4 * value.real / main, 1.0e4 * value.imag / main) for value in absolute)


def test_symmetric_source_has_normal_dipole_and_zero_quadrupole_terms() -> None:
    source = LineCurrentSource(10.0, 20.0, 1000.0)

    coefficients = multipole_coefficients((source,), order=2, r_ref_mm=5.0)

    assert coefficients[0] == pytest.approx((10000.0, 0.0), abs=1e-10)
    assert coefficients[1] == pytest.approx((0.0, 0.0), abs=1e-10)


def test_asymmetric_compact_sources_match_independent_closed_form_reference() -> None:
    sources = (
        LineCurrentSource(10.0, 20.0, 1000.0),
        LineCurrentSource(14.0, 25.0, 600.0),
    )

    coefficients = multipole_coefficients(sources, order=3, r_ref_mm=5.0)
    expected = expected_relative_multipoles(sources, order=3, r_ref_mm=5.0)

    for actual_pair, expected_pair in zip(coefficients, expected, strict=True):
        assert actual_pair == pytest.approx(expected_pair, rel=1e-12, abs=1e-10)
    assert not math.isclose(coefficients[2][0], 0.0, abs_tol=1e-6)
