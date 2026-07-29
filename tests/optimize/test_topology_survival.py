from __future__ import annotations

import numpy as np
from pymoo.core.population import Population
from pymoo.operators.survival.rank_and_crowding.classes import RankAndCrowding

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import run_campaign
from dot.optimize.topology_survival import (
    TopologyAwareRankAndCrowding,
    TopologySurvivalConfig,
    topology_family,
)


def test_topology_family_reflects_active_block_count_per_layer() -> None:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)

    def block() -> Block:
        return Block(phi_deg=45.0, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=10.0, current_a=1.0)

    two_one = DipoleDesign(
        aperture_radius_mm=5.0,
        layers=(
            Layer(inner_radius_mm=10.0, blocks=(block(), block())),
            Layer(inner_radius_mm=15.0, blocks=(block(),)),
        ),
    )
    one_two = DipoleDesign(
        aperture_radius_mm=5.0,
        layers=(
            Layer(inner_radius_mm=10.0, blocks=(block(),)),
            Layer(inner_radius_mm=15.0, blocks=(block(), block())),
        ),
    )

    assert topology_family(two_one) == "blocks:2,1"
    assert topology_family(one_two) == "blocks:1,2"
    assert topology_family(two_one) != topology_family(one_two)


def test_plain_rank_and_crowding_drops_the_minority_family() -> None:
    # Baseline failure mode this phase fixes: a strictly-dominated minority
    # family individual is dropped entirely by plain rank-and-crowding once
    # the majority family alone already fills n_survive.
    pop = _synthetic_population()

    survivors = RankAndCrowding()._do(None, pop, n_survive=3, random_state=np.random.RandomState(0))

    assert "b" not in {ind.get("topology_family") for ind in survivors}


def test_topology_aware_survival_preserves_the_minority_family() -> None:
    pop = _synthetic_population()

    survivors = TopologyAwareRankAndCrowding(TopologySurvivalConfig(enabled=True, min_families=2))._do(
        None, pop, n_survive=3, random_state=np.random.RandomState(0)
    )

    assert "b" in {ind.get("topology_family") for ind in survivors}
    assert len(survivors) == 3


def test_topology_aware_survival_disabled_by_default_matches_plain_rank_and_crowding() -> None:
    pop = _synthetic_population()

    survivors = TopologyAwareRankAndCrowding(TopologySurvivalConfig())._do(
        None, pop, n_survive=3, random_state=np.random.RandomState(0)
    )

    assert "b" not in {ind.get("topology_family") for ind in survivors}


def test_topology_aware_survival_preserves_families_when_every_candidate_is_infeasible() -> None:
    families = np.array(["a", "a", "a", "b", "c", "d"], dtype=object)
    pop = Population.new(X=np.arange(6, dtype=float)[:, None])
    pop.set("F", np.column_stack((np.arange(6.0), np.arange(6.0))))
    pop.set("G", np.asarray([[0.01], [0.02], [0.03], [0.5], [0.6], [0.7]]))
    pop.set("topology_family", families)
    survival = TopologyAwareRankAndCrowding(
        TopologySurvivalConfig(
            enabled=True,
            min_families=4,
            max_survivors_per_family=1,
        )
    )

    survivors = survival.do(
        _ConstrainedProblem(),
        pop,
        n_survive=4,
        random_state=np.random.RandomState(0),
    )

    assert {row.get("topology_family") for row in survivors} == {"a", "b", "c", "d"}
    assert all(float(row.CV[0]) > 0.0 for row in survivors)


def test_topology_aware_survival_never_sacrifices_feasible_for_family_quota() -> None:
    pop = Population.new(X=np.arange(4, dtype=float)[:, None])
    pop.set("F", np.asarray([[1.0, 2.0], [2.0, 1.0], [0.0, 0.0], [0.0, 0.0]]))
    pop.set("G", np.asarray([[0.0], [0.0], [0.01], [0.02]]))
    pop.set("topology_family", np.array(["a", "a", "b", "c"], dtype=object))
    survival = TopologyAwareRankAndCrowding(
        TopologySurvivalConfig(enabled=True, min_families=3)
    )

    survivors = survival.do(
        _ConstrainedProblem(),
        pop,
        n_survive=2,
        random_state=np.random.RandomState(0),
    )

    assert [float(row.CV[0]) for row in survivors] == [0.0, 0.0]


def test_run_campaign_with_topology_survival_keeps_more_than_one_family() -> None:
    topology = _optional_block_topology()
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=1.9,
    )

    result = run_campaign(
        topology,
        targets,
        _feasibility(),
        pop_size=16,
        n_gen=3,
        seed=5,
    )

    assert result.candidates


class _ConstrainedProblem:
    @staticmethod
    def has_constraints() -> bool:
        return True


def _optional_block_topology() -> Topology:
    # 4 optional block slots in one layer so active-block-count varies
    # across the population, giving topology_family() real diversity to
    # preserve.
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=4,
                inner_radius_bounds_mm=(20.0, 20.0),
                phi_bounds_deg=(10.0, 80.0),
                n_turns_bounds=(1, 1),
                alpha_bounds_deg=(-10.0, 20.0),
            ),
        ),
        cables={"inner": cable},
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=90.0)


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


def _synthetic_population() -> Population:
    f_values = np.array(
        [
            [1.0, 5.0],
            [2.0, 4.0],
            [3.0, 3.0],
            [4.0, 2.0],
            [5.0, 1.0],
            [10.0, 10.0],
        ]
    )
    families = np.array(["a", "a", "a", "a", "a", "b"], dtype=object)
    pop = Population.new(X=f_values.copy())
    pop.set("F", f_values)
    pop.set("topology_family", families)
    return pop
