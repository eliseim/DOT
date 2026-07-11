from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from pymoo.core.population import Population

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.geometry.constraints import check_feasibility
from dot.optimize import (
    LayerConductorData,
    LayerTopology,
    Topology,
    decode,
    field_quality_objective,
    genome_bounds,
    load_line_margin_objective,
)
from dot.optimize.problem import DipoleOptimizationProblem, FeasibilitySettings, MarginEvaluationExclusion, OptimizationTargets
from dot.optimize.runner import (
    ConstructiveMixedVariableSampling,
    GroundTruthRepair,
    PhiOrderingRepair,
    TurnBudgetRepair,
    _mixed_variable_nsga2,
    _minimum_phi_gap_deg,
    refresh_population_admission,
    run_campaign,
)


def test_run_campaign_returns_feasible_candidates_with_consistent_objectives() -> None:
    topology = _topology()
    targets = _targets()
    result = run_campaign(
        topology,
        targets,
        _feasibility(),
        pop_size=8,
        n_gen=3,
        seed=7,
    )

    assert result.candidates
    for candidate in result.candidates:
        layer = candidate.design.layers[0]
        assert layer.blocks[0].alpha_deg == 0.0
        assert all(-10.0 <= block.alpha_deg <= 20.0 for block in layer.blocks[1:])
    candidate = result.candidates[0]
    field_quality = field_quality_objective(
        candidate.design,
        targets.r_ref_mm,
        targets.max_order,
    )
    margin = load_line_margin_objective(
        candidate.design,
        cable_specs_by_layer=(candidate.design.layers[0].blocks[0].cable,),
        cadata_by_layer=targets.cadata_by_layer,
        temperature_k=targets.temperature_k,
    )

    assert candidate.objectives[0] == pytest.approx(field_quality, rel=1.0e-12)
    assert candidate.objectives[1] == pytest.approx(-margin, rel=1.0e-12)


def test_refresh_population_admission_rescoring_reflects_current_threshold() -> None:
    # admission_thresholds() anneals the harmonic threshold from a loose
    # start (10x the final target) down to the final target as generations
    # progress. An individual accepted as feasible under the loose,
    # early-generation threshold must be correctly re-flagged infeasible
    # once refresh_population_admission() re-scores it against a later,
    # stricter generation's threshold -- otherwise it survives NSGA2's
    # elitist selection forever on stale G (task 0042).
    topology = _topology()
    baseline = run_campaign(topology, _targets(), _feasibility(), pop_size=8, n_gen=3, seed=11)
    assert baseline.candidates
    genome = baseline.candidates[0].genome
    raw_field_quality = baseline.candidates[0].objectives[0]
    assert raw_field_quality > 0.0

    total_generations = 10
    target = raw_field_quality / 2.0
    targets_with_harmonic = replace(_targets(), max_harmonic_units=target)
    problem = DipoleOptimizationProblem(
        topology, targets_with_harmonic, _feasibility(), total_generations=total_generations
    )

    problem.set_generation(1)
    f1, g1 = problem.evaluate(genome, return_values_of=["F", "G"])
    assert np.all(np.atleast_1d(g1) <= 0.0)

    pop = Population.new(X=np.atleast_2d(genome))
    pop.set("F", np.atleast_2d(f1))
    pop.set("G", np.atleast_2d(g1))

    problem.set_generation(total_generations)
    refresh_population_admission(problem, pop)

    assert np.any(pop.get("G") > 0.0)


def test_run_campaign_excludes_unsupported_layers_from_margin_result() -> None:
    topology = _four_layer_topology()
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(None, None, conductor_data(), conductor_data()),
        temperature_k=0.0,
        excluded_margin_layers=(
            MarginEvaluationExclusion(layer_index=0, reason="unsupported REMFIT type 3 for 'NB3SNMP'"),
            MarginEvaluationExclusion(layer_index=1, reason="unsupported REMFIT type 3 for 'NB3SNMP'"),
        ),
    )

    result = run_campaign(
        topology,
        targets,
        _feasibility(),
        pop_size=8,
        n_gen=2,
        seed=7,
    )

    assert result.candidates
    assert [(item.layer_index, item.reason) for item in result.excluded_margin_layers] == [
        (0, "unsupported REMFIT type 3 for 'NB3SNMP'"),
        (1, "unsupported REMFIT type 3 for 'NB3SNMP'"),
    ]


