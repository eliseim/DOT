from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.genome import decode
from dot.optimize.operating_point import operating_point
from dot.optimize.problem import (
    DipoleOptimizationProblem,
    FeasibilitySettings,
    OptimizationTargets,
    solve_operating_point,
)


def test_problem_rejects_overlapping_turns_before_physics() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    genome = np.asarray([12.0, 20.0, 1.0, 20.0, 1.0, 1.0, 0.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert constraints[0] > 0.0
    assert objectives[0] >= 1.0e12


def test_problem_evaluates_both_objectives_for_feasible_geometry() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert problem.constraint_names == ("geometry",)
    assert constraints[0] <= 0.0


def test_problem_exposes_radiality_only_as_a_target_gated_preference_signal() -> None:
    targets = _targets(
        max_harmonic_units=1.0e9,
        min_margin_percent=0.0,
        prefer_radial_design=True,
    )
    problem = DipoleOptimizationProblem(_topology(), targets, _feasibility())
    genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])

    objectives, constraints, radiality, eligible = problem.evaluate(
        genome,
        return_values_of=[
            "F",
            "G",
            "radiality",
            "radial_preference_eligible",
        ],
    )

    assert np.all(np.isfinite(objectives))
    assert np.all(constraints <= 0.0)
    assert np.isfinite(radiality)
    assert bool(eligible)
    assert objectives[0] < 1.0e12
    assert objectives[1] < 0.0


def test_harmonic_and_margin_targets_are_certification_limits_not_search_constraints() -> None:
    targets = _targets(max_harmonic_units=1.0e-9, min_margin_percent=99.0)
    problem = DipoleOptimizationProblem(_topology(), targets, _feasibility())
    genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert problem.constraint_names == ("geometry",)
    assert constraints[0] <= 0.0
    assert np.all(np.isfinite(objectives))


def test_parallel_evaluation_matches_sequential_exactly() -> None:
    topology = _topology()
    targets = _targets(max_current_a=13000.0)
    feasibility = _feasibility()
    batch = np.asarray(
        [
            [12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0],
            [12.0, 20.0, 1.0, 20.0, 1.0, 1.0, 0.0],
            [8.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0],
            [14.0, 45.0, 2.0, 12.0, 2.0, 2.0, 1.0],
        ]
    )
    sequential = DipoleOptimizationProblem(topology, targets, feasibility)
    expected_f, expected_g = sequential.evaluate(batch, return_values_of=["F", "G"])
    parallel = DipoleOptimizationProblem(topology, targets, feasibility, n_workers=2)
    try:
        actual_f, actual_g = parallel.evaluate(batch, return_values_of=["F", "G"])
    finally:
        parallel.close()

    np.testing.assert_array_equal(actual_f, expected_f)
    np.testing.assert_array_equal(actual_g, expected_g)


def test_exact_evaluation_cache_reuses_duplicate_genomes() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])
    batch = np.asarray([genome, genome.copy()])

    first_f, first_g = problem.evaluate(batch, return_values_of=["F", "G"])
    second_f, second_g = problem.evaluate(batch, return_values_of=["F", "G"])

    np.testing.assert_array_equal(first_f, second_f)
    np.testing.assert_array_equal(first_g, second_g)
    assert problem.evaluation_cache_misses == 1
    assert problem.evaluation_cache_hits == 3


def test_current_range_is_always_a_hard_constraint() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_current_a=180.0),
        _feasibility(),
    )
    genome = np.asarray([12.0, 10.0, 1.0, 50.0, 1.0, 1.0, 70.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert problem.constraint_names == ("geometry", "current")
    assert constraints[0] <= 0.0
    assert constraints[1] > 0.0
    assert objectives[0] < 1.0e12
    assert objectives[1] < 0.0


def test_minimum_current_is_a_hard_constraint() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(min_current_a=180.0),
        _feasibility(),
    )
    genome = np.asarray([12.0, 10.0, 1.0, 40.0, 2.0, 1.0, 30.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert constraints[0] <= 0.0
    assert constraints[1] > 0.0
    assert objectives[0] < 1.0e12


def test_equal_current_bounds_fix_current_and_constrain_bore_field() -> None:
    topology = _topology()
    genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])
    unit_design = decode(genome, topology, topology.cables)
    required_current_a = abs(operating_point(unit_design, 0.02).operating_current_a)
    targets = _targets(
        min_current_a=required_current_a,
        max_current_a=required_current_a,
    )
    problem = DipoleOptimizationProblem(topology, targets, _feasibility())

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])
    solved = solve_operating_point(unit_design, targets)

    assert problem.constraint_names == ("geometry", "fixed_current_field")
    assert np.all(constraints <= 0.0)
    assert abs(solved.operating_current_a) == pytest.approx(required_current_a)
    assert solved.unit_bore_field_t * solved.scale_factor == pytest.approx(0.02)
    assert objectives[0] < 1.0e12

    mismatched = DipoleOptimizationProblem(
        topology,
        _targets(min_current_a=180.0, max_current_a=180.0),
        _feasibility(),
    )
    mismatch_g = mismatched.evaluate(genome, return_values_of=["G"])
    assert mismatch_g[1] > 0.0


