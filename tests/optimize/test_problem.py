from __future__ import annotations

import numpy as np

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import (
    AdmissionSchedule,
    AdmissionStage,
    DipoleOptimizationProblem,
    FeasibilitySettings,
    OptimizationTargets,
)


def test_problem_marks_overlapping_turns_as_constraint_violation() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    infeasible_genome = np.asarray([12.0, 20.0, 1.0, 20.0, 1.0, 1.0, 0.0])

    f_values, g_values = problem.evaluate(infeasible_genome, return_values_of=["F", "G"])

    assert g_values[0] > 0.0
    assert f_values[0] >= 1.0e12


def test_problem_reports_graded_geometry_constraint_severity() -> None:
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=1,
                inner_radius_bounds_mm=(6.0, 10.0),
                phi_bounds_deg=(20.0, 20.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)},
    )
    problem = DipoleOptimizationProblem(topology, _targets(), _feasibility())
    barely_infeasible = np.asarray([8.0, 20.0, 1.0])
    badly_infeasible = np.asarray([6.0, 20.0, 1.0])

    barely_g = problem.evaluate(barely_infeasible, return_values_of=["G"])
    badly_g = problem.evaluate(badly_infeasible, return_values_of=["G"])

    assert barely_g[0] > 0.0
    assert badly_g[0] > barely_g[0]


def test_problem_accepts_feasible_genome() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    feasible_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])

    f_values, g_values = problem.evaluate(feasible_genome, return_values_of=["F", "G"])

    assert g_values[0] <= 0.0
    assert f_values[0] < 1.0e12
    assert f_values[1] < 0.0


def test_problem_compares_harmonic_constraint_without_erroneous_1e4_rescale() -> None:
    # field_quality_objective's raw return value is already in CERN/European
    # relative "units" (multipole_coefficients' own docstring: "multiplied
    # by 1e4 -- b_1 is 10000 for a normal dipole"). Confirmed against the
    # real CTH-14T design: its field_quality_objective is ~2.0, sensibly
    # comparable to a target like 5.0 units. A prior version of this code
    # divided the target by 1e4 before comparing, making the threshold
    # ~10000x too strict (effectively unsatisfiable by any real design).
    feasible_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])
    baseline_problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    f_values = baseline_problem.evaluate(feasible_genome, return_values_of=["F"])
    field_quality = float(f_values[0])
    assert field_quality > 0.0, "test needs a genome with nonzero harmonic content to be meaningful"

    lenient_problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_harmonic_units=field_quality * 10.0),
        _feasibility(),
        total_generations=1,
    )
    lenient_problem.set_generation(1)
    lenient_g = lenient_problem.evaluate(feasible_genome, return_values_of=["G"])
    assert np.all(lenient_g <= 0.0), "a threshold well above the actual field quality must admit it"

    strict_problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_harmonic_units=field_quality / 10.0),
        _feasibility(),
        total_generations=1,
    )
    strict_problem.set_generation(1)
    strict_g = strict_problem.evaluate(feasible_genome, return_values_of=["G"])
    assert np.any(strict_g > 0.0), "a threshold well below the actual field quality must reject it"


def test_problem_anneals_target_admission_thresholds_to_final_targets() -> None:
    targets = _targets(max_harmonic_units=10.0, min_margin_percent=15.0, max_current_a=13000.0)
    problem = DipoleOptimizationProblem(
        _topology(),
        targets,
        _feasibility(),
        total_generations=10,
    )

    early_harmonic, early_margin, early_current = problem.admission_thresholds(generation=1)
    late_harmonic, late_margin, late_current = problem.admission_thresholds(generation=10)

    assert early_harmonic is not None
    assert early_margin is not None
    assert early_current is not None
    assert early_harmonic > targets.max_harmonic_units
    assert early_margin < targets.min_margin_percent
    assert early_current > targets.max_current_a
    assert late_harmonic == targets.max_harmonic_units
    assert late_margin == targets.min_margin_percent
    assert late_current == targets.max_current_a


def test_problem_admission_schedule_none_preserves_linear_anneal_exactly() -> None:
    # Locks the default (admission_schedule=None) fallback's exact values --
    # protects against a staged-schedule port accidentally changing the
    # default behavior every existing campaign/test relies on.
    targets = _targets(max_harmonic_units=10.0, min_margin_percent=15.0, max_current_a=13000.0)
    problem = DipoleOptimizationProblem(_topology(), targets, _feasibility(), total_generations=10)

    harmonic, margin, current = problem.admission_thresholds(generation=5)

    progress = 5 / 10
    expected_harmonic = 100.0 + progress * (10.0 - 100.0)
    expected_margin = -5.0 + progress * (15.0 - -5.0)
    expected_current = 26000.0 + progress * (13000.0 - 26000.0)
    assert harmonic == expected_harmonic
    assert margin == expected_margin
    assert current == expected_current


