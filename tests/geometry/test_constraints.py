from __future__ import annotations

import math

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer, TurnPolygon
from dot.geometry.constraints import (
    check_aperture_clearance,
    check_feasibility,
    check_inter_layer_spacing,
    check_midplane_clearance,
    check_pole_angle_limit,
    check_turn_non_intersection,
)


def test_aperture_clearance_accepts_turn_outside_aperture() -> None:
    design = _single_turn_design(inner_radius_mm=10.0, phi_deg=20.0)

    assert check_aperture_clearance(design, aperture_radius_mm=8.0) == []


def test_aperture_clearance_rejects_turn_inside_aperture() -> None:
    design = _single_turn_design(inner_radius_mm=10.0, phi_deg=20.0)

    violations = check_aperture_clearance(design, aperture_radius_mm=10.5)

    assert [violation.constraint_name for violation in violations] == ["aperture_clearance"]
    assert violations[0].layer_index == 0
    assert violations[0].block_index == 0
    assert violations[0].turn_index == 0
    assert violations[0].severity == pytest.approx(1.4332394106670137)


def test_inter_layer_spacing_accepts_radially_separated_layers() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            _layer(inner_radius_mm=10.0, phi_deg=0.0, cable=cable),
            _layer(inner_radius_mm=13.0, phi_deg=0.0, cable=cable),
        ),
    )

    assert check_inter_layer_spacing(design, min_clearance_mm=0.1) == []


def test_inter_layer_spacing_rejects_radially_overlapping_layers() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            _layer(inner_radius_mm=10.0, phi_deg=0.0, cable=cable),
            _layer(inner_radius_mm=12.0, phi_deg=0.0, cable=cable),
        ),
    )

    violations = check_inter_layer_spacing(design, min_clearance_mm=0.1)

    assert [violation.constraint_name for violation in violations] == ["inter_layer_spacing"]
    assert violations[0].layer_index == 1
    assert violations[0].severity == pytest.approx(0.28033988749894867)


def test_check_feasibility_rejects_inter_layer_overlap_across_empty_layer() -> None:
    inner_turn = TurnPolygon(
        corners=((-1.0, 10.0), (1.0, 10.0), (1.0, 12.0), (-1.0, 12.0)),
        current_a=1000.0,
    )
    outer_turn = TurnPolygon(
        corners=((8.0, 8.0), (10.0, 8.0), (10.0, 10.0), (8.0, 10.0)),
        current_a=1000.0,
    )
    design = DipoleDesign(
        aperture_radius_mm=1.0,
        layers=(
            Layer(inner_radius_mm=10.0, blocks=(_FixedTurnBlock(inner_turn),)),
            Layer(inner_radius_mm=11.0, blocks=()),
            Layer(inner_radius_mm=11.0, blocks=(_FixedTurnBlock(outer_turn),)),
        ),
    )

    result = check_feasibility(
        design,
        aperture_radius_mm=1.0,
        min_gap_mm=1.0,
        max_angle_deg=80.0,
        min_layer_clearance_mm=0.1,
    )

    assert result.is_feasible is False
    assert any(
        violation.constraint_name == "inter_layer_spacing"
        and violation.layer_index == 2
        and violation.other_layer_index == 0
        for violation in result.violations
    )
    assert not any(
        violation.constraint_name == "turn_non_intersection"
        for violation in result.violations
    )


def test_midplane_clearance_accepts_hand_computed_gap() -> None:
    design = _midplane_reference_design()
    hand_computed_lowest_y_mm = 10.0 * math.cos(math.radians(60.0)) - 4.0 / 2.0

    assert hand_computed_lowest_y_mm == pytest.approx(3.0, rel=0.0, abs=1.0e-12)
    assert check_midplane_clearance(design, min_gap_mm=3.0) == []


def test_midplane_clearance_rejects_hand_computed_gap() -> None:
    design = _midplane_reference_design()

    violations = check_midplane_clearance(design, min_gap_mm=3.3)

    assert [violation.constraint_name for violation in violations] == ["midplane_clearance"]
    assert violations[0].layer_index == 0
    assert violations[0].block_index == 0
    assert violations[0].turn_index == 0
    assert violations[0].severity == pytest.approx(0.3)


def test_turn_non_intersection_accepts_edge_contact_between_stacked_turns() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    block = Block(
        phi_deg=20.0,
        alpha_deg=0.0,
        n_turns=2,
        cable=cable,
        inner_radius_mm=10.0,
        current_a=1000.0,
    )
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(Layer(inner_radius_mm=10.0, blocks=(block,)),),
    )

    assert check_turn_non_intersection(design) == []


def test_turn_non_intersection_rejects_positive_area_polygon_overlap() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    first = Block(
        phi_deg=20.0,
        alpha_deg=0.0,
        n_turns=1,
        cable=cable,
        inner_radius_mm=10.0,
        current_a=1000.0,
    )
    second = Block(
        phi_deg=20.0,
        alpha_deg=0.0,
        n_turns=1,
        cable=cable,
        inner_radius_mm=10.5,
        current_a=1000.0,
    )
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(Layer(inner_radius_mm=10.0, blocks=(first, second)),),
    )

    violations = check_turn_non_intersection(design)

    assert [violation.constraint_name for violation in violations] == ["turn_non_intersection"]
    assert violations[0].layer_index == 0
    assert violations[0].block_index == 0
    assert violations[0].turn_index == 0
    assert violations[0].other_layer_index == 0
    assert violations[0].other_block_index == 1
    assert violations[0].other_turn_index == 0
    assert violations[0].severity > 0.0