def test_constructive_sampling_improves_initial_feasible_fraction() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=4,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": cable},
    )
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    lower, upper = genome_bounds(topology)
    rng = np.random.default_rng(13)
    random_genomes = rng.uniform(lower, upper, size=(200, topology.n_var))
    problem = _problem_for(topology, feasibility)
    constructive = ConstructiveMixedVariableSampling(topology, feasibility).do(
        problem,
        200,
        random_state=np.random.default_rng(13),
    )
    constructive_genomes = np.asarray(
        [candidate.X if not isinstance(candidate.X, dict) else _flatten(candidate.X, topology) for candidate in constructive],
        dtype=float,
    )

    random_feasible = _feasible_count(topology, feasibility, random_genomes)
    constructive_feasible = _feasible_count(topology, feasibility, constructive_genomes)

    # Block 0 now gets the window nearest phi_upper (midplane) instead of
    # phi_lower (pole); same random draws land in different windows, so the
    # exact random_feasible count differs from before that fix.
    assert random_feasible == 182
    assert constructive_feasible == 200
    assert constructive_feasible > random_feasible


def test_mixed_variable_sampling_and_mating_keep_turn_genes_integer() -> None:
    topology = _integer_topology()
    feasibility = _feasibility()
    problem = _problem_for(topology, feasibility)
    algorithm = _mixed_variable_nsga2(topology, feasibility, pop_size=8)
    sampled = algorithm.initialization.sampling.do(
        problem,
        8,
        random_state=np.random.default_rng(3),
    )
    turn_names = [
        name for name, variable in problem.vars.items() if variable.__class__.__name__ == "Integer"
    ]
    for candidate in sampled:
        assert all(float(candidate.X[name]).is_integer() for name in turn_names)

    parent_x = [candidate.X for candidate in sampled]
    for index, genome in enumerate(parent_x):
        genome = dict(genome)
        for name in turn_names:
            genome[name] = 1 if index % 2 == 0 else 5
        parent_x[index] = genome
    parents = Population.new(X=parent_x)
    offspring = algorithm.mating.do(
        problem,
        parents,
        12,
        random_state=np.random.default_rng(5),
    )

    assert any(
        any(float(child.X[name]) not in {1.0, 5.0} for name in turn_names)
        for child in offspring
    )
    for child in offspring:
        assert all(float(child.X[name]).is_integer() for name in turn_names)


def test_phi_ordering_repair_restores_block_order_and_gap() -> None:
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 74.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 55.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 32.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": True,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 8.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": True,
        "layer_0_block_3_alpha_deg": 0.0,
    }

    repaired = PhiOrderingRepair(topology, feasibility)._do(None, np.asarray([sample], dtype=object))[0]
    phis = [float(repaired[f"layer_0_block_{index}_phi_deg"]) for index in range(4)]
    min_gap = _minimum_phi_gap_deg(
        20.0,
        topology.cables["inner"].insulated_width_inner_mm,
        feasibility.min_gap_mm,
    )

    # Block 0 gets the window nearest phi_upper (midplane, where its
    # hard-fixed alpha=0 is valid); increasing block index moves toward
    # phi_lower (the pole).
    assert phis == sorted(phis, reverse=True)
    assert all(left - right >= min_gap - 1.0e-12 for left, right in zip(phis, phis[1:], strict=False))
    assert all(
        topology.layers[0].phi_bounds_deg[0] <= phi <= topology.layers[0].phi_bounds_deg[1]
        for phi in phis
    )


