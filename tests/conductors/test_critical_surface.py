from __future__ import annotations

import math

import pytest

from dot.conductors import Type1FitCoefficients, critical_current_density


COEFFS = Type1FitCoefficients(
    c1=3.0e9,
    c2=9.2,
    c3=0.57,
    c4=0.9,
    c5=2.32,
    c6=27.04,
    c7=14.5,
)


def _expected_jc(b_field_t: float, temperature_k: float, coeffs: Type1FitCoefficients) -> float:
    reduced_temperature = temperature_k / coeffs.c2
    reduced_temperature_power = reduced_temperature**1.7
    bc2_t = coeffs.c7 * (1.0 - reduced_temperature_power)
    reduced_field = b_field_t / bc2_t
    return (
        coeffs.c1
        * coeffs.c6
        * b_field_t ** (coeffs.c3 - 1.0)
        / bc2_t**coeffs.c3
        * (1.0 - reduced_field) ** coeffs.c4
        * (1.0 - reduced_temperature_power) ** coeffs.c5
    )


@pytest.mark.parametrize(
    ("b_field_t", "temperature_k"),
    [
        (2.0, 1.9),
        (6.0, 4.2),
        (8.0, 4.5),
    ],
)
def test_critical_current_density_matches_task_formula(
    b_field_t: float,
    temperature_k: float,
) -> None:
    assert math.isclose(
        critical_current_density(b_field_t, temperature_k, COEFFS),
        _expected_jc(b_field_t, temperature_k, COEFFS),
        rel_tol=1.0e-15,
    )


def test_critical_current_density_is_finite_positive_inside_domain() -> None:
    jc = critical_current_density(6.0, 4.2, COEFFS)

    assert math.isfinite(jc)
    assert jc > 0.0


def test_critical_current_density_decreases_as_field_increases() -> None:
    lower_field_jc = critical_current_density(4.0, 4.2, COEFFS)
    higher_field_jc = critical_current_density(8.0, 4.2, COEFFS)

    assert higher_field_jc < lower_field_jc


def test_critical_current_density_tends_to_zero_as_field_approaches_bc2() -> None:
    temperature_k = 4.2
    bc2_t = COEFFS.c7 * (1.0 - (temperature_k / COEFFS.c2) ** 1.7)

    farther = critical_current_density(bc2_t * (1.0 - 1.0e-3), temperature_k, COEFFS)
    nearer = critical_current_density(bc2_t * (1.0 - 1.0e-6), temperature_k, COEFFS)

    assert nearer < farther
    assert nearer < 1.0e-2 * farther


def test_critical_current_density_tends_to_zero_as_temperature_approaches_tc0() -> None:
    def jc_at_reduced_bc2_distance(epsilon: float) -> float:
        temperature_k = COEFFS.c2 * (1.0 - epsilon)
        bc2_t = COEFFS.c7 * (1.0 - (temperature_k / COEFFS.c2) ** 1.7)
        return critical_current_density(0.5 * bc2_t, temperature_k, COEFFS)

    farther = jc_at_reduced_bc2_distance(1.0e-3)
    nearer = jc_at_reduced_bc2_distance(1.0e-6)

    assert nearer < farther
    assert nearer < 1.0e-3 * farther


@pytest.mark.parametrize(
    ("b_field_t", "temperature_k"),
    [
        (-1.0, 4.2),
        (1.0, -1.0),
        (1.0, 9.2),
        (20.0, 4.2),
    ],
)
def test_critical_current_density_rejects_invalid_physical_inputs(
    b_field_t: float,
    temperature_k: float,
) -> None:
    with pytest.raises(ValueError):
        critical_current_density(b_field_t, temperature_k, COEFFS)
