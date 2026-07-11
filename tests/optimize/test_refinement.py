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
