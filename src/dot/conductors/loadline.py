"""Short-sample current and load-line margin calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .cadata import CableRecord, RemfitCoefficients, StrandRecord
from .critical_current import cable_critical_current, strand_non_copper_area_m2
from .critical_surface import critical_current_density_for_fit, upper_critical_field


@dataclass(frozen=True, slots=True)
class ConservativeCurrentAdvice:
    """Current ceiling estimated by assuming ``Bpeak = Bbore`` in Layer 1."""

    maximum_current_a: float
    assumed_peak_field_t: float
    short_sample_field_t: float
    short_sample_current_a: float
    operating_fraction: float
    critical_current_density_a_per_mm2: float
    strand_total_area_mm2: float
    strand_non_copper_area_mm2: float
    cable_non_copper_area_mm2: float
    cu_to_non_cu_ratio: float
    cable_degradation_percent: float


def conservative_maximum_current_advice(
    coeffs: RemfitCoefficients,
    strand: StrandRecord,
    cable: CableRecord,
    temperature_k: float,
    bore_field_t: float,
    desired_margin_percent: float,
) -> ConservativeCurrentAdvice:
    """Estimate a user-facing upper current bound from the critical fit.

    Let ``f = 1 - margin/100``. Points on one linear load line scale from
    the origin, hence the short-sample field corresponding to an assumed
    operating peak ``Bop`` is ``Bss = Bop/f``. The fit supplies non-copper
    ``Jc(Bss,T)``; DOT multiplies it by
    ``Nstrands*pi*d^2/[4*(1+Cu/nonCu)]`` and the cadata cabling-degradation
    factor to obtain ``Ic_cable``. The advised operating current is then
    ``f * Ic_cable(Bss, T)``. In a real dipole ``Bpeak > Bbore``, so
    using ``Bop = Bbore`` makes this an optimistic upper-bound recommendation,
    never an
    automatically imposed constraint.
    """

    _require_finite_positive(bore_field_t, "bore_field_t")
    if (
        not math.isfinite(desired_margin_percent)
        or desired_margin_percent < 0.0
        or desired_margin_percent >= 100.0
    ):
        raise ValueError("desired_margin_percent must be finite in [0, 100)")
    operating_fraction = 1.0 - desired_margin_percent / 100.0
    short_sample_field_t = bore_field_t / operating_fraction
    jc = critical_current_density_for_fit(short_sample_field_t, temperature_k, coeffs)
    short_sample_current_a = cable_critical_current(jc, strand, cable)
    maximum_current_a = operating_fraction * short_sample_current_a
    strand_total_area_mm2 = math.pi * strand.diameter_mm**2 / 4.0
    strand_non_copper_area_mm2 = strand_non_copper_area_m2(strand) * 1.0e6
    cable_non_copper_area_mm2 = cable.n_strands * strand_non_copper_area_mm2
    return ConservativeCurrentAdvice(
        maximum_current_a=maximum_current_a,
        assumed_peak_field_t=bore_field_t,
        short_sample_field_t=short_sample_field_t,
        short_sample_current_a=short_sample_current_a,
        operating_fraction=operating_fraction,
        critical_current_density_a_per_mm2=jc * 1.0e-6,
        strand_total_area_mm2=strand_total_area_mm2,
        strand_non_copper_area_mm2=strand_non_copper_area_mm2,
        cable_non_copper_area_mm2=cable_non_copper_area_mm2,
        cu_to_non_cu_ratio=strand.cu_to_non_cu_ratio,
        cable_degradation_percent=cable.degradation_percent,
    )


def solve_short_sample_current(
    coeffs: RemfitCoefficients,
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
    # Guard in *field* space before converting to current. Moving one ULP
    # below ``Bc2/k`` in current space is insufficient: multiplying the
    # resulting current by ``k`` can round straight back to Bc2 and violate
    # the critical-surface domain. The relative guard is many orders below
    # any engineering or solver tolerance while remaining numerically stable.
    domain_upper = (bc2_t * (1.0 - 1.0e-12)) / k_field_per_current
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
    coeffs: RemfitCoefficients,
    strand: StrandRecord,
    cable: CableRecord,
    temperature_k: float,
    k_field_per_current: float,
    current_a: float,
) -> float:
    field_t = k_field_per_current * current_a
    jc = critical_current_density_for_fit(field_t, temperature_k, coeffs)
    value = cable_critical_current(jc, strand, cable) - current_a
    if not math.isfinite(value):
        raise ValueError("load-line equation produced a non-finite value")
    return value


def _bc2(coeffs: RemfitCoefficients, temperature_k: float) -> float:
    return upper_critical_field(coeffs, temperature_k)


def _require_finite_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive, got {value!r}")


def _require_finite_nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
