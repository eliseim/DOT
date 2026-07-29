from __future__ import annotations

from dataclasses import replace

import pytest

from dot.geometry import (
    Block,
    CableSpec,
    DipoleDesign,
    Layer,
    block_radiality,
    radiality_summary,
    radialized_block_alpha_deg,
)


def _cable() -> CableSpec:
    return CableSpec(
        width_inner_mm=1.50,
        width_outer_mm=1.62,
        height_mm=12.0,
        insulation_radial_mm=0.10,
        insulation_azimuthal_mm=0.10,
    )


def _block(*, turns: int, phi: float = 20.0, alpha: float = 5.0) -> Block:
    return Block(
        phi_deg=phi,
        alpha_deg=alpha,
        n_turns=turns,
        cable=_cable(),
        inner_radius_mm=35.0,
        current_a=1.0,
    )


def test_block_radiality_uses_the_middle_turn_for_an_odd_block() -> None:
    record = block_radiality(_block(turns=9))

    assert record.center_turn_indices == (4,)
    assert record.deviation_deg >= 0.0


def test_block_radiality_averages_the_two_middle_turns_for_an_even_block() -> None:
    record = block_radiality(_block(turns=8))

    assert record.center_turn_indices == (3, 4)
    assert record.deviation_deg >= 0.0


def test_radialized_alpha_reduces_central_cable_deviation() -> None:
    block = _block(turns=9, phi=25.0, alpha=-10.0)
    before = block_radiality(block).deviation_deg

    alpha = radialized_block_alpha_deg(block, (-20.0, 80.0))
    after = block_radiality(replace(block, alpha_deg=alpha)).deviation_deg

    assert after < before
    assert after == pytest.approx(0.0, abs=1.0e-6)


def test_optimization_summary_can_exclude_fixed_midplane_blocks() -> None:
    fixed_midplane = _block(turns=9, phi=0.0, alpha=0.0)
    adjustable = _block(turns=5, phi=45.0, alpha=0.0)
    design = DipoleDesign(
        aperture_radius_mm=25.0,
        layers=(
            Layer(
                inner_radius_mm=35.0,
                blocks=(fixed_midplane, adjustable),
            ),
        ),
    )

    complete = radiality_summary(design)
    adjustable_only = radiality_summary(design, include_midplane_blocks=False)

    assert len(complete.blocks) == 2
    assert adjustable_only.blocks == (block_radiality(adjustable, block_index=1),)
