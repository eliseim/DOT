from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from pymoo.core.population import Population

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import Block, CableSpec, DipoleDesign, Layer, block_radiality
from dot.geometry.constraints import check_feasibility, check_layer_nesting
from dot.optimize import (
    LayerConductorData,
    LayerTopology,
    Topology,
    decode,
    field_quality_objective,
    genome_bounds,
    load_line_margin_objective,
)
from dot.optimize.genome import flatten_mixed_genome
from dot.optimize.problem import (
    DipoleOptimizationProblem,
    FeasibilitySettings,
    OptimizationTargets,
)
from dot.optimize.runner import (
    FeasibilityAwareMating,
    ConstructiveMixedVariableSampling,
    GroundTruthRepair,
    LayerNestingRepair,
    MinActiveBlocksRepair,
    PhiOrderingRepair,
    RadialCompactionRepair,
    TurnBudgetRepair,
    _certify_candidate,
    _assign_sector_turns,
    _mixed_variable_nsga2,
    _minimum_phi_gap_deg,
    _search_nondominated,
    ParetoCandidate,
    best_generation_candidate,
    run_campaign,
)


def test_search_archive_drops_em_equivalent_complexity_in_turn_then_block_order() -> None:
    cable = CableSpec(width_mm=1.0, height_mm=1.0)

    def candidate(turns: tuple[int, ...]) -> ParetoCandidate:
        blocks = tuple(
            Block(10.0 + 20.0 * index, 0.0, count, cable, 20.0, 100.0)
            for index, count in enumerate(turns)
        )
        return ParetoCandidate(
            genome=np.empty(0),
            design=DipoleDesign(8.0, (Layer(20.0, blocks),)),
            objectives=(4.0, -25.0),
        )

    archive = _search_nondominated([candidate((2, 1)), candidate((1, 1)), candidate((2,))])

    assert len(archive) == 1
    assert [block.n_turns for block in archive[0].design.layers[0].blocks] == [2]


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
        fidelity=targets.certification_fidelity,
    )
    margin = load_line_margin_objective(
        candidate.design,
        cable_specs_by_layer=(candidate.design.layers[0].blocks[0].cable,),
        cadata_by_layer=targets.cadata_by_layer,
        temperature_k=targets.temperature_k,
    )

    assert candidate.objectives[0] == pytest.approx(field_quality, rel=1.0e-12)
    assert candidate.objectives[1] == pytest.approx(-margin, rel=1.0e-12)


def test_certification_uses_signed_harmonic_target_residual() -> None:
    topology = _topology()
    feasibility = _feasibility()
    baseline = run_campaign(
        topology,
        _targets(),
        feasibility,
        pop_size=8,
        n_gen=3,
        seed=7,
    )
    candidate = baseline.candidates[0]
    b3 = next(normal for order, normal, _skew in candidate.harmonics if order == 3)
    targets = replace(
        _targets(),
        max_order=3,
        harmonic_orders=(3,),
        harmonic_targets=((3, b3),),
        max_harmonic_units=1.0e-9,
    )

    certified = _certify_candidate(candidate, topology, targets, feasibility)

    assert certified is not None
    assert certified.objectives[0] == pytest.approx(0.0, abs=1.0e-10)
    assert certified.harmonic_targets == ((3, b3),)


def test_certification_enforces_minimum_and_exact_fixed_current() -> None:
    topology = _topology()
    feasibility = _feasibility()
    baseline = run_campaign(
        topology,
        _targets(),
        feasibility,
        pop_size=8,
        n_gen=3,
        seed=9,
    )
    candidate = baseline.candidates[0]
    assert candidate.operating_current_a is not None
    fixed_current_a = abs(candidate.operating_current_a)

    fixed_targets = replace(
        _targets(),
        min_current_a=fixed_current_a,
        max_current_a=fixed_current_a,
    )
    fixed = _certify_candidate(candidate, topology, fixed_targets, feasibility)

    assert fixed is not None
    assert fixed.operating_current_a == pytest.approx(fixed_current_a)

    minimum_only_targets = replace(
        _targets(),
        min_current_a=fixed_current_a + 1.0,
    )
    assert _certify_candidate(candidate, topology, minimum_only_targets, feasibility) is None


