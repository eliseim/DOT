from __future__ import annotations

import numpy as np
import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize import LayerTopology, Topology, decode, encode, genome_bounds
from dot.optimize.genome import genome_variables, mixed_variable_spec


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

    assert topology.n_var == 18
    assert genome.shape == (topology.n_var,)
    assert genome.tolist() == [
        12.0,
        12.0,
        2.0,
        38.0,
        3.0,
        1.0,
        22.5,
        24.0,
        20.0,
        1.0,
        40.0,
        2.0,
        1.0,
        -3.5,
        55.0,
        4.0,
        1.0,
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

    decoded = decode([12.0, 12.0, 2.0, 38.0, 3.0, 1.0, 45.0], topology, topology.cables)

    assert topology.n_var == 7
    assert [block.alpha_deg for block in decoded.layers[0].blocks] == [0.0, 45.0]


def test_user_fixed_layer_anchor_is_not_changed_by_genome_values() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(12.0, 12.0),
                phi_bounds_deg=(5.0, 90.0),
                n_turns_bounds=(1, 5),
                alpha_bounds_deg=(-75.0, 15.0),
                inner_radius_mm=12.0,
                first_block_phi_deg=87.5,
                first_block_alpha_deg=-3.0,
            ),
        ),
        cables={"inner": cable},
    )

    lower, upper = genome_bounds(topology)
    assert lower[:3].tolist() == pytest.approx([12.0, 87.5, 1.0])
    assert upper[:3].tolist() == pytest.approx([12.0, 87.5, 5.0])

    decoded = decode(
        [999.0, 1.0, 4.0, 30.0, 2.0, 1.0, -20.0],
        topology,
        topology.cables,
    )
    first = decoded.layers[0].blocks[0]
    assert first.inner_radius_mm == pytest.approx(12.0)
    assert first.phi_deg == pytest.approx(87.5)
    assert first.alpha_deg == pytest.approx(-3.0)
    assert first.n_turns == 4


def test_optional_block_active_genes_control_decoded_block_count() -> None:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
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
        cables={"inner": cable},
    )

    base = [12.0, 5.0, 1.0, 25.0, 2.0, 0.0, 10.0, 45.0, 3.0, 0.0, 20.0, 65.0, 4.0, 0.0, 30.0]
    expected_phis = {
        (0.0, 0.0, 0.0): [5.0],
        (1.0, 0.0, 0.0): [5.0, 25.0],
        (1.0, 1.0, 0.0): [5.0, 25.0, 45.0],
        (1.0, 1.0, 1.0): [5.0, 25.0, 45.0, 65.0],
        (0.0, 1.0, 0.0): [5.0, 45.0],
        (0.0, 0.0, 1.0): [5.0, 65.0],
        (1.0, 0.0, 1.0): [5.0, 25.0, 65.0],
    }
    for active_values, phis in expected_phis.items():
        genome = list(base)
        genome[5], genome[9], genome[13] = active_values

        decoded = decode(genome, topology, topology.cables)

        assert [block.phi_deg for block in decoded.layers[0].blocks] == phis


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
            5.0,
                1.0,
                0.0,
                -10.0,
                22.0,
                15.0,
            1.0,
                15.0,
                1.0,
                0.0,
                -5.0,
                15.0,
                1.0,
                0.0,
                -5.0,
        ]
    )
    assert upper.tolist() == pytest.approx(
        [
            20.0,
                60.0,
            5.0,
            60.0,
                5.0,
                1.0,
                70.0,
                30.0,
                80.0,
            6.0,
                80.0,
                6.0,
                1.0,
                68.0,
                80.0,
                6.0,
                1.0,
                68.0,
        ]
    )


def test_genome_bounds_give_every_block_the_full_phi_window() -> None:
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

    phi_slots = [1, 3, 7, 11]
    assert lower[phi_slots].tolist() == pytest.approx([2.0, 2.0, 2.0, 2.0])
    assert upper[phi_slots].tolist() == pytest.approx([78.0, 78.0, 78.0, 78.0])


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


def test_optional_block_slot_does_not_change_reachable_phi_range() -> None:
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
        [20.0, 2.0, 1.0, 2.0, 1.0, 1.0, 0.0, 2.0, 1.0, 1.0, 0.0, 2.0, 1.0, 1.0, 0.0]
    )
    old_upper = np.array(
        [20.0, 78.0, 1.0, 78.0, 1.0, 1.0, 0.0, 78.0, 1.0, 1.0, 0.0, 78.0, 1.0, 1.0, 0.0]
    )
    new_lower, new_upper = genome_bounds(topology)

    phi_slots = [1, 3, 7, 11]
    assert new_lower[phi_slots].tolist() == old_lower[phi_slots].tolist()
    assert new_upper[phi_slots].tolist() == old_upper[phi_slots].tolist()


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