def test_ground_truth_repair_shrinks_pole_ward_block_to_real_feasibility() -> None:
    cable = CableSpec(width_inner_mm=1.53, width_outer_mm=1.658, height_mm=18.363, insulation_radial_mm=0.145, insulation_azimuthal_mm=0.145)
    topology = Topology(
        aperture_radius_mm=25.0,
        layers=(
            LayerTopology(
                cable_id="c",
                n_blocks=2,
                inner_radius_bounds_mm=(30.0, 30.0),
                phi_bounds_deg=(12.0, 78.0),
                n_turns_bounds=(1, 15),
                alpha_bounds_deg=(-88.0, 10.0),
            ),
        ),
        cables={"c": cable},
    )
    feasibility = FeasibilitySettings(min_gap_mm=0.15, max_angle_deg=80.0, min_pole_gap_mm=1.5)
    # block1 gets genome_bounds()'s pole-side window; anchored at its own
    # lower bound (12deg) with a "correctly aligned" alpha and 8 turns --
    # confirmed (this session's diagnosis) to violate pole_angle_limit
    # (required minimum 90-80=10deg from the pole) despite the anchor
    # phi itself clearing that floor.
    sample = {
        "layer_0_inner_radius_mm": 30.0,
        "layer_0_block_0_phi_deg": 70.0,
        "layer_0_block_0_n_turns": 10,
        "layer_0_block_1_phi_deg": 12.0,
        "layer_0_block_1_n_turns": 8,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 12.0 - 90.0,
    }

    repaired = GroundTruthRepair(topology, feasibility)._do(None, np.asarray([sample], dtype=object))[0]

    from dot.optimize.genome import flatten_mixed_genome

    genome = flatten_mixed_genome(repaired, topology)
    unit_design = decode(genome, topology, topology.cables)
    result = check_feasibility(
        unit_design,
        aperture_radius_mm=topology.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        max_angle_deg=feasibility.max_angle_deg,
        min_pole_gap_mm=feasibility.min_pole_gap_mm,
    )
    assert result.is_feasible, "\n".join(v.message for v in result.violations)
    # Repaired by shrinking the offending (pole-ward) block, not the safe one.
    assert repaired["layer_0_block_1_n_turns"] < 8
    assert repaired["layer_0_block_0_n_turns"] == 10


def test_turn_budget_repair_reduces_largest_active_turn_counts_first() -> None:
    topology = _turn_budget_topology()
    targets = _targets(max_total_turns=7, max_turns_per_layer=4)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 10.0,
        "layer_0_block_0_n_turns": 5,
        "layer_0_block_1_phi_deg": 30.0,
        "layer_0_block_1_n_turns": 4,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_1_inner_radius_mm": 24.0,
        "layer_1_block_0_phi_deg": 20.0,
        "layer_1_block_0_n_turns": 4,
        "layer_1_block_1_phi_deg": 40.0,
        "layer_1_block_1_n_turns": 5,
        "layer_1_block_1_active": False,
        "layer_1_block_1_alpha_deg": 0.0,
    }

    repaired = TurnBudgetRepair(topology, targets)._do(None, np.asarray([sample], dtype=object))[0]

    assert repaired["layer_0_block_0_n_turns"] == 1
    assert repaired["layer_0_block_1_n_turns"] == 3
    assert repaired["layer_1_block_0_n_turns"] == 3
    assert repaired["layer_1_block_1_n_turns"] == 5
    assert _active_turn_total(repaired, topology) == 7
    assert _active_layer_turn_totals(repaired, topology) == [4, 3]


def test_turn_budget_repair_respects_lower_bounds_when_budget_is_impossible() -> None:
    topology = _turn_budget_topology(n_turns_bounds=(2, 5))
    targets = _targets(max_total_turns=3, max_turns_per_layer=3)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 10.0,
        "layer_0_block_0_n_turns": 5,
        "layer_0_block_1_phi_deg": 30.0,
        "layer_0_block_1_n_turns": 5,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_1_inner_radius_mm": 24.0,
        "layer_1_block_0_phi_deg": 20.0,
        "layer_1_block_0_n_turns": 5,
        "layer_1_block_1_phi_deg": 40.0,
        "layer_1_block_1_n_turns": 5,
        "layer_1_block_1_active": False,
        "layer_1_block_1_alpha_deg": 0.0,
    }

    repaired = TurnBudgetRepair(topology, targets)._do(None, np.asarray([sample], dtype=object))[0]

    assert repaired["layer_0_block_0_n_turns"] == 2
    assert repaired["layer_0_block_1_n_turns"] == 2
    assert repaired["layer_1_block_0_n_turns"] == 2
    assert repaired["layer_1_block_1_n_turns"] == 5
    assert _active_turn_total(repaired, topology) == 6


