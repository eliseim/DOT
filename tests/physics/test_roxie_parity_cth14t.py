from __future__ import annotations

import math

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.physics import field_at, multipole_coefficients, place_line_current_sources

CURRENT_A = 12238.0
R_REF_MM = 16.6667
REFERENCE_FIELD_T = 12.419091
REFERENCE_MAIN_DIPOLE_UNITS = 10000.0

CTH_HF = CableSpec(width_mm=1.594, height_mm=18.363, insulation_thickness_mm=0.145)
CTH_LF = CableSpec(width_mm=1.91, height_mm=16.17, insulation_thickness_mm=0.145)

BLOCK_TABLE = (
    (1, 4, 25.0, 0.343771, 0.0, CTH_HF, 20),
    (2, 6, 25.0, 20.2269, 23.4754, CTH_HF, 20),
    (3, 3, 25.0, 48.7, 46.4651, CTH_HF, 20),
    (4, 2, 25.0, 66.5, 65.9882, CTH_HF, 20),
    (5, 13, 44.153, 0.194649, 0.0, CTH_HF, 20),
    (6, 14, 44.153, 33.9911, 42.3351, CTH_HF, 20),
    (7, 18, 63.306, 0.135759, 0.0, CTH_LF, 15),
    (8, 2, 63.306, 35.0656, 35.0776, CTH_LF, 15),
    (9, 24, 80.269, 0.10707, 0.0, CTH_LF, 15),
)


def test_dot_field_quality_matches_real_no_iron_roxie_cth14t_output() -> None:
    """Validate DOT's bulk dipole-field parity against a real ROXIE CTH-14T run.

    The ROXIE block table is converted into DOT's angle conventions below. This
    test intentionally does not require exact harmonic-by-harmonic agreement:
    ROXIE's reference turn positions were independently optimized to cancel
    specific harmonics, while DOT's formula-based turn placement reproduces the
    bulk current distribution without trying to reverse-engineer that optimized
    fine geometry.
    """
    design = _cth14t_design()
    sources = tuple(
        source
        for layer in design.layers
        for block in layer.blocks
        for turn in block.turns()
        for source in place_line_current_sources(turn, n1=2, n2=_n2_for_block(block))
    )

    bx_t, by_t = field_at(sources, 0.0, 0.0)
    field_magnitude_t = math.hypot(bx_t, by_t)
    coefficients = multipole_coefficients(sources, order=13, r_ref_mm=R_REF_MM)

    assert field_magnitude_t == pytest.approx(REFERENCE_FIELD_T, rel=0.02)
    assert coefficients[0][0] == pytest.approx(REFERENCE_MAIN_DIPOLE_UNITS, abs=2.0)
    for normal, _ in coefficients:
        assert math.isfinite(normal)
        assert abs(normal) < 20000.0
    for _, skew in coefficients:
        assert skew == pytest.approx(0.0, abs=1.0)


def _cth14t_design() -> DipoleDesign:
    layers: list[Layer] = []
    for radius_mm in (25.0, 44.153, 63.306, 80.269):
        blocks = tuple(_block(record) for record in BLOCK_TABLE if record[2] == radius_mm)
        layers.append(Layer(inner_radius_mm=radius_mm, blocks=blocks))
    return DipoleDesign(aperture_radius_mm=R_REF_MM, layers=tuple(layers))


def _block(record: tuple[int, int, float, float, float, CableSpec, int]) -> Block:
    _, n_turns, radius_mm, phi_roxie_deg, alpha_roxie_deg, cable, _ = record
    return Block(
        phi_deg=90.0 - phi_roxie_deg,
        alpha_deg=-alpha_roxie_deg,
        n_turns=n_turns,
        cable=cable,
        inner_radius_mm=radius_mm,
        current_a=CURRENT_A,
    )


def _n2_for_block(block: Block) -> int:
    for record in BLOCK_TABLE:
        _, n_turns, radius_mm, phi_roxie_deg, alpha_roxie_deg, cable, n2 = record
        if (
            block.n_turns == n_turns
            and block.inner_radius_mm == radius_mm
            and block.phi_deg == 90.0 - phi_roxie_deg
            and block.alpha_deg == -alpha_roxie_deg
            and block.cable == cable
        ):
            return n2
    raise AssertionError("unexpected CTH-14T block")