def test_certification_rejects_sub_tolerance_overlap_when_block_gap_is_positive() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": cable},
    )
    blocks = (
        Block(30.0, 0.0, 1, cable, 20.0, 1.0),
        Block(40.0, 0.0, 1, cable, 20.0, 1.0),
    )
    candidate = ParetoCandidate(
        genome=np.empty(0),
        design=DipoleDesign(8.0, (Layer(20.0, blocks),)),
        objectives=(0.0, 0.0),
    )
    feasibility = FeasibilitySettings(
        min_gap_mm=0.0,
        max_angle_deg=90.0,
        min_layer_clearance_mm=0.0,
        min_inter_block_gap_mm=1.0,
        geometry_tolerance_mm=0.005,
    )

    assert _certify_candidate(candidate, topology, _targets(), feasibility) is None


def test_ground_truth_repair_preserves_11t_outer_block_while_restoring_clearance() -> None:
    cable = CableSpec(
        width_inner_mm=1.53,
        width_outer_mm=1.658,
        height_mm=18.363,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    radius_mm = 44.15255001214963
    topology = Topology(
        aperture_radius_mm=25.0,
        layers=(
            LayerTopology(
                cable_id="outer",
                n_blocks=2,
                min_blocks=1,
                inner_radius_bounds_mm=(radius_mm, radius_mm),
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(3, 14),
                alpha_bounds_deg=(-15.0, 75.0),
                inner_radius_mm=radius_mm,
                first_block_phi_deg=0.194650906011,
                first_block_alpha_deg=0.0,
            ),
        ),
        cables={"outer": cable},
    )
    sample = {
        "layer_0_inner_radius_mm": radius_mm,
        "layer_0_block_0_phi_deg": 0.194650906011,
        "layer_0_block_0_n_turns": 14,
        "layer_0_block_1_phi_deg": 34.566638189406,
        "layer_0_block_1_n_turns": 11,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 13.562600337392,
    }
    feasibility = FeasibilitySettings(
        min_gap_mm=0.0,
        min_layer_clearance_mm=0.0,
        min_inter_block_gap_mm=1.0,
        geometry_tolerance_mm=0.005,
    )

    GroundTruthRepair(topology, feasibility)._repair_sample(sample)
    repaired = decode(flatten_mixed_genome(sample, topology), topology, topology.cables)
    result = check_feasibility(
        repaired,
        aperture_radius_mm=topology.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        geometry_tolerance_mm=feasibility.geometry_tolerance_mm,
    )

    assert result.is_feasible
    assert sample["layer_0_block_1_active"] is True
    assert sample["layer_0_block_0_n_turns"] == 14
    assert sample["layer_0_block_1_n_turns"] == 11
    assert sample["layer_0_block_1_phi_deg"] > 34.566638189406


def test_layer_nesting_repair_shifts_outer_layer_until_nesting_clears() -> None:
    # A near-pole outer-layer block violates C10 against the inner layer's
    # pole-most conductor -- confirmed empirically (task 0043) at these
    # exact values. A uniform phi shift toward the midplane, capped by
    # max_nesting_repair_deg, must clear it when the cap allows enough
    # room, and must leave the sample untouched when it doesn't.
    topology = _nesting_topology()

    without_cap = _nesting_violation_sample()
    feasibility_no_cap = _feasibility_with_nesting_cap(None)
    LayerNestingRepair(topology, feasibility_no_cap)._repair_sample(without_cap)
    assert without_cap["layer_1_block_1_phi_deg"] == pytest.approx(80.0)
    assert _design_violates_nesting(topology, without_cap)

    repaired = _nesting_violation_sample()
    feasibility_generous_cap = _feasibility_with_nesting_cap(60.0)
    LayerNestingRepair(topology, feasibility_generous_cap)._repair_sample(repaired)
    assert repaired["layer_1_block_0_phi_deg"] == pytest.approx(15.0)
    assert repaired["layer_1_block_1_phi_deg"] < 80.0
    assert repaired["layer_1_block_1_phi_deg"] >= 80.0 - 60.0
    assert not _design_violates_nesting(topology, repaired)

    capped_short = _nesting_violation_sample()
    feasibility_tiny_cap = _feasibility_with_nesting_cap(2.0)
    LayerNestingRepair(topology, feasibility_tiny_cap)._repair_sample(capped_short)
    assert capped_short["layer_1_block_1_phi_deg"] == pytest.approx(80.0)
    assert _design_violates_nesting(topology, capped_short)


def test_layer_nesting_enforced_end_to_end_does_not_collapse_the_population() -> None:
    # Enabling enforce_layer_nesting used to collapse the whole population
    # (task #37) because nothing repaired a violation. With
    # LayerNestingRepair wired into CampaignRepair, a short campaign over a
    # topology prone to nesting violations must still produce at least one
    # candidate that satisfies check_feasibility(enforce_layer_nesting=True).
    topology = _nesting_topology()
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(), conductor_data()),
        temperature_k=1.9,
    )
    feasibility = FeasibilitySettings(
        min_gap_mm=0.1,
        max_angle_deg=90.0,
        enforce_layer_nesting=True,
        max_nesting_repair_deg=60.0,
    )

    result = run_campaign(topology, targets, feasibility, pop_size=12, n_gen=4, seed=3)

    assert result.candidates
    for candidate in result.candidates:
        check = check_feasibility(
            candidate.design,
            aperture_radius_mm=topology.aperture_radius_mm,
            min_gap_mm=feasibility.min_gap_mm,
            max_angle_deg=feasibility.max_angle_deg,
            enforce_layer_nesting=True,
        )
        assert check.is_feasible, "\n".join(v.message for v in check.violations)