def _topology() -> Topology:
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 22.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(-10.0, 20.0),
            ),
        ),
        cables={"inner": cable},
    )


def _four_layer_topology() -> Topology:
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    layers = tuple(
        LayerTopology(
            cable_id=f"layer-{index}",
            n_blocks=1,
            inner_radius_bounds_mm=(20.0 + index * 4.0, 20.5 + index * 4.0),
            phi_bounds_deg=(10.0 + index * 15.0, 15.0 + index * 15.0),
            n_turns_bounds=(1, 1),
            alpha_bounds_deg=(-10.0, 70.0),
        )
        for index in range(4)
    )
    return Topology(
        aperture_radius_mm=8.0,
        layers=layers,
        cables={f"layer-{index}": cable for index in range(4)},
    )


def _integer_topology() -> Topology:
    cable = CableSpec(width_mm=0.2, height_mm=0.2, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 22.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 20.0),
            ),
        ),
        cables={"inner": cable},
    )


def _tight_four_block_topology() -> Topology:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=4,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": cable},
    )


def _turn_budget_topology(n_turns_bounds: tuple[int, int] = (1, 5)) -> Topology:
    cable = CableSpec(width_mm=0.2, height_mm=0.2, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(10.0, 50.0),
                n_turns_bounds=n_turns_bounds,
                alpha_bounds_deg=(0.0, 0.0),
            ),
            LayerTopology(
                cable_id="outer",
                n_blocks=2,
                inner_radius_bounds_mm=(24.0, 24.0),
                phi_bounds_deg=(20.0, 60.0),
                n_turns_bounds=n_turns_bounds,
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": cable, "outer": cable},
    )


def _targets(
    *,
    max_total_turns: int | None = None,
    max_turns_per_layer: int | None = None,
) -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=0.0,
        max_total_turns=max_total_turns,
        max_turns_per_layer=max_turns_per_layer,
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=80.0)


def _problem_for(topology: Topology, feasibility: FeasibilitySettings):
    from dot.optimize.problem import DipoleOptimizationProblem

    cadata_by_layer = tuple(conductor_data() for _ in topology.layers)
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=cadata_by_layer,
        temperature_k=0.0,
    )
    return DipoleOptimizationProblem(topology, targets, feasibility)


def _flatten(genome: dict[str, float | int], topology: Topology) -> np.ndarray:
    from dot.optimize.genome import flatten_mixed_genome

    return flatten_mixed_genome(genome, topology)


def _feasible_count(
    topology: Topology,
    feasibility: FeasibilitySettings,
    genomes: np.ndarray,
) -> int:
    feasible = 0
    for genome in genomes:
        result = check_feasibility(
            decode(genome, topology, topology.cables),
            aperture_radius_mm=topology.aperture_radius_mm,
            min_gap_mm=feasibility.min_gap_mm,
            max_angle_deg=feasibility.max_angle_deg,
        )
        feasible += int(result.is_feasible)
    return feasible


def _active_turn_total(sample: dict[str, float | int], topology: Topology) -> int:
    return sum(_active_layer_turn_totals(sample, topology))


def _active_layer_turn_totals(sample: dict[str, float | int], topology: Topology) -> list[int]:
    totals: list[int] = []
    for layer_index, layer in enumerate(topology.layers):
        total = 0
        for block_index in range(layer.n_blocks):
            if block_index > 0 and not sample[f"layer_{layer_index}_block_{block_index}_active"]:
                continue
            total += int(sample[f"layer_{layer_index}_block_{block_index}_n_turns"])
        totals.append(total)
    return totals


def conductor_data() -> LayerConductorData:
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    remfit = Type1FitCoefficients(
        c1=10.0 * 5000.0 / (3.141592653589793 * 1.0**2 / 4.0 * 1.0e-6),
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=10.0,
    )
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)
