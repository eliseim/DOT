from __future__ import annotations

import numpy as np

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import DipoleOptimizationProblem, FeasibilitySettings, OptimizationTargets


def test_problem_marks_overlapping_turns_as_constraint_violation() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    infeasible_genome = np.asarray([12.0, 20.0, 1.0, 20.0, 1.0])

    f_values, g_values = problem.evaluate(infeasible_genome, return_values_of=["F", "G"])

    assert g_values[0] > 0.0
    assert f_values[0] >= 1.0e12


def test_problem_accepts_feasible_genome() -> None:
    problem = DipoleOptimizationProblem(_topology(), _targets(), _feasibility())
    feasible_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0])

    f_values, g_values = problem.evaluate(feasible_genome, return_values_of=["F", "G"])

    assert g_values[0] <= 0.0
    assert f_values[0] < 1.0e12
    assert f_values[1] < 0.0


def test_problem_marks_operating_current_above_cap_as_constraint_violation() -> None:
    problem = DipoleOptimizationProblem(
        _topology(),
        _targets(max_current_a=200.0),
        _feasibility(),
    )
    over_cap_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 1.0])
    under_cap_genome = np.asarray([12.0, 10.0, 1.0, 45.0, 2.0])

    over_f, over_g = problem.evaluate(over_cap_genome, return_values_of=["F", "G"])
    under_f, under_g = problem.evaluate(under_cap_genome, return_values_of=["F", "G"])

    assert over_g[0] > 0.0
    assert over_f[0] >= 1.0e12
    assert under_g[0] <= 0.0
    assert under_f[0] < 1.0e12


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
            ),
            LayerTopology(
                cable_id="supported",
                n_blocks=1,
                inner_radius_bounds_mm=(24.0, 24.5),
                phi_bounds_deg=(40.0, 50.0),
                n_turns_bounds=(1, 1),
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
            ),
        ),
        cables={"inner": cable},
    )


def _targets(*, max_current_a: float | None = None) -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.02,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=0.0,
        max_current_a=max_current_a,
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=80.0)


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