def test_turn_budgets_are_hard_constraints() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_total_turns=2, max_turns_per_layer=2),
        _feasibility(),
    )
    genome = np.asarray([12.0, 10.0, 2.0, 45.0, 2.0, 1.0, 0.0])

    objectives, constraints = problem.evaluate(genome, return_values_of=["F", "G"])

    assert problem.constraint_names == ("geometry", "total_turns", "turns_per_layer")
    assert constraints[0] <= 0.0
    assert constraints[1] == pytest.approx(1.0)
    assert constraints[2] == pytest.approx(1.0)
    assert objectives[0] >= 1.0e12


def test_targets_require_supported_conductor_data_for_every_layer() -> None:
    with pytest.raises(ValueError, match="supported conductor data"):
        replace(_targets(), cadata_by_layer=(None,))  # type: ignore[arg-type]

    targets = replace(_targets(), cadata_by_layer=())
    with pytest.raises(ValueError, match="one entry per topology layer"):
        DipoleOptimizationProblem(_topology(), targets, _feasibility())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("target_bore_field_t", -1.0, "target_bore_field_t"),
        ("r_ref_mm", 0.0, "r_ref_mm"),
        ("max_order", 2, "max_order"),
        ("temperature_k", 0.0, "temperature_k"),
        ("max_harmonic_units", 0.0, "max_harmonic_units"),
        ("min_margin_percent", 100.0, "min_margin_percent"),
        ("max_total_turns", 0, "max_total_turns"),
    ],
)
def test_targets_reject_nonphysical_values(
    field_name: str,
    value: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_targets(), **{field_name: value})


def test_targets_reject_inverted_current_range() -> None:
    with pytest.raises(ValueError, match="min_current_a must not exceed max_current_a"):
        _targets(min_current_a=13001.0, max_current_a=13000.0)


def test_problem_rejects_reference_radius_outside_aperture() -> None:
    targets = replace(_targets(), r_ref_mm=_topology().aperture_radius_mm)
    with pytest.raises(ValueError, match="smaller than the aperture"):
        DipoleOptimizationProblem(_topology(), targets, _feasibility())


@pytest.mark.parametrize(
    "settings",
    [
        {"min_gap_mm": -0.1},
        {"min_gap_mm": 0.0, "min_layer_clearance_mm": float("nan")},
        {"min_gap_mm": 0.0, "geometry_tolerance_mm": -0.001},
        {"min_gap_mm": 0.0, "enforce_layer_nesting": "false"},
    ],
)
def test_feasibility_settings_reject_invalid_values(settings: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        FeasibilitySettings(**settings)


def _topology() -> Topology:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(12.0, 14.0),
                phi_bounds_deg=(10.0, 50.0),
                n_turns_bounds=(1, 2),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
        ),
        cables={"inner": cable},
    )


def _targets(
    *,
    min_current_a: float | None = None,
    max_current_a: float | None = None,
    max_harmonic_units: float | None = None,
    min_margin_percent: float | None = None,
    max_total_turns: int | None = None,
    max_turns_per_layer: int | None = None,
    prefer_radial_design: bool = False,
) -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.02,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=1.9,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
        min_current_a=min_current_a,
        max_current_a=max_current_a,
        max_total_turns=max_total_turns,
        max_turns_per_layer=max_turns_per_layer,
        prefer_radial_design=prefer_radial_design,
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)


def conductor_data() -> LayerConductorData:
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    remfit = Type1FitCoefficients(
        c1=10.0 * 5000.0 / (np.pi * 1.0**2 / 4.0 * 1.0e-6),
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=10.0,
    )
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)
