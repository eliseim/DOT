from __future__ import annotations

import math

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.optimize import operating_point
from dot.optimize.operating_point import operating_point_at_current
from dot.physics import field_at, place_line_current_sources


def test_operating_point_scales_current_exactly_from_unit_current_field() -> None:
    design = _one_block_design(current_a=1.0)
    sources = tuple(
        source for turn in design.all_turns() for source in place_line_current_sources(turn)
    )
    _, unit_by_t = field_at(sources, 0.0, 0.0)
    target_t = 0.02
    expected_scale = target_t / unit_by_t

    solved = operating_point(design, target_t)

    assert solved.unit_bore_field_t == pytest.approx(unit_by_t, rel=0.0, abs=1.0e-15)
    assert solved.scale_factor == pytest.approx(expected_scale, rel=1.0e-12)
    assert solved.operating_current_a == pytest.approx(expected_scale)
    assert solved.design.layers[0].blocks[0].current_a == pytest.approx(expected_scale)

    scaled_sources = tuple(
        source for turn in solved.design.all_turns() for source in place_line_current_sources(turn)
    )
    _, scaled_by_t = field_at(scaled_sources, 0.0, 0.0)
    assert math.isclose(scaled_by_t, target_t, rel_tol=1.0e-12, abs_tol=1.0e-15)

    solved_again = operating_point(solved.design, target_t)
    assert solved_again.scale_factor == pytest.approx(1.0)
    assert solved_again.operating_current_a == pytest.approx(expected_scale)


def test_operating_point_at_current_sets_exact_magnitude_and_target_polarity() -> None:
    design = _one_block_design(current_a=1.0)
    solved = operating_point_at_current(
        design,
        12000.0,
        target_bore_field_t=0.02,
    )

    assert abs(solved.operating_current_a) == pytest.approx(12000.0)
    assert abs(solved.design.layers[0].blocks[0].current_a) == pytest.approx(12000.0)
    sources = tuple(
        source for turn in solved.design.all_turns() for source in place_line_current_sources(turn)
    )
    _, bore_field_t = field_at(sources, 0.0, 0.0)
    assert bore_field_t > 0.0


def _one_block_design(*, current_a: float) -> DipoleDesign:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=12.0,
                blocks=(
                    Block(
                        phi_deg=25.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=current_a,
                    ),
                ),
            ),
        ),
    )
