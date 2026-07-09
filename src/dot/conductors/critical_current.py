"""Strand and cable critical-current composition."""

from __future__ import annotations

import math

from .cadata import CableRecord, StrandRecord


def strand_critical_current(jc_a_per_m2: float, strand: StrandRecord) -> float:
    """Return strand Ic in A from superconductor Jc and strand dimensions.

    The strand is modeled as a circular cross-section with total area
    ``pi/4 * diameter_mm^2``. The catalogue Cu:SC ratio is interpreted as
    ``A_cu / A_sc``, so ``A_sc = A_total / (1 + Cu:SC)``. The area is converted
    from mm^2 to m^2 before multiplying by Jc in A/m^2.
    """

    _require_finite_nonnegative(jc_a_per_m2, "jc_a_per_m2")
    total_area_mm2 = math.pi * strand.diameter_mm * strand.diameter_mm / 4.0
    superconductor_area_m2 = total_area_mm2 / (1.0 + strand.cu_to_sc_ratio) * 1.0e-6
    current_a = jc_a_per_m2 * superconductor_area_m2
    if not math.isfinite(current_a) or current_a < 0.0:
        raise ValueError(f"strand critical current is invalid: {current_a!r}")
    return current_a


def cable_critical_current(
    jc_a_per_m2: float,
    strand: StrandRecord,
    cable: CableRecord,
) -> float:
    """Return cable Ic in A as independent strand Ic times count and degradation."""

    degradation_factor = 1.0 - cable.degradation_percent / 100.0
    current_a = cable.n_strands * strand_critical_current(jc_a_per_m2, strand) * degradation_factor
    if not math.isfinite(current_a) or current_a < 0.0:
        raise ValueError(f"cable critical current is invalid: {current_a!r}")
    return current_a


def _require_finite_nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
