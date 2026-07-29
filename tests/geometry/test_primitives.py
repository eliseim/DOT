from __future__ import annotations

import math

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer, TurnPolygon


def test_single_turn_corners_for_hand_checked_absolute_alpha_axis_aligned_case() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.5)

    turn = TurnPolygon.from_parameters(
        inner_radius_mm=10.0,
        phi_deg=90.0,
        alpha_deg=0.0,
        cable=cable,
        current_a=1000.0,
    )

    expected = (
        (0.0, 7.5),
        (0.0, 12.5),
        (3.0, 12.5),
        (3.0, 7.5),
    )
    for actual, wanted in zip(turn.corners, expected, strict=True):
        assert actual == pytest.approx(wanted)
    assert turn.current_a == 1000.0


def test_single_turn_corners_for_hand_checked_keystoned_trapezoid_case() -> None:
    cable = CableSpec(
        width_inner_mm=4.0,
        width_outer_mm=6.0,
        height_mm=2.0,
        insulation_radial_mm=0.25,
        insulation_azimuthal_mm=0.5,
    )

    turn = TurnPolygon.from_parameters(
        inner_radius_mm=10.0,
        phi_deg=90.0,
        alpha_deg=0.0,
        cable=cable,
        current_a=1000.0,
    )

    expected = (
        (0.0, 10.0),
        (0.0, 15.0),
        (2.5, 17.0),
        (2.5, 10.0),
    )
    for actual, wanted in zip(turn.corners, expected, strict=True):
        assert actual == pytest.approx(wanted)
    inner_width = math.dist(turn.corners[0], turn.corners[1])
    outer_width = math.dist(turn.corners[3], turn.corners[2])
    assert inner_width == pytest.approx(5.0)
    assert outer_width == pytest.approx(7.0)
    assert inner_width != pytest.approx(outer_width)


def test_turn_height_axis_uses_absolute_alpha_independent_of_phi() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.5)
    expected_height_axis = (
        math.cos(math.radians(46.4651)),
        math.sin(math.radians(46.4651)),
    )

    turns = tuple(
        TurnPolygon.from_parameters(
            inner_radius_mm=25.0,
            phi_deg=phi_deg,
            alpha_deg=46.4651,
            cable=cable,
            current_a=1000.0,
        )
        for phi_deg in (41.3, 72.0)
    )

    for turn in turns:
        actual_height_axis = (
            (turn.corners[3][0] - turn.corners[0][0]) / cable.insulated_height_mm,
            (turn.corners[3][1] - turn.corners[0][1]) / cable.insulated_height_mm,
        )
        assert actual_height_axis == pytest.approx(expected_height_axis, rel=0.0, abs=1e-12)

    first_axis = (
        (turns[0].corners[3][0] - turns[0].corners[0][0]) / cable.insulated_height_mm,
        (turns[0].corners[3][1] - turns[0].corners[0][1]) / cable.insulated_height_mm,
    )
    second_axis = (
        (turns[1].corners[3][0] - turns[1].corners[0][0]) / cable.insulated_height_mm,
        (turns[1].corners[3][1] - turns[1].corners[0][1]) / cable.insulated_height_mm,
    )
    assert second_axis == pytest.approx(first_axis, rel=0.0, abs=1e-12)


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
    assert turns[0].corners[0] == pytest.approx((10.0, -2.5))
    assert turns[0].corners[2] == pytest.approx((13.0, 2.5))
    expected_anchor = (
        math.sqrt(10.0 * 10.0 - cable.insulated_width_inner_mm * cable.insulated_width_inner_mm),
        cable.insulated_width_inner_mm,
    )
    assert turns[1].corners[0] == pytest.approx(
        (
            expected_anchor[0],
            expected_anchor[1] - 0.5 * cable.insulated_width_inner_mm,
        )
    )
    assert turns[1].corners[2] == pytest.approx(
        (
            expected_anchor[0] + cable.insulated_height_mm,
            expected_anchor[1] + 0.5 * cable.insulated_width_outer_mm,
        )
    )


