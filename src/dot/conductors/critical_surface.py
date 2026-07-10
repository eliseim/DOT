"""Bottura Nb-Ti critical-current density fit."""

from __future__ import annotations

import math

from .cadata import RemfitCoefficients, Type1FitCoefficients, Type11FitCoefficients


def critical_current_density(
    b_field_t: float,
    temperature_k: float,
    coeffs: Type1FitCoefficients,
) -> float:
    """Return Bottura Nb-Ti REMFIT type-1 ``Jc(B,T)`` in A/m^2.

    Implemented formula:
    ``C1*C6*B^(C3-1)/Bc2(T)^C3*(1-B/Bc2(T))^C4*(1-(T/C2)^1.7)^C5``.
    """

    _validate_scalar(b_field_t, "b_field_t")
    _validate_scalar(temperature_k, "temperature_k")
    if b_field_t < 0.0:
        raise ValueError("b_field_t must be non-negative")
    if temperature_k < 0.0:
        raise ValueError("temperature_k must be non-negative")
    if temperature_k >= coeffs.c2:
        raise ValueError("temperature_k must be less than Tc0")

    reduced_temperature = temperature_k / coeffs.c2
    reduced_temperature_power = reduced_temperature**1.7
    bc2_t = coeffs.c7 * (1.0 - reduced_temperature_power)
    if not math.isfinite(bc2_t) or bc2_t <= 0.0:
        raise ValueError(f"Bc2(T) must be finite and positive, got {bc2_t!r}")
    if b_field_t >= bc2_t:
        raise ValueError("b_field_t must be less than Bc2(T)")
    if b_field_t == 0.0 and coeffs.c3 < 1.0:
        raise ValueError("Jc(B,T) is singular at B=0 for C3 < 1")

    reduced_field = b_field_t / bc2_t
    jc = (
        coeffs.c1
        * coeffs.c6
        * (b_field_t ** (coeffs.c3 - 1.0))
        / (bc2_t**coeffs.c3)
        * ((1.0 - reduced_field) ** coeffs.c4)
        * ((1.0 - reduced_temperature_power) ** coeffs.c5)
    )
    if not math.isfinite(jc) or jc < 0.0:
        raise ValueError(f"Jc evaluation produced an invalid value: {jc!r}")
    return jc


def critical_current_density_nb3sn(
    b_field_t: float,
    temperature_k: float,
    coeffs: Type11FitCoefficients,
) -> float:
    """Return CERN high-field Nb3Sn REMFIT type-11 ``Jc(B,T)`` in A/m^2."""

    _validate_scalar(b_field_t, "b_field_t")
    _validate_scalar(temperature_k, "temperature_k")
    if b_field_t < 0.0:
        raise ValueError("b_field_t must be non-negative")
    if temperature_k < 0.0:
        raise ValueError("temperature_k must be non-negative")
    if temperature_k >= coeffs.tc0_k:
        raise ValueError("temperature_k must be less than Tc0")

    bc2_t = upper_critical_field(coeffs, temperature_k)
    if b_field_t >= bc2_t:
        raise ValueError("b_field_t must be less than Bc2(T)")
    if b_field_t == 0.0 and coeffs.p < 1.0:
        raise ValueError("Jc(B,T) is singular at B=0 for p < 1")

    reduced_temperature = temperature_k / coeffs.tc0_k
    reduced_temperature_v = reduced_temperature**coeffs.v
    reduced_field = b_field_t / bc2_t
    c_t = (
        coeffs.c0
        * ((1.0 - reduced_temperature_v) ** coeffs.alpha)
        * ((1.0 - reduced_temperature**2) ** coeffs.alpha)
    )
    jc = c_t / b_field_t * (reduced_field**coeffs.p) * ((1.0 - reduced_field) ** coeffs.q)
    if not math.isfinite(jc) or jc < 0.0:
        raise ValueError(f"Jc evaluation produced an invalid value: {jc!r}")
    return jc


def critical_current_density_for_fit(
    b_field_t: float,
    temperature_k: float,
    coeffs: RemfitCoefficients,
) -> float:
    """Return ``Jc(B,T)`` for a supported REMFIT coefficient set."""

    if isinstance(coeffs, Type1FitCoefficients):
        return critical_current_density(b_field_t, temperature_k, coeffs)
    return critical_current_density_nb3sn(b_field_t, temperature_k, coeffs)


def upper_critical_field(coeffs: RemfitCoefficients, temperature_k: float) -> float:
    """Return ``Bc2(T)`` for a supported REMFIT coefficient set."""

    if not math.isfinite(temperature_k):
        raise ValueError("temperature_k must be finite")
    if temperature_k < 0.0:
        raise ValueError("temperature_k must be non-negative")
    if isinstance(coeffs, Type1FitCoefficients):
        if temperature_k >= coeffs.c2:
            raise ValueError("temperature_k must be less than Tc0")
        bc2_t = coeffs.c7 * (1.0 - (temperature_k / coeffs.c2) ** 1.7)
    else:
        if temperature_k >= coeffs.tc0_k:
            raise ValueError("temperature_k must be less than Tc0")
        bc2_t = coeffs.bc20_t * (1.0 - (temperature_k / coeffs.tc0_k) ** coeffs.v)
    if not math.isfinite(bc2_t) or bc2_t <= 0.0:
        raise ValueError(f"Bc2(T) must be finite and positive, got {bc2_t!r}")
    return bc2_t


def _validate_scalar(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