def test_pole_angle_limit_accepts_outer_edge_below_limit() -> None:
    design = _single_turn_design(inner_radius_mm=10.0, phi_deg=20.0)

    assert check_pole_angle_limit(design, max_angle_deg=33.0) == []


def test_pole_angle_limit_rejects_outer_edge_above_limit() -> None:
    design = _single_turn_design(inner_radius_mm=10.0, phi_deg=40.0)

    violations = check_pole_angle_limit(design, max_angle_deg=30.0)

    assert [violation.constraint_name for violation in violations] == ["pole_angle_limit"]
    assert violations[0].layer_index == 0
    assert violations[0].block_index == 0
    assert violations[0].turn_index == 0
    assert violations[0].severity > 0.0


def test_pole_angle_limit_applies_per_layer_limits() -> None:
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(inner_radius_mm=10.0, blocks=(_FixedTurnBlock(_turn_with_outer_angle(82.0)),)),
            Layer(inner_radius_mm=14.0, blocks=(_FixedTurnBlock(_turn_with_outer_angle(84.0)),)),
        ),
    )

    assert check_pole_angle_limit(design, max_angle_deg=85.0) == []

    violations = check_pole_angle_limit(design, max_angle_deg=(80.0, 85.0))

    assert [violation.constraint_name for violation in violations] == ["pole_angle_limit"]
    assert violations[0].layer_index == 0


def test_pole_angle_limit_rejects_per_layer_length_mismatch() -> None:
    with pytest.raises(ValueError, match="sequence length must equal"):
        check_pole_angle_limit(_valid_two_layer_design(), max_angle_deg=(80.0,))


def test_check_feasibility_accepts_valid_hand_constructed_design() -> None:
    result = check_feasibility(
        _valid_two_layer_design(),
        aperture_radius_mm=8.0,
        min_gap_mm=1.0,
        max_angle_deg=45.0,
    )

    assert result.is_feasible is True
    assert result.violations == ()


def test_check_feasibility_aggregates_identified_turn_overlap_violation() -> None:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    overlapping = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=10.0,
                blocks=(
                    Block(
                        phi_deg=20.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=10.0,
                        current_a=1000.0,
                    ),
                    Block(
                        phi_deg=20.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=10.5,
                        current_a=1000.0,
                    ),
                ),
            ),
        ),
    )

    result = check_feasibility(
        overlapping,
        aperture_radius_mm=8.0,
        min_gap_mm=1.0,
        max_angle_deg=45.0,
    )

    assert result.is_feasible is False
    assert any(
        violation.constraint_name == "turn_non_intersection"
        and violation.layer_index == 0
        and violation.block_index == 0
        and violation.turn_index == 0
        and violation.other_block_index == 1
        for violation in result.violations
    )


def _single_turn_design(*, inner_radius_mm: float, phi_deg: float) -> DipoleDesign:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(_layer(inner_radius_mm=inner_radius_mm, phi_deg=phi_deg, cable=cable),),
    )


def _midplane_reference_design() -> DipoleDesign:
    cable = CableSpec(width_mm=4.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=6.0,
        layers=(_layer(inner_radius_mm=10.0, phi_deg=60.0, cable=cable),),
    )


def _valid_two_layer_design() -> DipoleDesign:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    first = Block(
        phi_deg=20.0,
        alpha_deg=0.0,
        n_turns=2,
        cable=cable,
        inner_radius_mm=10.0,
        current_a=1000.0,
    )
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(inner_radius_mm=10.0, blocks=(first,)),
            _layer(inner_radius_mm=15.0, phi_deg=20.0, cable=cable),
        ),
    )


def _layer(*, inner_radius_mm: float, phi_deg: float, cable: CableSpec) -> Layer:
    return Layer(
        inner_radius_mm=inner_radius_mm,
        blocks=(
            Block(
                phi_deg=phi_deg,
                alpha_deg=0.0,
                n_turns=1,
                cable=cable,
                inner_radius_mm=inner_radius_mm,
                current_a=1000.0,
            ),
        ),
    )


def _turn_with_outer_angle(angle_deg: float) -> TurnPolygon:
    return TurnPolygon(
        corners=(
            _point_at_angle(angle_deg - 2.0, 10.0),
            _point_at_angle(angle_deg - 2.0, 11.0),
            _point_at_angle(angle_deg, 12.0),
            _point_at_angle(angle_deg, 13.0),
        ),
        current_a=1000.0,
    )


def _point_at_angle(angle_deg: float, radius_mm: float) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg)
    return (radius_mm * math.sin(angle_rad), radius_mm * math.cos(angle_rad))


def test_sat_overlap_test_uses_finite_polygons_not_radius_envelopes() -> None:
    first = TurnPolygon(
        corners=((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)),
        current_a=1000.0,
    )
    second = TurnPolygon(
        corners=((3.0, 1.0), (5.0, 1.0), (5.0, 3.0), (3.0, 3.0)),
        current_a=1000.0,
    )
    first_block = _FixedTurnBlock(first)
    second_block = _FixedTurnBlock(second)
    design = DipoleDesign(
        aperture_radius_mm=0.1,
        layers=(Layer(inner_radius_mm=1.0, blocks=(first_block, second_block)),),
    )

    violations = check_turn_non_intersection(design)

    assert [violation.constraint_name for violation in violations] == ["turn_non_intersection"]


class _FixedTurnBlock:
    def __init__(self, turn: TurnPolygon) -> None:
        self._turn = turn

    def turns(self) -> tuple[TurnPolygon, ...]:
        return (self._turn,)