def test_problem_staged_schedule_holds_constant_within_a_stage_then_steps() -> None:
    # The actual behavioral difference from the linear anneal: within a
    # stage's fraction range the threshold must not move at all, and must
    # jump discontinuously the generation progress crosses a boundary -- a
    # naive port could wrongly interpolate instead of stepping.
    schedule = AdmissionSchedule(
        stages=(
            AdmissionStage(end_fraction=0.5, harmonic_multiplier=4.0, margin_relaxation_percent=10.0, current_multiplier=2.0),
            AdmissionStage(end_fraction=1.0, harmonic_multiplier=1.0, margin_relaxation_percent=0.0, current_multiplier=1.0),
        )
    )
    targets = _targets(
        max_harmonic_units=5.0,
        min_margin_percent=25.0,
        max_current_a=10000.0,
        admission_schedule=schedule,
    )
    problem = DipoleOptimizationProblem(_topology(), targets, _feasibility(), total_generations=10)

    # generations 1..5 all fall within the first stage (progress <= 0.5).
    thresholds_by_generation = [problem.admission_thresholds(generation=g) for g in (1, 3, 5)]
    assert len(set(thresholds_by_generation)) == 1, "threshold must be constant within a stage"
    first_stage_harmonic, first_stage_margin, first_stage_current = thresholds_by_generation[0]
    assert first_stage_harmonic == 20.0
    assert first_stage_margin == 15.0
    assert first_stage_current == 20000.0

    # generation 6 (progress=0.6) crosses into the second stage.
    second_stage_harmonic, second_stage_margin, second_stage_current = problem.admission_thresholds(generation=6)
    assert second_stage_harmonic == 5.0
    assert second_stage_margin == 25.0
    assert second_stage_current == 10000.0
    assert second_stage_harmonic != first_stage_harmonic
    assert second_stage_margin != first_stage_margin
    assert second_stage_current != first_stage_current


def test_refresh_population_admission_reflects_staged_threshold_step() -> None:
    # Mirrors test_runner.py's task-0042 stale-G regression test, but with a
    # staged schedule: a candidate admitted as feasible during an early
    # plateau must be correctly re-flagged infeasible the generation a
    # later stage steps the threshold down -- proving staged thresholds
    # compose correctly with refresh_population_admission.
    from pymoo.core.population import Population

    from dot.optimize.runner import refresh_population_admission

    topology = _topology()
    schedule = AdmissionSchedule(
        stages=(
            AdmissionStage(end_fraction=0.5, harmonic_multiplier=100.0, margin_relaxation_percent=0.0, current_multiplier=1.0),
            AdmissionStage(end_fraction=1.0, harmonic_multiplier=1.0, margin_relaxation_percent=0.0, current_multiplier=1.0),
        )
    )
    baseline_problem = DipoleOptimizationProblem(topology, _targets(), _feasibility())
    feasible_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])
    raw_field_quality = float(baseline_problem.evaluate(feasible_genome, return_values_of=["F"])[0])
    assert raw_field_quality > 0.0

    total_generations = 10
    targets_with_harmonic = _targets(max_harmonic_units=raw_field_quality / 2.0, admission_schedule=schedule)
    problem = DipoleOptimizationProblem(topology, targets_with_harmonic, _feasibility(), total_generations=total_generations)

    problem.set_generation(1)
    f1, g1 = problem.evaluate(feasible_genome, return_values_of=["F", "G"])
    assert np.all(np.atleast_1d(g1) <= 0.0)

    pop = Population.new(X=np.atleast_2d(feasible_genome))
    pop.set("F", np.atleast_2d(f1))
    pop.set("G", np.atleast_2d(g1))

    problem.set_generation(total_generations)
    refresh_population_admission(problem, pop)

    assert np.any(pop.get("G") > 0.0)


def test_problem_marks_operating_current_above_cap_as_graded_constraint_violation() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_current_a=180.0),
        _feasibility(),
        total_generations=10,
    )
    barely_over_cap_genome = np.asarray([12.0, 10.0, 2.0, 45.0, 2.0, 1.0, 0.0])
    badly_over_cap_genome = np.asarray([12.0, 10.0, 1.0, 50.0, 1.0, 1.0, 70.0])
    problem.set_generation(10)

    barely_over_f, barely_over_g = problem.evaluate(barely_over_cap_genome, return_values_of=["F", "G"])
    badly_over_f, badly_over_g = problem.evaluate(badly_over_cap_genome, return_values_of=["F", "G"])

    assert problem.n_ieq_constr == 2
    assert barely_over_g[0] <= 0.0
    assert badly_over_g[0] <= 0.0
    assert barely_over_g[1] > 0.0
    assert badly_over_g[1] > barely_over_g[1]
    assert barely_over_f[0] < 1.0e12
    assert badly_over_f[0] < 1.0e12