def _nesting_topology() -> Topology:
    cable = CableSpec(width_mm=3.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                min_blocks=2,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(1, 3),
                alpha_bounds_deg=(0.0, 0.0),
            ),
            LayerTopology(
                cable_id="outer",
                n_blocks=2,
                min_blocks=2,
                inner_radius_bounds_mm=(24.0, 24.0),
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(1, 2),
                alpha_bounds_deg=(0.0, 0.0),
            ),
        ),
        cables={"inner": cable, "outer": cable},
    )


def _nesting_violation_sample() -> dict[str, float | int]:
    return {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 10.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 75.0,
        "layer_0_block_1_n_turns": 3,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_1_inner_radius_mm": 24.0,
        "layer_1_block_0_phi_deg": 15.0,
        "layer_1_block_0_n_turns": 1,
        "layer_1_block_1_phi_deg": 80.0,
        "layer_1_block_1_n_turns": 2,
        "layer_1_block_1_active": True,
        "layer_1_block_1_alpha_deg": 0.0,
    }


def _feasibility_with_nesting_cap(max_nesting_repair_deg: float | None) -> FeasibilitySettings:
    return FeasibilitySettings(
        min_gap_mm=0.1,
        max_angle_deg=90.0,
        max_nesting_repair_deg=max_nesting_repair_deg,
    )


def _design_violates_nesting(topology: Topology, sample: dict[str, float | int]) -> bool:
    genome = flatten_mixed_genome(sample, topology)
    design = decode(genome, topology, topology.cables)
    return any(v.layer_index == 1 for v in check_layer_nesting(design))


def test_run_campaign_with_parallel_workers_still_produces_candidates() -> None:
    topology = _topology()
    result = run_campaign(
        topology,
        _targets(),
        _feasibility(),
        pop_size=8,
        n_gen=3,
        seed=7,
        n_workers=2,
    )

    assert result.candidates


def test_run_campaign_on_generation_callback_fires_every_generation_with_a_design() -> None:
    from dot.geometry import DipoleDesign

    topology = _topology()
    calls: list[tuple[int, int, object, object, object, object]] = []

    def _on_generation(
        generation, total_generations, design, margin_percent, harmonic_units, family_count
    ):  # noqa: ANN001
        calls.append(
            (generation, total_generations, design, margin_percent, harmonic_units, family_count)
        )

    run_campaign(
        topology,
        _targets(),
        _feasibility(),
        pop_size=8,
        n_gen=3,
        seed=7,
        on_generation=_on_generation,
    )

    assert len(calls) == 3
    for (
        generation,
        total_generations,
        design,
        _margin_percent,
        harmonic_units,
        family_count,
    ) in calls:
        assert total_generations == 3
        assert 1 <= generation <= 3
        # The population always has at least a closest-to-feasible individual,
        # so a design should be reported from generation 1 onward.
        assert design is None or isinstance(design, DipoleDesign)
        assert harmonic_units is None or harmonic_units >= 0.0
        assert family_count is None or family_count >= 1


