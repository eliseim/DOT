from __future__ import annotations

import math

import pytest

from dot.conductors import (
    CableRecord,
    StrandRecord,
    Type1FitCoefficients,
    conservative_maximum_current_advice,
    load_line_margin_percent,
    solve_short_sample_current,
)
from dot.conductors.cadata import Type11FitCoefficients


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


def test_short_sample_solver_accepts_type11_nb3sn_coefficients() -> None:
    coeffs = Type11FitCoefficients(
        c0=2.14462e11,
        bc20_t=29.38,
        tc0_k=16.0,
        alpha=0.96,
        v=1.52,
        p=0.5,
        q=2.0,
    )
    strand = StrandRecord(diameter_mm=0.85, cu_to_sc_ratio=1.2)
    cable = CableRecord(n_strands=40, degradation_percent=2.0)

    solved = solve_short_sample_current(
        coeffs,
        strand,
        cable,
        temperature_k=1.9,
        k_field_per_current=1.0e-3,
    )

    assert math.isfinite(solved)
    assert solved > 0.0


def test_conservative_current_advice_lands_on_requested_loadline_fraction() -> None:
    coeffs = Type11FitCoefficients(
        c0=2.14462e11,
        bc20_t=29.38,
        tc0_k=16.0,
        alpha=0.96,
        v=1.52,
        p=0.5,
        q=2.0,
    )
    strand = StrandRecord(diameter_mm=0.85, cu_to_sc_ratio=0.9)
    cable = CableRecord(n_strands=40, degradation_percent=5.0)

    advice = conservative_maximum_current_advice(
        coeffs,
        strand,
        cable,
        temperature_k=1.9,
        bore_field_t=12.4,
        desired_margin_percent=25.0,
    )
    solved_short_sample = solve_short_sample_current(
        coeffs,
        strand,
        cable,
        temperature_k=1.9,
        k_field_per_current=12.4 / advice.maximum_current_a,
    )

    assert advice.operating_fraction == 0.75
    assert advice.short_sample_field_t == 12.4 / 0.75
    total_area_mm2 = math.pi * strand.diameter_mm**2 / 4.0
    strand_non_copper_area_mm2 = total_area_mm2 / (1.0 + 0.9)
    cable_non_copper_area_mm2 = cable.n_strands * strand_non_copper_area_mm2
    expected_short_sample_a = (
        advice.critical_current_density_a_per_mm2
        * cable_non_copper_area_mm2
        * (1.0 - cable.degradation_percent / 100.0)
    )
    assert advice.cu_to_non_cu_ratio == pytest.approx(0.9)
    assert advice.strand_total_area_mm2 == pytest.approx(total_area_mm2)
    assert advice.strand_non_copper_area_mm2 == pytest.approx(
        strand_non_copper_area_mm2
    )
    assert advice.cable_non_copper_area_mm2 == pytest.approx(
        cable_non_copper_area_mm2
    )
    assert advice.short_sample_current_a == pytest.approx(expected_short_sample_a)
    assert advice.maximum_current_a == advice.operating_fraction * advice.short_sample_current_a
    assert solved_short_sample == pytest.approx(advice.short_sample_current_a, rel=1.0e-8)
    assert load_line_margin_percent(
        advice.maximum_current_a, solved_short_sample
    ) == pytest.approx(25.0, abs=1.0e-8)


def test_current_advice_does_not_confuse_fit_alpha_with_cu_non_cu_ratio() -> None:
    coeffs = Type11FitCoefficients(
        c0=2.14462e11,
        bc20_t=29.38,
        tc0_k=16.0,
        alpha=0.96,
        v=1.52,
        p=0.5,
        q=2.0,
    )
    cable = CableRecord(n_strands=40, degradation_percent=5.0)
    advice_09 = conservative_maximum_current_advice(
        coeffs,
        StrandRecord(diameter_mm=0.85, cu_to_sc_ratio=0.9),
        cable,
        temperature_k=1.9,
        bore_field_t=12.4,
        desired_margin_percent=25.0,
    )
    advice_12 = conservative_maximum_current_advice(
        coeffs,
        StrandRecord(diameter_mm=0.85, cu_to_sc_ratio=1.2),
        cable,
        temperature_k=1.9,
        bore_field_t=12.4,
        desired_margin_percent=25.0,
    )

    assert coeffs.alpha == pytest.approx(0.96)
    assert advice_09.cu_to_non_cu_ratio == pytest.approx(0.9)
    assert advice_12.cu_to_non_cu_ratio == pytest.approx(1.2)
    assert advice_09.maximum_current_a / advice_12.maximum_current_a == pytest.approx(
        (1.0 + 1.2) / (1.0 + 0.9)
    )
