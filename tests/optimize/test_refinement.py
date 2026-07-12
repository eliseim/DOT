from __future__ import annotations

import numpy as np

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize.objectives import LayerConductorData
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.refinement import RefinementConfig, run_refinement, select_refinement_seeds
from dot.optimize.runner import ParetoCandidate


def test_refinement_only_perturbs_phi_and_alpha_topology_and_turns_stay_frozen() -> None:
    seed = _near_feasible_seed()
    targets = _targets()
    feasibility = _feasibility()
    config = RefinementConfig(
        enabled=True, population=6, generations=2, angular_mutation_probability=1.0, angular_mutation_sigma_deg=1.0
    )

    result = run_refinement(targets, feasibility, (seed,), config, random_state=np.random.default_rng(1))

    assert result.candidates
    for candidate in result.candidates:
        assert len(candidate.design.layers) == len(seed.design.layers)
        for layer, seed_layer in zip(candidate.design.layers, seed.design.layers, strict=True):
            assert layer.inner_radius_mm == seed_layer.inner_radius_mm
            assert len(layer.blocks) == len(seed_layer.blocks)
            for block, seed_block in zip(layer.blocks, seed_layer.blocks, strict=True):
                assert block.n_turns == seed_block.n_turns
                assert block.cable == seed_block.cable
                assert block.inner_radius_mm == seed_block.inner_radius_mm
                # current_a is NOT frozen -- it's a physics-solved operating
                # condition (operating_point() re-solves it for whatever
                # field the perturbed geometry produces), not a topology
                # parameter. Only phi/alpha are perturbed genes; turns,
                # cable, and radius are the frozen topology; current is a
                # downstream consequence of all of those, checked above.


def test_refinement_converts_a_near_feasible_seed_into_a_fully_feasible_candidate() -> None:
    # This is the mechanism's whole point: a seed failing check_feasibility
    # by a small margin (0.07mm inter_block_gap severity, confirmed via a
    # scan of the boundary) must be nudged, via bounded random phi/alpha
    # perturbation of its active blocks, into at least one fully feasible
    # descendant -- closing exactly the kind of small residual violation
    # that's kept CTH-14T candidates near, but not at, feasible this
    # session.
    seed = _near_feasible_seed()
    targets = _targets()
    feasibility = _feasibility()
    assert not check_feasibility(
        seed.design,
        aperture_radius_mm=seed.design.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        max_angle_deg=feasibility.max_angle_deg,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
    ).is_feasible, "test fixture must actually be infeasible to start"

    config = RefinementConfig(
        enabled=True, population=8, generations=3, angular_mutation_probability=1.0, angular_mutation_sigma_deg=1.0
    )
    result = run_refinement(targets, feasibility, (seed,), config, random_state=np.random.default_rng(0))

    feasible_candidates = [
        candidate
        for candidate in result.candidates
        if check_feasibility(
            candidate.design,
            aperture_radius_mm=candidate.design.aperture_radius_mm,
            min_gap_mm=feasibility.min_gap_mm,
            max_angle_deg=feasibility.max_angle_deg,
            min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        ).is_feasible
    ]
    assert feasible_candidates


def test_select_refinement_seeds_respects_max_seeds_and_per_topology_cap() -> None:
    seed = _near_feasible_seed()
    candidates = tuple(
        ParetoCandidate(genome=np.empty(0), design=seed.design, objectives=(float(index), -10.0 - index))
        for index in range(6)
    )
    config = RefinementConfig(max_seeds=3, max_seeds_per_topology=2)

    seeds = select_refinement_seeds(candidates, config)

    assert len(seeds) <= config.max_seeds


def _near_feasible_seed() -> ParetoCandidate:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
    block0 = Block(phi_deg=60.0, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=20.0, current_a=100.0)
    # 53.5deg sits just past the C7 inter-block-gap boundary (52-53deg is
    # feasible, 54deg+ is clearly infeasible -- confirmed via a direct
    # boundary scan), giving a small, nudge-able violation.
    block1 = Block(phi_deg=53.5, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=20.0, current_a=100.0)
    design = DipoleDesign(aperture_radius_mm=8.0, layers=(Layer(inner_radius_mm=20.0, blocks=(block0, block1)),))
    return ParetoCandidate(genome=np.empty(0), design=design, objectives=(1.0, -10.0))


def _targets() -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=0.0,
    )


