"""Short-sample current and load-line margin calculations."""

from __future__ import annotations

import math

from .cadata import CableRecord, StrandRecord, Type1FitCoefficients
from .critical_current import cable_critical_current
from .critical_surface import critical_current_density


def solve_short_sample_current(
    coeffs: Type1FitCoefficients,
    strand: StrandRecord,
    cable: CableRecord,
    temperature_k: float,
    k_field_per_current: float,
    i_lo: float = 1.0,
    i_hi: float | None = None,
    tol: float = 1.0e-6,
    max_iterations: int = 200,
) -> float:
    """Solve ``Ic_cable(k*I,T) = I`` by bisection.

    The upper bracket is limited to just below ``Bc2(T) / k`` so every critical
    surface evaluation stays inside its documented physical domain.
    """

    _require_finite_positive(k_field_per_current, "k_field_per_current")
    _require_finite_positive(i_lo, "i_lo")
    _require_finite_positive(tol, "tol")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be an integer")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")

    bc2_t = _bc2(coeffs, temperature_k)
    domain_upper = math.nextafter(bc2_t / k_field_per_current, 0.0)
    if not math.isfinite(domain_upper) or domain_upper <= 0.0:
        raise ValueError("load-line upper domain bound must be finite and positive")
    upper = domain_upper if i_hi is None else min(i_hi, domain_upper)
    _require_finite_positive(upper, "i_hi")
    if not i_lo < upper:
        raise ValueError("i_lo must be less than the effective upper bracket")

    f_lo = _equation(coeffs, strand, cable, temperature_k, k_field_per_current, i_lo)
    f_hi = _equation(coeffs, strand, cable, temperature_k, k_field_per_current, upper)
    if f_lo < 0.0:
        raise ValueError("lower bracket is already above the short-sample current")
    if f_hi > 0.0:
        raise ValueError("upper bracket is below the short-sample current")
    if f_lo == 0.0:
        return i_lo
    if f_hi == 0.0:
        return upper

    lower = i_lo
    for _ in range(max_iterations):
        midpoint = (lower + upper) / 2.0
        residual = _equation(coeffs, strand, cable, temperature_k, k_field_per_current, midpoint)
        if residual == 0.0 or (upper - lower) / 2.0 <= tol:
            return midpoint
        if residual > 0.0:
            lower = midpoint
        else:
            upper = midpoint
    raise ValueError(
        f"short-sample bisection did not converge within {max_iterations} iterations"
    )


def load_line_margin_percent(i_operating: float, i_short_sample: float) -> float:
    """Return current margin as ``100 * (1 - I_operating / I_short_sample)``."""

    _require_finite_nonnegative(i_operating, "i_operating")
    _require_finite_positive(i_short_sample, "i_short_sample")
    return 100.0 * (1.0 - i_operating / i_short_sample)


def _equation(
    coeffs: Type1FitCoefficients,
    strand: StrandRecord,
    cable: CableRecord,
    temperature_k: float,
    k_field_per_current: float,
    current_a: float,
) -> float:
    field_t = k_field_per_current * current_a
    jc = critical_current_density(field_t, temperature_k, coeffs)
    value = cable_critical_current(jc, strand, cable) - current_a
    if not math.isfinite(value):
        raise ValueError("load-line equation produced a non-finite value")
    return value


def _bc2(coeffs: Type1FitCoefficients, temperature_k: float) -> float:
    if not math.isfinite(temperature_k):
        raise ValueError("temperature_k must be finite")
    if temperature_k < 0.0:
        raise ValueError("temperature_k must be non-negative")
    if temperature_k >= coeffs.c2:
        raise ValueError("temperature_k must be less than Tc0")
    return coeffs.c7 * (1.0 - (temperature_k / coeffs.c2) ** 1.7)


def _require_finite_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive, got {value!r}")


def _require_finite_nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