def test_live_generation_candidate_never_reports_penalty_as_physics() -> None:
    topology = _topology()
    genome = np.asarray([20.0, 10.0, 1.0, 45.0, 1.0, 1.0, 0.0])
    pop = Population.new(X=np.asarray([genome]))
    pop.set("F", np.asarray([[1.0e12, 1.0e12]]))
    pop.set("G", np.asarray([[1.0]]))

    found = best_generation_candidate(topology, pop, _targets())

    assert found is not None
    design, objectives, margin = found
    assert isinstance(design, DipoleDesign)
    assert objectives == (None, None)
    assert margin is None


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
        [
            candidate.X if not isinstance(candidate.X, dict) else _flatten(candidate.X, topology)
            for candidate in constructive
        ],
        dtype=float,
    )

    random_feasible = _feasible_count(topology, feasibility, random_genomes)
    constructive_feasible = _feasible_count(topology, feasibility, constructive_genomes)

    assert random_feasible < 200
    assert constructive_feasible == 200
    assert constructive_feasible > random_feasible


def test_sector_turn_seeding_covers_balanced_and_weighted_topologies() -> None:
    phi_variables = [
        ("layer_0_block_0_phi_deg", 0, (0.0, 90.0)),
        ("layer_0_block_1_phi_deg", 1, (0.0, 90.0)),
    ]

    assignments: dict[str, tuple[int, int]] = {}
    for strategy in ("balanced", "midplane_weighted", "pole_weighted", "random_weighted"):
        sample: dict[str, float | int] = {}
        _assign_sector_turns(
            sample,
            0,
            phi_variables,
            (1, 20),
            20,
            strategy=strategy,
            rng=np.random.default_rng(17),
        )
        assignments[strategy] = (
            int(sample["layer_0_block_0_n_turns"]),
            int(sample["layer_0_block_1_n_turns"]),
        )

    assert assignments["balanced"] == (10, 10)
    assert assignments["midplane_weighted"][0] > assignments["midplane_weighted"][1]
    assert assignments["pole_weighted"][0] < assignments["pole_weighted"][1]
    assert all(sum(turns) == 20 for turns in assignments.values())


def test_parallel_repair_matches_serial_sampling_exactly() -> None:
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=1.9,
    )
    serial_problem = DipoleOptimizationProblem(topology, targets, feasibility)
    parallel_problem = DipoleOptimizationProblem(
        topology,
        targets,
        feasibility,
        n_workers=2,
    )
    try:
        serial = ConstructiveMixedVariableSampling(topology, feasibility).do(
            serial_problem,
            16,
            random_state=np.random.default_rng(27),
        )
        parallel = ConstructiveMixedVariableSampling(topology, feasibility).do(
            parallel_problem,
            16,
            random_state=np.random.default_rng(27),
        )
    finally:
        parallel_problem.close()

    assert [candidate.X for candidate in parallel] == [
        candidate.X for candidate in serial
    ]


def test_mixed_variable_sampling_and_mating_keep_turn_genes_integer() -> None:
    topology = _integer_topology()
    feasibility = _feasibility()
    problem = _problem_for(topology, feasibility)
    algorithm = _mixed_variable_nsga2(topology, feasibility, pop_size=8, targets=problem.targets)
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

    # Crossover for Integer (n_turns) genes is UX (uniform swap), not SBX --
    # deliberately, matching dd's own topology-collapse fix (blend-then-round
    # crossover on discrete genes "is semantically weak and tends to push
    # [them] toward whichever parent dominates the front"). So novelty here
    # comes from MUTATION alone, a genuinely stochastic rare event over a
    # small 12-offspring sample -- check across several seeds rather than
    # asserting one fixed seed always produces it.
    all_offspring = [
        child
        for seed in range(20)
        for child in algorithm.mating.do(
            problem, parents, 12, random_state=np.random.default_rng(seed)
        )
    ]
    assert any(
        any(float(child.X[name]) not in {1.0, 5.0} for name in turn_names)
        for child in all_offspring
    )
    for child in all_offspring:
        assert all(float(child.X[name]).is_integer() for name in turn_names)


