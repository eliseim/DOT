from __future__ import annotations

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
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
    assert lower.tolist() == [
        10.0,
        5.0,
        1.0,
        5.0,
        1.0,
        -10.0,
        22.0,
        15.0,
        1.0,
        15.0,
        1.0,
        -5.0,
        15.0,
        1.0,
        -5.0,
    ]
    assert upper.tolist() == [
        20.0,
        60.0,
        5.0,
        60.0,
        5.0,
        70.0,
        30.0,
        80.0,
        6.0,
        80.0,
        6.0,
        68.0,
        80.0,
        6.0,
        68.0,
    ]


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