def test_block_turns_project_width_step_onto_local_arc_tangent() -> None:
    cable = CableSpec(width_mm=10.0, height_mm=2.0)
    block = Block(
        phi_deg=30.0,
        alpha_deg=0.0,
        n_turns=3,
        cable=cable,
        inner_radius_mm=100.0,
        current_a=1000.0,
    )

    turns = block.turns()

    anchors = tuple(
        (
            0.5 * (turn.corners[0][0] + turn.corners[1][0]),
            0.5 * (turn.corners[0][1] + turn.corners[1][1]),
        )
        for turn in turns
    )
    phis = tuple(math.degrees(math.atan2(anchor[1], anchor[0])) for anchor in anchors)
    radii = tuple(math.hypot(*anchor) for anchor in anchors)
    expected_phi_1 = math.degrees(
        math.asin(
            (
                block.inner_radius_mm * math.sin(math.radians(block.phi_deg))
                + cable.insulated_width_inner_mm
            )
            / block.inner_radius_mm
        )
    )
    expected_phi_2 = math.degrees(
        math.asin(
            (
                block.inner_radius_mm * math.sin(math.radians(expected_phi_1))
                + cable.insulated_width_inner_mm
            )
            / block.inner_radius_mm
        )
    )

    assert phis == pytest.approx(
        (
            30.0,
            expected_phi_1,
            expected_phi_2,
        )
    )
    assert radii == pytest.approx((100.0, 100.0, 100.0))


def test_block_turns_match_cth_lf_multiturn_arc_projection_and_keystone_tilt() -> None:
    cable = CableSpec(
        width_inner_mm=1.736,
        width_outer_mm=2.084,
        height_mm=16.17,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    block = Block(
        phi_deg=55.0,
        alpha_deg=0.0,
        n_turns=2,
        cable=cable,
        inner_radius_mm=35.0,
        current_a=1000.0,
    )

    turns = block.turns()

    anchors = tuple(turn.corners[0] for turn in turns)
    phis = tuple(math.degrees(math.atan2(anchor[1], anchor[0])) for anchor in anchors)
    wrong_step = math.degrees(cable.insulated_width_inner_mm / block.inner_radius_mm)
    projected_step = phis[1] - phis[0]
    expected_projected_step = math.degrees(
        math.asin(
            (
                block.inner_radius_mm * math.sin(math.radians(block.phi_deg))
                + cable.insulated_width_inner_mm
            )
            / block.inner_radius_mm
        )
    )
    keystone_deg = math.degrees(
        math.atan2(
            cable.width_outer_mm - cable.width_inner_mm,
            cable.height_mm,
        )
    )
    second_height_axis = (
        (turns[1].corners[3][0] - turns[1].corners[0][0]) / cable.insulated_height_mm,
        (turns[1].corners[3][1] - turns[1].corners[0][1]) / cable.insulated_height_mm,
    )

    assert wrong_step == pytest.approx(3.316607122671565)
    assert projected_step == pytest.approx(expected_projected_step - 55.0)
    assert projected_step == pytest.approx(6.287068778190076)
    assert second_height_axis == pytest.approx((math.cos(math.radians(keystone_deg)), math.sin(math.radians(keystone_deg))))


def test_block_turns_keep_radius_when_width_stack_reaches_pole() -> None:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    block = Block(
        phi_deg=45.0,
        alpha_deg=0.0,
        n_turns=4,
        cable=cable,
        inner_radius_mm=30.0,
        current_a=1000.0,
    )

    turns = block.turns()

    anchors = tuple(
        ((turn.corners[0][0] + turn.corners[1][0]) / 2.0, (turn.corners[0][1] + turn.corners[1][1]) / 2.0)
        for turn in turns
    )
    phis = tuple(math.degrees(math.atan2(anchor[1], anchor[0])) for anchor in anchors)
    radii = tuple(math.hypot(*anchor) for anchor in anchors)

    assert phis == pytest.approx(
        (
            45.0,
            math.degrees(math.asin((30.0 * math.sin(math.radians(45.0)) + 4.0) / 30.0)),
            math.degrees(math.asin((30.0 * math.sin(math.radians(45.0)) + 8.0) / 30.0)),
            90.0,
        )
    )
    assert radii == pytest.approx((30.0, 30.0, 30.0, 30.0))


def test_block_turns_reuses_exact_immutable_geometry() -> None:
    block = Block(
        phi_deg=17.0,
        alpha_deg=19.0,
        n_turns=4,
        cable=CableSpec(
            width_inner_mm=1.2,
            width_outer_mm=1.4,
            height_mm=14.0,
        ),
        inner_radius_mm=28.0,
        current_a=1.0,
    )

    first = block.turns()
    second = block.turns()
    equal_block = Block(
        phi_deg=block.phi_deg,
        alpha_deg=block.alpha_deg,
        n_turns=block.n_turns,
        cable=block.cable,
        inner_radius_mm=block.inner_radius_mm,
        current_a=block.current_a,
    )

    assert second is first
    assert equal_block.turns() is first
