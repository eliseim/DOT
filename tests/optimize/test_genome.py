from __future__ import annotations

import numpy as np
import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize import LayerTopology, Topology, decode, encode, genome_bounds


def test_encode_decode_round_trips_fixed_topology_variables() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=12.0,
                blocks=(
                    Block(
                        phi_deg=12.0,
                        alpha_deg=0.0,
                        n_turns=2,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=350.0,
                    ),
                    Block(
                        phi_deg=38.0,
                        alpha_deg=22.5,
                        n_turns=3,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=350.0,
                    ),
                ),
            ),
            Layer(
                inner_radius_mm=24.0,
                blocks=(
                    Block(
                        phi_deg=20.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=24.0,
                        current_a=350.0,
                    ),
                    Block(
                        phi_deg=40.0,
                        alpha_deg=-3.5,
                        n_turns=2,
                        cable=cable,
                        inner_radius_mm=24.0,
                        current_a=350.0,
                    ),
                    Block(
                        phi_deg=55.0,
                        alpha_deg=66.0,
                        n_turns=4,
                        cable=cable,
                        inner_radius_mm=24.0,
                        current_a=350.0,
                    ),
                ),
            ),
        ),
    )
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(10.0, 20.0),
                phi_bounds_deg=(5.0, 60.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
            LayerTopology(
                cable_id="outer",
                n_blocks=3,
                inner_radius_bounds_mm=(22.0, 30.0),
                phi_bounds_deg=(15.0, 80.0),
                n_turns_bounds=(1, 6),
                alpha_bounds_deg=(-5.0, 68.0),
            ),
        ),
        cables={"inner": cable, "outer": cable},
    )

    genome = encode(design)
    decoded = decode(genome, topology, topology.cables)

    assert topology.n_var == 15
    assert genome.shape == (topology.n_var,)
    assert genome.tolist() == [
        12.0,
        12.0,
        2.0,
        38.0,
        3.0,
        22.5,
        24.0,
        20.0,
        1.0,
        40.0,
        2.0,
        -3.5,
        55.0,
        4.0,
        66.0,
    ]
    assert decoded.layers[0].inner_radius_mm == pytest.approx(12.0)
    assert decoded.layers[1].inner_radius_mm == pytest.approx(24.0)
    assert [[block.phi_deg for block in layer.blocks] for layer in decoded.layers] == [
        [12.0, 38.0],
        [20.0, 40.0, 55.0],
    ]
    assert [[block.n_turns for block in layer.blocks] for layer in decoded.layers] == [
        [2, 3],
        [1, 2, 4],
    ]
    assert [[block.alpha_deg for block in layer.blocks] for layer in decoded.layers] == [
        [0.0, 22.5],
        [0.0, -3.5, 66.0],
    ]
    assert [[block.current_a for block in layer.blocks] for layer in decoded.layers] == [
        [1.0, 1.0],
        [1.0, 1.0, 1.0],
    ]


def test_first_block_alpha_is_not_a_genome_slot() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(10.0, 20.0),
                phi_bounds_deg=(5.0, 60.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
        ),
        cables={"inner": cable},
    )

    decoded = decode([12.0, 12.0, 2.0, 38.0, 3.0, 45.0], topology, topology.cables)

    assert topology.n_var == 6
    assert [block.alpha_deg for block in decoded.layers[0].blocks] == [0.0, 45.0]


def test_genome_bounds_match_topology_order() -> None:
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(10.0, 20.0),
                phi_bounds_deg=(5.0, 60.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
            LayerTopology(
                cable_id="outer",
                n_blocks=3,
                inner_radius_bounds_mm=(22.0, 30.0),
                phi_bounds_deg=(15.0, 80.0),
                n_turns_bounds=(1, 6),
                alpha_bounds_deg=(-5.0, 68.0),
            ),
        ),
    )

    lower, upper = genome_bounds(topology)

    assert lower.shape == (topology.n_var,)
    assert upper.shape == (topology.n_var,)
    assert lower.tolist() == pytest.approx(
        [
            10.0,
            5.0,
            1.0,
            32.5,
            1.0,
            -10.0,
            22.0,
            15.0,
            1.0,
            36.66666666666667,
            1.0,
            -5.0,
            58.333333333333336,
            1.0,
            -5.0,
        ]
    )
    assert upper.tolist() == pytest.approx(
        [
            20.0,
            32.5,
            5.0,
            60.0,
            5.0,
            70.0,
            30.0,
            36.66666666666667,
            6.0,
            58.333333333333336,
            6.0,
            68.0,
            80.0,
            6.0,
            68.0,
        ]
    )


def test_genome_bounds_partitions_four_block_phi_window() -> None:
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=4,
                inner_radius_bounds_mm=(10.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
        ),
    )

    lower, upper = genome_bounds(topology)

    phi_slots = [1, 3, 6, 9]
    assert lower[phi_slots].tolist() == pytest.approx([2.0, 21.0, 40.0, 59.0])
    assert upper[phi_slots].tolist() == pytest.approx([21.0, 40.0, 59.0, 78.0])


def test_genome_bounds_leaves_single_block_phi_bounds_unchanged() -> None:
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=1,
                inner_radius_bounds_mm=(10.0, 20.0),
                phi_bounds_deg=(2.0, 78.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-10.0, 70.0),
            ),
        ),
    )

    lower, upper = genome_bounds(topology)

    assert lower.tolist() == [10.0, 2.0, 1.0]
    assert upper.tolist() == [20.0, 78.0, 5.0]


def test_partitioned_phi_windows_materially_improve_random_feasible_fraction() -> None:
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
    old_lower = np.array(
        [20.0, 2.0, 1.0, 2.0, 1.0, 0.0, 2.0, 1.0, 0.0, 2.0, 1.0, 0.0]
    )
    old_upper = np.array(
        [20.0, 78.0, 1.0, 78.0, 1.0, 0.0, 78.0, 1.0, 0.0, 78.0, 1.0, 0.0]
    )
    new_lower, new_upper = genome_bounds(topology)

    old_feasible = _sample_feasible_count(topology, old_lower, old_upper)
    new_feasible = _sample_feasible_count(topology, new_lower, new_upper)

    assert old_feasible == 48
    assert new_feasible == 139
    assert new_feasible >= old_feasible + 50


def _sample_feasible_count(
    topology: Topology,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    n_samples: int = 200,
    seed: int = 13,
) -> int:
    rng = np.random.default_rng(seed)
    feasible_count = 0
    for _ in range(n_samples):
        genome = rng.uniform(lower, upper)
        design = decode(genome, topology, topology.cables)
        result = check_feasibility(
            design,
            aperture_radius_mm=topology.aperture_radius_mm,
            min_gap_mm=0.1,
            max_angle_deg=90.0,
        )
        feasible_count += int(result.is_feasible)
    return feasible_count


def test_layer_topology_validates_alpha_bounds_order() -> None:
    with pytest.raises(ValueError, match="alpha_bounds_deg lower must be <= upper"):
        LayerTopology(
            cable_id="inner",
            n_blocks=1,
            inner_radius_bounds_mm=(10.0, 20.0),
            phi_bounds_deg=(5.0, 60.0),
            n_turns_bounds=(1, 5),
            alpha_bounds_deg=(70.0, -10.0),
        )