def test_problem_computes_objectives_for_current_above_final_cap_within_annealed_threshold() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_current_a=180.0),
        _feasibility(),
        total_generations=10,
    )
    over_final_cap_genome = np.asarray([12.0, 10.0, 1.0, 40.0, 2.0, 1.0, 30.0])
    problem.set_generation(1)

    f_values, g_values = problem.evaluate(over_final_cap_genome, return_values_of=["F", "G"])

    assert g_values[0] <= 0.0
    assert g_values[1] <= 0.0
    assert f_values[0] < 1.0e12
    assert f_values[1] < 0.0


def test_problem_accepts_feasible_genome_with_unsupported_layer_excluded() -> None:
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="unsupported",
                n_blocks=1,
                inner_radius_bounds_mm=(20.0, 20.5),
                phi_bounds_deg=(10.0, 20.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
            LayerTopology(
                cable_id="supported",
                n_blocks=1,
                inner_radius_bounds_mm=(24.0, 24.5),
                phi_bounds_deg=(40.0, 50.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
        ),
        cables={"unsupported": cable, "supported": cable},
    )
    targets = OptimizationTargets(
        target_bore_field_t=0.02,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(None, conductor_data()),
        temperature_k=0.0,
    )
    problem = DipoleOptimizationProblem(topology, targets, _feasibility())
    feasible_genome = np.asarray([20.0, 12.0, 1.0, 24.0, 45.0, 1.0])

    f_values, g_values = problem.evaluate(feasible_genome, return_values_of=["F", "G"])

    assert g_values[0] <= 0.0
    assert f_values[0] < 1.0e12
    assert f_values[1] < 0.0


def test_problem_reports_graded_turn_budget_constraints() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_total_turns=2, max_turns_per_layer=2),
        _feasibility(),
    )
    barely_over_budget = np.asarray([12.0, 10.0, 1.0, 45.0, 2.0, 1.0, 0.0])
    badly_over_budget = np.asarray([12.0, 10.0, 2.0, 45.0, 2.0, 1.0, 0.0])

    barely_f, barely_g = problem.evaluate(barely_over_budget, return_values_of=["F", "G"])
    badly_f, badly_g = problem.evaluate(badly_over_budget, return_values_of=["F", "G"])

    assert problem.n_ieq_constr == 3
    assert barely_g[0] <= 0.0
    assert badly_g[0] <= 0.0
    assert barely_g[1] == 1.0
    assert badly_g[1] == 2.0
    assert barely_g[2] == 1.0
    assert badly_g[2] == 2.0
    assert barely_f[0] >= 1.0e12
    assert badly_f[0] >= 1.0e12

    # Verification that inactive block slot's turns are not counted towards budgets
    inactive_but_high_turns = np.asarray([12.0, 10.0, 1.0, 45.0, 2.0, 0.0, 0.0])
    inactive_f, inactive_g = problem.evaluate(inactive_but_high_turns, return_values_of=["F", "G"])
    assert inactive_g[1] == 0.0
    assert inactive_g[2] == 0.0
    assert inactive_f[0] < 1.0e12


def test_problem_computes_objectives_for_designs_within_turn_budgets() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_total_turns=3, max_turns_per_layer=3),
        _feasibility(),
    )
    within_budget = np.asarray([12.0, 10.0, 1.0, 45.0, 2.0, 1.0, 0.0])

    f_values, g_values = problem.evaluate(within_budget, return_values_of=["F", "G"])

    assert np.all(g_values <= 0.0)
    assert f_values[0] < 1.0e12
    assert f_values[1] < 0.0


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
    max_current_a: float | None = None,
    max_harmonic_units: float | None = None,
    min_margin_percent: float | None = None,
    max_total_turns: int | None = None,
    max_turns_per_layer: int | None = None,
    admission_schedule: AdmissionSchedule | None = None,
) -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.02,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=0.0,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
        max_current_a=max_current_a,
        max_total_turns=max_total_turns,
        max_turns_per_layer=max_turns_per_layer,
        admission_schedule=admission_schedule,
    )


def _feasibility() -> FeasibilitySettings:
    # max_angle_deg=90 is a no-op for the (corrected, minimum-from-pole)
    # pole_angle_limit check -- these tests exercise other constraints
    # (turn budget, current cap), not pole-angle specifically.
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
