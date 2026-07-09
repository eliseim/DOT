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
                        alpha_deg=0.0,
                        n_turns=3,
                        cable=cable,
                        inner_radius_mm=12.0,
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
            ),
        ),
        cables={"inner": cable},
    )

    genome = encode(design)
    decoded = decode(genome, topology, topology.cables)

    assert genome.tolist() == [12.0, 12.0, 2.0, 38.0, 3.0]
    assert decoded.layers[0].inner_radius_mm == pytest.approx(12.0)
    assert [block.phi_deg for block in decoded.layers[0].blocks] == [12.0, 38.0]
    assert [block.n_turns for block in decoded.layers[0].blocks] == [2, 3]
    assert [block.alpha_deg for block in decoded.layers[0].blocks] == [0.0, 0.0]
    assert [block.current_a for block in decoded.layers[0].blocks] == [1.0, 1.0]


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
            ),
        ),
    )

    lower, upper = genome_bounds(topology)

    assert lower.tolist() == [10.0, 5.0, 1.0, 5.0, 1.0]
    assert upper.tolist() == [20.0, 60.0, 5.0, 60.0, 5.0]
