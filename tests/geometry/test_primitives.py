from __future__ import annotations

from dot.geometry import Block, CableSpec, DipoleDesign, Layer, TurnPolygon


def test_single_turn_corners_for_hand_checked_axis_aligned_case() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.5)

    turn = TurnPolygon.from_parameters(
        inner_radius_mm=10.0,
        phi_deg=0.0,
        alpha_deg=0.0,
        cable=cable,
        current_a=1000.0,
    )

    assert turn.corners == (
        (-2.5, 10.0),
        (2.5, 10.0),
        (2.5, 13.0),
        (-2.5, 13.0),
    )
    assert turn.current_a == 1000.0


def test_block_layer_and_design_flatten_turns_in_radial_stack() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.5)
    block = Block(
        phi_deg=0.0,
        alpha_deg=0.0,
        n_turns=2,
        cable=cable,
        inner_radius_mm=10.0,
        current_a=1000.0,
    )
    layer = Layer(inner_radius_mm=10.0, blocks=(block,))
    design = DipoleDesign(aperture_radius_mm=8.0, layers=(layer,))

    turns = design.all_turns()

    assert len(turns) == 2
    assert turns[0].corners[0] == (-2.5, 10.0)
    assert turns[0].corners[2] == (2.5, 13.0)
    assert turns[1].corners[0] == (-2.5, 13.0)
    assert turns[1].corners[2] == (2.5, 16.0)
