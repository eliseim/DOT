from __future__ import annotations

import math

import pytest

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


def test_block_layer_and_design_flatten_azimuthally_wound_turns() -> None:
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
    expected_phi = math.degrees(cable.insulated_width_mm / 10.0)
    expected_anchor = (10.0 * math.sin(math.radians(expected_phi)), 10.0 * math.cos(math.radians(expected_phi)))
    expected_tangent = (math.cos(math.radians(expected_phi)), -math.sin(math.radians(expected_phi)))
    assert turns[1].corners[0] == pytest.approx(
        (
            expected_anchor[0] - 0.5 * cable.insulated_width_mm * expected_tangent[0],
            expected_anchor[1] - 0.5 * cable.insulated_width_mm * expected_tangent[1],
        )
    )
    assert turns[1].corners[2] == pytest.approx(
        (
            expected_anchor[0] + 0.5 * cable.insulated_width_mm * expected_tangent[0]
            + cable.insulated_height_mm * math.sin(math.radians(expected_phi)),
            expected_anchor[1] + 0.5 * cable.insulated_width_mm * expected_tangent[1]
            + cable.insulated_height_mm * math.cos(math.radians(expected_phi)),
        )
    )


def test_block_turns_step_phi_by_insulated_width_at_constant_radius() -> None:
    cable = CableSpec(width_mm=10.0, height_mm=2.0, insulation_thickness_mm=0.0)
    block = Block(
        phi_deg=30.0,
        alpha_deg=0.0,
        n_turns=3,
        cable=cable,
        inner_radius_mm=100.0,
        current_a=1000.0,
    )

    turns = block.turns()

    expected_step = math.degrees(cable.insulated_width_mm / block.inner_radius_mm)
    anchors = tuple(
        ((turn.corners[0][0] + turn.corners[1][0]) / 2.0, (turn.corners[0][1] + turn.corners[1][1]) / 2.0)
        for turn in turns
    )
    phis = tuple(math.degrees(math.atan2(anchor[0], anchor[1])) for anchor in anchors)
    radii = tuple(math.hypot(*anchor) for anchor in anchors)

    assert phis == pytest.approx((30.0, 30.0 + expected_step, 30.0 + 2.0 * expected_step))
    assert radii == pytest.approx((100.0, 100.0, 100.0))
