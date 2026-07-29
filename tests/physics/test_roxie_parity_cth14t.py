from __future__ import annotations

import math
from pathlib import Path

import pytest

from dot.conductors import resolve_conductor
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize import LayerConductorData
from dot.optimize.objectives import (
    CERTIFICATION_FIDELITY,
    SEARCH_FIDELITY,
    harmonic_table,
    load_line_margin_detail,
)
from dot.optimize.operating_point import operating_point
from dot.physics import field_at, multipole_coefficients, place_line_current_sources

CURRENT_A = 12238.0
R_REF_MM = 16.6667
REFERENCE_FIELD_T = 12.419091
REFERENCE_MAIN_DIPOLE_UNITS = 10000.0
REFERENCE_HARMONICS = {
    3: -4.20941,
    5: 1.74497,
    7: 2.10137,
    9: 0.79814,
    11: 1.42473,
}

CTH_HF = CableSpec(
    width_inner_mm=1.53,
    width_outer_mm=1.658,
    height_mm=18.363,
    insulation_radial_mm=0.145,
    insulation_azimuthal_mm=0.145,
)
CTH_LF = CableSpec(
    width_inner_mm=1.736,
    width_outer_mm=2.084,
    height_mm=16.17,
    insulation_radial_mm=0.145,
    insulation_azimuthal_mm=0.145,
)

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


def test_cth_report_block_angles_are_native_dot_inputs() -> None:
    """Page 11 values require no complementary/sign conversion in DOT."""

    design = _cth14t_design()
    inner_blocks = design.layers[0].blocks

    assert [block.phi_deg for block in inner_blocks] == pytest.approx(
        [0.343771, 20.2269, 48.7, 66.5]
    )
    assert [block.alpha_deg for block in inner_blocks] == pytest.approx(
        [0.0, 23.4754, 46.4651, 65.9882]
    )
    assert inner_blocks[0].phi_deg < inner_blocks[-1].phi_deg


def test_dot_field_quality_matches_real_no_iron_roxie_cth14t_output() -> None:
    """Validate DOT's bulk dipole-field parity against a real ROXIE CTH-14T run.

    The ROXIE block table is passed directly into DOT's native convention. This
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


def test_published_cth_geometry_is_feasible_with_true_aperture_and_gaps() -> None:
    result = check_feasibility(
        _cth14t_design(),
        aperture_radius_mm=25.0,
        min_gap_mm=0.15,
        max_angle_deg=(80.0, 85.0, 85.0, 85.0),
        min_layer_clearance_mm=0.5,
        min_inter_block_gap_mm=0.1,
        # The public report table is rounded; 0.05 mm covers its first-block
        # radius rounding without weakening campaign engineering clearances.
        geometry_tolerance_mm=0.05,
    )

    assert result.is_feasible, result.violations


def test_certification_fidelity_matches_no_iron_roxie_cth_harmonic_vector() -> None:
    table = harmonic_table(
        _cth14t_design(),
        R_REF_MM,
        11,
        CERTIFICATION_FIDELITY,
    )

    by_order = {order: b_n for order, b_n, _ in table}
    for order, expected in REFERENCE_HARMONICS.items():
        assert by_order[order] == pytest.approx(expected, abs=1.5)


def test_search_fidelity_does_not_hide_the_cth_loadline_margin() -> None:
    root = Path(__file__).resolve().parents[2]
    cadata = (root / "campaign" / "dot_cables.cadata").read_text(encoding="utf-8")
    resolutions = tuple(
        resolve_conductor(cadata, name) for name in ("CTH_HF", "CTH_HF", "CTH_LF", "CTH_LF")
    )
    conductor_data = tuple(
        LayerConductorData(
            strand=resolution.strand,
            cable=resolution.cable,
            remfit=resolution.remfit,
        )
        for resolution in resolutions
    )
    solved = operating_point(_cth14t_design(), 12.4)

    margins = load_line_margin_detail(
        solved.design,
        conductor_data,
        1.9,
        fidelity=SEARCH_FIDELITY,
    )

    assert min(record.margin_percent for record in margins) >= 25.0


def test_search_harmonics_track_certification_without_false_low_order_optimum() -> None:
    """The fast Gaussian rule must stay close to the dense certification vector."""

    design = _cth14t_design()
    search = harmonic_table(design, R_REF_MM, 11, SEARCH_FIDELITY)
    certification = harmonic_table(design, R_REF_MM, 11, CERTIFICATION_FIDELITY)
    search_by_order = {order: normal for order, normal, _skew in search}
    certification_by_order = {order: normal for order, normal, _skew in certification}

    for order in REFERENCE_HARMONICS:
        assert search_by_order[order] == pytest.approx(
            certification_by_order[order],
            abs=0.35,
        )


def _cth14t_design() -> DipoleDesign:
    layers: list[Layer] = []
    for radius_mm in (25.0, 44.153, 63.306, 80.269):
        blocks = tuple(_block(record) for record in BLOCK_TABLE if record[2] == radius_mm)
        layers.append(Layer(inner_radius_mm=radius_mm, blocks=blocks))
    return DipoleDesign(aperture_radius_mm=25.0, layers=tuple(layers))


def _block(record: tuple[int, int, float, float, float, CableSpec, int]) -> Block:
    _, n_turns, radius_mm, phi_roxie_deg, alpha_roxie_deg, cable, _ = record
    return Block(
        phi_deg=phi_roxie_deg,
        alpha_deg=alpha_roxie_deg,
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
            and block.phi_deg == phi_roxie_deg
            and block.alpha_deg == alpha_roxie_deg
            and block.cable == cable
        ):
            return n2
    raise AssertionError("unexpected CTH-14T block")