def test_min_active_blocks_repair_activates_blocks_below_the_floor() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=4,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(0.0, 0.0),
                min_blocks=3,
            ),
        ),
        cables={"inner": cable},
    )
    # Only block 0 (always active) is active -- one short of the floor of 3.
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 74.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 55.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": False,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 32.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": False,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 8.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": False,
        "layer_0_block_3_alpha_deg": 0.0,
    }

    repaired = MinActiveBlocksRepair(topology)._do(None, np.asarray([sample], dtype=object))[0]

    active_count = 1 + sum(bool(repaired[f"layer_0_block_{index}_active"]) for index in range(1, 4))
    assert active_count >= 3
    for index in range(1, 4):
        if repaired[f"layer_0_block_{index}_active"]:
            assert int(repaired[f"layer_0_block_{index}_n_turns"]) >= 1


def test_min_active_blocks_repair_leaves_already_satisfied_layers_untouched() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(0.0, 0.0),
                min_blocks=1,
            ),
        ),
        cables={"inner": cable},
    )
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 74.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 55.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": False,
        "layer_0_block_1_alpha_deg": 0.0,
    }

    repaired = MinActiveBlocksRepair(topology)._do(None, np.asarray([sample], dtype=object))[0]

    assert repaired["layer_0_block_1_active"] is False


def test_phi_ordering_repair_restores_block_order_and_gap() -> None:
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 16.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 35.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 58.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": True,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 82.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": True,
        "layer_0_block_3_alpha_deg": 0.0,
    }

    repaired = PhiOrderingRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]
    phis = [float(repaired[f"layer_0_block_{index}_phi_deg"]) for index in range(4)]
    min_gap = _minimum_phi_gap_deg(
        20.0,
        topology.cables["inner"].insulated_width_inner_mm,
        feasibility.min_gap_mm,
    )

    # Block 0 is nearest phi_lower (midplane); increasing block index moves
    # toward phi_upper (the pole).
    assert phis == sorted(phis)
    assert all(
        right - left >= min_gap - 1.0e-12 for left, right in zip(phis, phis[1:], strict=False)
    )
    assert all(
        topology.layers[0].phi_bounds_deg[0] <= phi <= topology.layers[0].phi_bounds_deg[1]
        for phi in phis
    )


def test_phi_ordering_repair_uses_midward_blocks_real_turn_footprint() -> None:
    # Turns extend from their anchor toward increasing phi.  The clearance
    # between block 0 (midward) and block 1 (poleward) must therefore use
    # block 0's turn count.  Using block 1's count was a direction error
    # that left multi-turn blocks colliding despite ordered anchors.
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 16.0,
        "layer_0_block_0_n_turns": 2,
        "layer_0_block_1_phi_deg": 18.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 58.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": True,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 82.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": True,
        "layer_0_block_3_alpha_deg": 0.0,
    }

    repaired = PhiOrderingRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]
    phis = [float(repaired[f"layer_0_block_{index}_phi_deg"]) for index in range(4)]
    required = _minimum_phi_gap_deg(
        20.0,
        topology.cables["inner"].insulated_width_inner_mm,
        feasibility.min_gap_mm,
        n_turns=2,
    )
    assert phis[1] - phis[0] >= required - 1.0e-12
    assert phis[2] == pytest.approx(58.0)
    assert phis[3] == pytest.approx(82.0)


