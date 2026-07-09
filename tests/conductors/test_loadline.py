from __future__ import annotations

import math

from dot.conductors import (
    CableRecord,
    StrandRecord,
    Type1FitCoefficients,
    load_line_margin_percent,
    solve_short_sample_current,
)


def test_short_sample_solver_matches_closed_form_linear_case() -> None:
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    area_m2 = math.pi * 1.0**2 / 4.0 * 1.0e-6
    target_zero_field_cable_current_a = 1000.0
    coeffs = Type1FitCoefficients(
        c1=10.0 * target_zero_field_cable_current_a / area_m2,
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=10.0,
    )
    temperature_k = 0.0
    k_field_per_current = 1.0e-3
    expected_short_sample = target_zero_field_cable_current_a / (
        1.0 + target_zero_field_cable_current_a * k_field_per_current / coeffs.c7
    )

    solved = solve_short_sample_current(
        coeffs,
        strand,
        cable,
        temperature_k,
        k_field_per_current,
        tol=1.0e-9,
    )

    assert math.isclose(solved, expected_short_sample, rel_tol=0.0, abs_tol=1.0e-6)


def test_load_line_margin_percent_matches_definition() -> None:
    margin = load_line_margin_percent(i_operating=700.0, i_short_sample=1000.0)
    expected = 100.0 * (1.0 - 700.0 / 1000.0)

    assert margin > 0.0
    assert math.isclose(margin, expected, rel_tol=0.0, abs_tol=1.0e-12)