def test_mixed_turn_refinement_lets_margin_move_unlike_angle_only() -> None:
    # task 0049: campaign9 (a real, full-scale run) proved angle-only
    # refinement can slash harmonic content but never moves load-line
    # margin at all -- every refined candidate landed in the seed's
    # narrow margin band, since turns/current (which govern margin) were
    # frozen. Mixed-turn refinement unfreezes turns; this must produce a
    # visibly WIDER margin spread than angle-only refinement on the same
    # seed, and must actually vary total turn count.
    seed = _turn_growable_seed()
    targets = _targets()
    feasibility = _feasibility()

    angle_only_config = RefinementConfig(
        enabled=True, population=10, generations=3,
        angular_mutation_probability=0.5, angular_mutation_sigma_deg=1.0,
        mixed_turn_enabled=False,
    )
    angle_only = run_refinement(targets, feasibility, (seed,), angle_only_config, random_state=np.random.default_rng(0))
    angle_only_margins = [-c.objectives[1] for c in angle_only.candidates]
    assert angle_only_margins

    mixed_config = RefinementConfig(
        enabled=True, population=10, generations=3,
        angular_mutation_probability=0.5, angular_mutation_sigma_deg=1.0,
        mixed_turn_enabled=True, turn_mutation_probability=0.6, turn_step=1,
        preserve_layer_total_probability=0.0, max_total_turns=10,
    )
    mixed = run_refinement(targets, feasibility, (seed,), mixed_config, random_state=np.random.default_rng(0))
    mixed_margins = [-c.objectives[1] for c in mixed.candidates]
    mixed_turns = {sum(b.n_turns for l in c.design.layers for b in l.blocks) for c in mixed.candidates}
    assert mixed_margins

    assert (max(mixed_margins) - min(mixed_margins)) > 5.0 * (max(angle_only_margins) - min(angle_only_margins)), (
        "mixed-turn refinement should spread margin far more than angle-only refinement on the same seed"
    )
    assert len(mixed_turns) > 1, "total turn count should actually vary across mixed-turn candidates"


def test_mixed_turn_refinement_respects_max_total_turns_budget() -> None:
    seed = _turn_growable_seed()
    targets = _targets()
    feasibility = _feasibility()
    config = RefinementConfig(
        enabled=True, population=10, generations=4,
        angular_mutation_probability=0.0,
        mixed_turn_enabled=True, turn_mutation_probability=0.9, turn_step=1,
        preserve_layer_total_probability=0.0, max_total_turns=6,
    )

    result = run_refinement(targets, feasibility, (seed,), config, random_state=np.random.default_rng(2))

    assert result.candidates
    for candidate in result.candidates:
        total_turns = sum(b.n_turns for l in candidate.design.layers for b in l.blocks)
        assert total_turns <= 6


def test_mixed_turn_refinement_keeps_active_block_pattern_and_radius_frozen() -> None:
    seed = _turn_growable_seed()
    targets = _targets()
    feasibility = _feasibility()
    config = RefinementConfig(
        enabled=True, population=10, generations=3,
        angular_mutation_probability=0.5, angular_mutation_sigma_deg=1.0,
        mixed_turn_enabled=True, turn_mutation_probability=0.6, turn_step=1,
        preserve_layer_total_probability=0.0, max_total_turns=10,
    )

    result = run_refinement(targets, feasibility, (seed,), config, random_state=np.random.default_rng(0))

    assert result.candidates
    for candidate in result.candidates:
        assert len(candidate.design.layers) == len(seed.design.layers)
        for layer, seed_layer in zip(candidate.design.layers, seed.design.layers, strict=True):
            assert layer.inner_radius_mm == seed_layer.inner_radius_mm
            assert len(layer.blocks) == len(seed_layer.blocks)
            for block, seed_block in zip(layer.blocks, seed_layer.blocks, strict=True):
                assert block.cable == seed_block.cable
                assert block.inner_radius_mm == seed_block.inner_radius_mm


def _turn_growable_seed() -> ParetoCandidate:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
    block0 = Block(phi_deg=70.0, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=20.0, current_a=100.0)
    block1 = Block(phi_deg=40.0, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=20.0, current_a=100.0)
    design = DipoleDesign(aperture_radius_mm=8.0, layers=(Layer(inner_radius_mm=20.0, blocks=(block0, block1)),))
    return ParetoCandidate(genome=np.empty(0), design=design, objectives=(1.0, -10.0))


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0, min_inter_block_gap_mm=1.0)


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