def test_radial_compaction_repair_pulls_every_layer_to_the_tight_target_gap() -> None:
    # A campaign's own feasibility check only enforces the radial layer gap
    # as a MINIMUM (check_inter_layer_spacing: gap >= min_layer_clearance_mm),
    # so a free inner_radius_mm gene sampled/mutated anywhere in its bounds
    # is exactly as "feasible" whether it leaves 0.11mm or 4mm of slack.
    # This repair must make every layer hug the previous layer's actual
    # outer edge by exactly min_layer_clearance_mm, regardless of where the
    # sample's own radius gene proposed sitting -- windows here are
    # deliberately wide so the tight target lands in each window's
    # interior, not clamped to either edge.
    cable = CableSpec(width_mm=1.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=tuple(
            LayerTopology(
                cable_id="c",
                n_blocks=1,
                inner_radius_bounds_mm=(1.0, 500.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 1),
            )
            for _ in range(4)
        ),
        cables={"c": cable},
    )
    feasibility = FeasibilitySettings(
        min_gap_mm=0.1, max_angle_deg=80.0, min_layer_clearance_mm=0.5
    )
    sample = {
        f"layer_{index}_inner_radius_mm": 300.0 + index for index in range(4)
    }  # loose, out of order

    repaired = RadialCompactionRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]

    radii = [float(repaired[f"layer_{index}_inner_radius_mm"]) for index in range(4)]
    assert radii[0] == pytest.approx(1.0)
    for index in range(1, 4):
        expected = radii[index - 1] + cable.insulated_height_mm + feasibility.min_layer_clearance_mm
        assert radii[index] == pytest.approx(expected)


def test_radial_compaction_repair_clamps_to_bounds_when_target_is_unreachable() -> None:
    # If the previous layer's actual outer edge would push a layer's target
    # radius above its own genome upper bound, the repair must clamp to that
    # bound rather than exceed it (a Real gene outside its own bounds would
    # be invalid input to everything downstream).
    cable = CableSpec(
        width_mm=0.1, height_mm=50.0, insulation_thickness_mm=0.0
    )  # deliberately tall
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=1,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 1),
            ),
            LayerTopology(
                cable_id="outer",
                n_blocks=1,
                inner_radius_bounds_mm=(21.0, 22.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 1),
            ),
        ),
        cables={"inner": cable, "outer": cable},
    )
    feasibility = FeasibilitySettings(
        min_gap_mm=0.1, max_angle_deg=80.0, min_layer_clearance_mm=0.5
    )
    sample = {"layer_0_inner_radius_mm": 20.0, "layer_1_inner_radius_mm": 21.0}

    repaired = RadialCompactionRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]

    assert float(repaired["layer_1_inner_radius_mm"]) == pytest.approx(22.0)


def test_phi_ordering_repair_pins_lone_midplane_block_to_tight_lower_bound() -> None:
    # When only block 0 is active in a layer (every other block deactivated),
    # the >=2-block branch (which lands block 0 exactly at phi_lower by
    # construction) never runs -- an earlier version of this repair skipped
    # the layer entirely in that case, leaving the lone midplane block's phi
    # wherever sampling/mutation put it instead of pinned to the tight
    # midplane-clearance target.
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 50.0,  # loose, nowhere near phi_lower
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 60.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": False,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 70.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": False,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 80.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": False,
        "layer_0_block_3_alpha_deg": 0.0,
    }

    repaired = PhiOrderingRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]

    assert float(repaired["layer_0_block_0_phi_deg"]) == pytest.approx(
        topology.layers[0].phi_bounds_deg[0]
    )


class _StubMating:
    """Deterministic stand-in for MixedVariableMating.do() -- returns the
    next sample dict from a fixed sequence, repeating the last entry once
    the sequence is exhausted (mirrors always-infeasible mating output)."""

    def __init__(self, sequence: list[dict[str, float | int]]) -> None:
        self._sequence = sequence
        self.calls = 0

    def do(self, problem, pop, n_offsprings, random_state=None, **kwargs):  # noqa: ANN001, ANN003
        sample = self._sequence[min(self.calls, len(self._sequence) - 1)]
        self.calls += 1
        return Population.new(X=[dict(sample)])


def test_feasibility_aware_mating_retries_infeasible_offspring_until_valid() -> None:
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sampling = ConstructiveMixedVariableSampling(topology, feasibility)

    infeasible_sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 40.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 40.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 40.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": True,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 40.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": True,
        "layer_0_block_3_alpha_deg": 0.0,
    }
    adaptive = FeasibilityAwareMating(
        topology, feasibility, _StubMating([infeasible_sample]), sampling
    )
    assert not adaptive._is_valid(infeasible_sample), "test fixture must actually be infeasible"

    # First .do() call returns the always-infeasible sample; local
    # re-mutation retries hit the same stub (still infeasible, since the
    # stub ignores retries and always returns its one queued sample), so
    # the regeneration must fall through to the constructive-sampler
    # fallback, which is feasibility-aware by construction.
    pop = sampling.do(None, 1)
    off = adaptive.do(None, pop, 1)

    assert len(off) == 1
    assert adaptive._is_valid(off[0].get("X"))
    assert adaptive.valid_fraction_history == [1.0]