@pytest.mark.parametrize("phi_bounds", [(-1.0, 60.0), (5.0, 91.0)])
def test_layer_topology_rejects_phi_bounds_outside_first_quadrant(
    phi_bounds: tuple[float, float],
) -> None:
    with pytest.raises(ValueError, match="compact first quadrant"):
        LayerTopology(
            cable_id="inner",
            n_blocks=1,
            inner_radius_bounds_mm=(10.0, 20.0),
            phi_bounds_deg=phi_bounds,
            n_turns_bounds=(1, 5),
        )


def test_layer_topology_validates_min_blocks_not_greater_than_n_blocks() -> None:
    with pytest.raises(ValueError, match="min_blocks must be <= n_blocks"):
        LayerTopology(
            cable_id="inner",
            n_blocks=2,
            inner_radius_bounds_mm=(10.0, 20.0),
            phi_bounds_deg=(5.0, 60.0),
            n_turns_bounds=(1, 5),
            min_blocks=3,
        )


def test_layer_topology_min_blocks_defaults_to_one() -> None:
    layer = LayerTopology(
        cable_id="inner",
        n_blocks=4,
        inner_radius_bounds_mm=(10.0, 20.0),
        phi_bounds_deg=(5.0, 60.0),
        n_turns_bounds=(1, 5),
    )
    assert layer.min_blocks == 1


def test_genome_indexing_and_bounds_consistency() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    topology = Topology(
        aperture_radius_mm=10.0,
        layers=(
            LayerTopology(
                cable_id="c1",
                n_blocks=1,
                inner_radius_bounds_mm=(12.0, 15.0),
                phi_bounds_deg=(5.0, 60.0),
                n_turns_bounds=(1, 5),
            ),
            LayerTopology(
                cable_id="c2",
                n_blocks=3,
                inner_radius_bounds_mm=(18.0, 22.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 4),
            ),
            LayerTopology(
                cable_id="c3",
                n_blocks=2,
                inner_radius_bounds_mm=(25.0, 30.0),
                phi_bounds_deg=(15.0, 80.0),
                n_turns_bounds=(2, 6),
            ),
        ),
        cables={"c1": cable, "c2": cable, "c3": cable},
    )

    assert topology.n_var == 21

    lower, upper = genome_bounds(topology)
    assert lower.shape == (21,)
    assert upper.shape == (21,)

    variables = genome_variables(topology)
    assert len(variables) == 21

    for i, var in enumerate(variables):
        assert var.index == i
        assert var.bounds == (lower[i], upper[i])

    spec = mixed_variable_spec(topology)
    assert len(spec) == 21
    for var in variables:
        assert var.name in spec

    design = DipoleDesign(
        aperture_radius_mm=10.0,
        layers=(
            Layer(
                inner_radius_mm=13.0,
                blocks=(
                    Block(phi_deg=12.0, alpha_deg=0.0, n_turns=2, cable=cable, inner_radius_mm=13.0, current_a=1.0),
                ),
            ),
            Layer(
                inner_radius_mm=19.0,
                blocks=(
                    Block(phi_deg=15.0, alpha_deg=0.0, n_turns=1, cable=cable, inner_radius_mm=19.0, current_a=1.0),
                    Block(phi_deg=35.0, alpha_deg=10.0, n_turns=3, cable=cable, inner_radius_mm=19.0, current_a=1.0),
                ),
            ),
            Layer(
                inner_radius_mm=26.0,
                blocks=(
                    Block(phi_deg=20.0, alpha_deg=0.0, n_turns=4, cable=cable, inner_radius_mm=26.0, current_a=1.0),
                ),
            ),
        ),
    )

    encoded = encode(design, topology)
    assert encoded.shape == (21,)

    # Layer 0 starts at 0: [13.0, 12.0, 2.0]
    # Layer 1 starts at 3: [19.0, 15.0, 1.0, 35.0, 3.0, active=1.0, alpha=10.0, phi2, turns2, active=0.0, alpha2]
    # active flag at index 3 + 1 + 2 + 4 + 2 = 12 must be 0.0.
    assert encoded[12] == 0.0
    # Layer 2 starts at 14: [26.0, 20.0, 4.0, phi1, turns1, active=0.0, alpha1]
    # active flag at index 14 + 1 + 2 + 2 = 19 must be 0.0.
    assert encoded[19] == 0.0

    decoded = decode(encoded, topology)
    assert len(decoded.layers) == 3
    assert len(decoded.layers[0].blocks) == 1
    assert len(decoded.layers[1].blocks) == 2
    assert len(decoded.layers[2].blocks) == 1

    assert decoded.layers[1].blocks[1].phi_deg == 35.0
    assert decoded.layers[1].blocks[1].alpha_deg == 10.0