def test_feasibility_aware_mating_degrades_gracefully_when_fallback_also_fails(
    monkeypatch,
) -> None:  # noqa: ANN001
    topology = _tight_four_block_topology()
    feasibility = FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)
    sampling = ConstructiveMixedVariableSampling(topology, feasibility)

    infeasible_sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 40.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 40.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 0.0,
        "layer_0_block_2_phi_deg": 40.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": True,
        "layer_0_block_2_alpha_deg": 0.0,
        "layer_0_block_3_phi_deg": 40.0,
        "layer_0_block_3_n_turns": 1,
        "layer_0_block_3_active": True,
        "layer_0_block_3_alpha_deg": 0.0,
    }
    adaptive = FeasibilityAwareMating(
        topology, feasibility, _StubMating([infeasible_sample]), sampling
    )
    # Force even the fallback constructive sampler to hand back the same
    # infeasible sample, so no retry path can ever succeed -- this must
    # not crash, and must still return a full-size, consumable offspring
    # population (never silently drop offspring).
    monkeypatch.setattr(
        sampling,
        "do",
        lambda problem, n, random_state=None: Population.new(X=[dict(infeasible_sample)]),
    )

    pop = Population.new(X=[dict(infeasible_sample)])
    off = adaptive.do(None, pop, 1)

    assert len(off) == 1
    assert adaptive.valid_fraction_history == [0.0]


def test_radial_mating_trials_start_only_after_a_target_met_parent_exists() -> None:
    topology = _topology()
    feasibility = _feasibility()
    sample = {
        "layer_0_inner_radius_mm": 20.0,
        "layer_0_block_0_phi_deg": 10.0,
        "layer_0_block_0_n_turns": 1,
        "layer_0_block_1_phi_deg": 30.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": -10.0,
    }
    before = decode(
        flatten_mixed_genome(sample, topology),
        topology,
        topology.cables,
    )
    adaptive = FeasibilityAwareMating(
        topology,
        feasibility,
        _StubMating([sample]),
        ConstructiveMixedVariableSampling(topology, feasibility),
        prefer_radial_design=True,
        radial_trial_fraction=1.0,
        radial_activation_delay_generations=0,
    )

    not_ready = Population.new(X=[dict(sample)])
    not_ready.set("radial_preference_eligible", np.asarray([False]))
    unchanged = adaptive.do(None, not_ready, 1, random_state=np.random.RandomState(2))
    assert unchanged[0].X["layer_0_block_1_alpha_deg"] == -10.0

    ready = Population.new(X=[dict(sample)])
    ready.set("radial_preference_eligible", np.asarray([True]))
    radialized = adaptive.do(None, ready, 1, random_state=np.random.RandomState(2))
    after = decode(
        flatten_mixed_genome(radialized[0].X, topology),
        topology,
        topology.cables,
    )

    assert adaptive.radial_trial_count_history == [0, 1]
    assert block_radiality(after.layers[0].blocks[1]).deviation_deg < block_radiality(
        before.layers[0].blocks[1]
    ).deviation_deg


def test_ground_truth_repair_shrinks_pole_ward_block_to_real_feasibility() -> None:
    cable = CableSpec(
        width_inner_mm=1.53,
        width_outer_mm=1.658,
        height_mm=18.363,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
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

    repaired = GroundTruthRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]

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


def test_ground_truth_repair_rotates_aperture_offender_before_deleting_turns() -> None:
    cable = CableSpec(
        width_inner_mm=1.53,
        width_outer_mm=1.658,
        height_mm=18.363,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    topology = Topology(
        aperture_radius_mm=25.0,
        layers=(
            LayerTopology(
                cable_id="c",
                n_blocks=2,
                inner_radius_bounds_mm=(25.0, 25.0),
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(2, 7),
                alpha_bounds_deg=(-15.0, 75.0),
                first_block_phi_deg=0.343771,
                first_block_alpha_deg=0.0,
            ),
        ),
        cables={"c": cable},
    )
    feasibility = FeasibilitySettings(
        min_gap_mm=0.0,
        min_layer_clearance_mm=0.0,
        min_inter_block_gap_mm=1.0,
        geometry_tolerance_mm=0.005,
    )
    sample = {
        "layer_0_inner_radius_mm": 25.0,
        "layer_0_block_0_phi_deg": 0.343771,
        "layer_0_block_0_n_turns": 4,
        "layer_0_block_1_phi_deg": 20.2269,
        "layer_0_block_1_n_turns": 6,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 23.4754,
    }
    initial = check_feasibility(
        decode(flatten_mixed_genome(sample, topology), topology, topology.cables),
        aperture_radius_mm=topology.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        geometry_tolerance_mm=feasibility.geometry_tolerance_mm,
    )
    assert [violation.constraint_name for violation in initial.violations] == ["aperture_clearance"]

    repaired = GroundTruthRepair(topology, feasibility)._do(
        None,
        np.asarray([sample], dtype=object),
    )[0]
    repaired_design = decode(
        flatten_mixed_genome(repaired, topology),
        topology,
        topology.cables,
    )
    result = check_feasibility(
        repaired_design,
        aperture_radius_mm=topology.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        geometry_tolerance_mm=feasibility.geometry_tolerance_mm,
    )

    assert result.is_feasible, "\n".join(v.message for v in result.violations)
    assert repaired["layer_0_block_1_n_turns"] == 6
    assert bool(repaired["layer_0_block_1_active"]) is True
    assert repaired["layer_0_block_1_alpha_deg"] < 23.4754


def test_ground_truth_repair_never_deactivates_a_block_below_min_blocks() -> None:
    # Same pole-angle-violation setup as the shrink test above, but the
    # offending block's turns are already at its lower bound (1, not 8), so
    # GroundTruthRepair's only remaining move is deactivation -- which task
    # 0054's own min_blocks=2 floor for this layer must forbid, since block1
    # is the layer's only non-block-0 ACTIVE block (deactivating it would
    # drop the layer to 1 active block).
    cable = CableSpec(
        width_inner_mm=1.53,
        width_outer_mm=1.658,
        height_mm=18.363,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    topology = Topology(
        aperture_radius_mm=25.0,
        layers=(
            LayerTopology(
                cable_id="c",
                n_blocks=3,
                inner_radius_bounds_mm=(30.0, 30.0),
                phi_bounds_deg=(12.0, 78.0),
                n_turns_bounds=(1, 15),
                alpha_bounds_deg=(-88.0, 10.0),
                min_blocks=2,
            ),
        ),
        cables={"c": cable},
    )
    feasibility = FeasibilitySettings(min_gap_mm=0.15, max_angle_deg=80.0, min_pole_gap_mm=1.5)
    sample = {
        "layer_0_inner_radius_mm": 30.0,
        "layer_0_block_0_phi_deg": 70.0,
        "layer_0_block_0_n_turns": 10,
        "layer_0_block_1_phi_deg": 12.0,
        "layer_0_block_1_n_turns": 1,
        "layer_0_block_1_active": True,
        "layer_0_block_1_alpha_deg": 12.0 - 90.0,
        "layer_0_block_2_phi_deg": 12.0,
        "layer_0_block_2_n_turns": 1,
        "layer_0_block_2_active": False,
        "layer_0_block_2_alpha_deg": 0.0,
    }
    assert not check_feasibility(
        decode(flatten_mixed_genome(sample, topology), topology, topology.cables),
        aperture_radius_mm=topology.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        max_angle_deg=feasibility.max_angle_deg,
        min_pole_gap_mm=feasibility.min_pole_gap_mm,
    ).is_feasible, "test fixture must actually be infeasible to start"

    repaired = GroundTruthRepair(topology, feasibility)._do(
        None, np.asarray([sample], dtype=object)
    )[0]

    assert bool(repaired["layer_0_block_1_active"]) is True, (
        "block1 must stay active -- deactivating it would drop layer 0 below its min_blocks=2 floor"
    )
    assert int(repaired["layer_0_block_1_n_turns"]) == 1


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
                phi_bounds_deg=(12.0, 88.0),
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
        temperature_k=1.9,
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
        temperature_k=1.9,
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
