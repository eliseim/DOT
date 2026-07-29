from __future__ import annotations

import math

import pytest

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.conductors import load_line_margin_percent, solve_short_sample_current
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.optimize import LayerConductorData, field_quality_objective, load_line_margin_objective
from dot.optimize.objectives import (
    PEAK_FIELD_FILAMENTS_PER_AXIS,
    _conductor_turns_by_layer,
    _peak_field_on_own_turns,
    _turn_boundary_sample_points,
    load_line_margin_by_block_detail,
    load_line_margin_detail,
)
from dot.physics import field_at, multipole_coefficients, place_line_current_sources


def test_field_quality_objective_matches_direct_multipole_calculation() -> None:
    design = _asymmetric_design(current_a=250.0)
    r_ref_mm = 5.0
    max_order = 4
    sources = tuple(source for turn in design.all_turns() for source in place_line_current_sources(turn))
    coefficients = multipole_coefficients(sources, order=max_order, r_ref_mm=r_ref_mm)
    expected = max(max(abs(b_n), abs(a_n)) for b_n, a_n in coefficients[1:])

    actual = field_quality_objective(design, r_ref_mm=r_ref_mm, max_order=max_order)

    assert actual == pytest.approx(expected, rel=0.0, abs=1.0e-12)


def test_field_quality_objective_can_select_allowed_normal_orders_explicitly() -> None:
    design = _asymmetric_design(current_a=250.0)
    sources = tuple(
        source
        for turn in design.all_turns()
        for source in place_line_current_sources(turn)
    )
    coefficients = multipole_coefficients(sources, order=7, r_ref_mm=5.0)

    actual = field_quality_objective(
        design,
        r_ref_mm=5.0,
        max_order=7,
        normal_orders=(3, 5, 7),
        include_skew=False,
    )

    assert actual == pytest.approx(
        max(abs(coefficients[order - 1][0]) for order in (3, 5, 7)),
        rel=0.0,
        abs=1.0e-12,
    )


def test_field_quality_objective_scores_signed_normal_harmonic_targets() -> None:
    design = _asymmetric_design(current_a=250.0)
    sources = tuple(
        source
        for turn in design.all_turns()
        for source in place_line_current_sources(turn)
    )
    b3 = multipole_coefficients(sources, order=3, r_ref_mm=5.0)[2][0]

    actual = field_quality_objective(
        design,
        r_ref_mm=5.0,
        max_order=3,
        normal_orders=(3,),
        normal_targets={3: b3 - 2.5},
        include_skew=False,
    )

    assert actual == pytest.approx(2.5, rel=0.0, abs=1.0e-12)


def test_bare_conductor_preserves_each_keystoned_turn_frame() -> None:
    cable = CableSpec(
        height_mm=15.1,
        width_inner_mm=1.736,
        width_outer_mm=2.064,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    design = DipoleDesign(
        aperture_radius_mm=28.0,
        layers=(
            Layer(
                inner_radius_mm=28.15,
                blocks=(
                    Block(
                        phi_deg=70.0,
                        alpha_deg=-12.0,
                        n_turns=4,
                        cable=cable,
                        inner_radius_mm=28.15,
                        current_a=1000.0,
                    ),
                ),
            ),
        ),
    )

    insulated = design.layers[0].blocks[0].turns()
    bare = tuple(item.turn for item in _conductor_turns_by_layer(design))

    assert [turn.alpha_deg for turn in bare] == pytest.approx(
        [turn.alpha_deg for turn in insulated]
    )
    assert len(set(turn.alpha_deg for turn in bare)) == 4
    assert [turn.anchor for turn in bare] == [turn.anchor for turn in insulated]


def test_load_line_margin_objective_matches_direct_loadline_solver_inputs() -> None:
    design = _asymmetric_design(current_a=250.0)
    layer_data = conductor_data()
    temperature_k = 0.0
    expected_layer, expected_peak_t = _direct_peak_field_layer_and_value(design)
    operating_current_a = abs(design.layers[expected_layer].blocks[0].current_a)
    short_sample_a = solve_short_sample_current(
        layer_data.remfit,
        layer_data.strand,
        layer_data.cable,
        temperature_k,
        expected_peak_t / operating_current_a,
    )
    expected = load_line_margin_percent(operating_current_a, short_sample_a)

    actual = load_line_margin_objective(
        design,
        cable_specs_by_layer=(design.layers[0].blocks[0].cable,),
        cadata_by_layer=(layer_data,),
        temperature_k=temperature_k,
    )

    assert actual == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)


def test_load_line_margin_rejects_an_unsupported_layer() -> None:
    design = _two_layer_design(current_a=250.0)

    with pytest.raises(ValueError, match="supported conductor data for every layer"):
        load_line_margin_objective(
            design,
            cable_specs_by_layer=(),
            cadata_by_layer=(None, conductor_data()),  # type: ignore[arg-type]
            temperature_k=0.0,
        )


def test_load_line_margin_detail_identifies_conductor_limited_outer_layer() -> None:
    # Directly answers the "is the minimum margin in the high-field inner
    # layer, or in an outer layer with a weaker conductor?" question (task
    # 0051): layer 0 is closer to the bore (higher peak field), layer 1 is
    # farther out (lower peak field) but deliberately given a much weaker
    # conductor -- the limiting layer must be layer 1, despite its lower
    # field, proving the detail correctly attributes the bottleneck to
    # conductor choice rather than field level.
    design = _two_layer_design(current_a=250.0)
    strong_conductor = conductor_data()
    weak_conductor = _weak_conductor_data()

    records = load_line_margin_detail(
        design,
        cadata_by_layer=(strong_conductor, weak_conductor),
        temperature_k=0.0,
    )

    by_layer = {record.layer_index: record for record in records}
    assert by_layer[0].peak_field_t > by_layer[1].peak_field_t, "layer 0 (inner) must see the higher field"
    assert by_layer[1].margin_percent < by_layer[0].margin_percent, (
        "layer 1 must be the limiting layer despite its lower field, due to its weaker conductor"
    )

    overall_margin = load_line_margin_objective(
        design,
        cable_specs_by_layer=(),
        cadata_by_layer=(strong_conductor, weak_conductor),
        temperature_k=0.0,
    )
    assert overall_margin == pytest.approx(by_layer[1].margin_percent)


def test_load_line_margin_requires_one_supported_record_per_layer() -> None:
    with pytest.raises(ValueError, match="supported conductor data for every layer"):
        load_line_margin_objective(
            _two_layer_design(current_a=250.0),
            cable_specs_by_layer=(),
            cadata_by_layer=(None, None),  # type: ignore[arg-type]
            temperature_k=0.0,
        )


def test_block_margin_detail_uses_continuous_roxie_numbering() -> None:
    design = _two_layer_design(current_a=250.0)
    inner = design.layers[0]
    extra = Block(
        phi_deg=55.0,
        alpha_deg=0.0,
        n_turns=1,
        cable=inner.blocks[0].cable,
        inner_radius_mm=inner.inner_radius_mm,
        current_a=250.0,
    )
    design = DipoleDesign(
        aperture_radius_mm=design.aperture_radius_mm,
        layers=(
            Layer(inner_radius_mm=inner.inner_radius_mm, blocks=(*inner.blocks, extra)),
            design.layers[1],
        ),
    )

    records = load_line_margin_by_block_detail(
        design,
        cadata_by_layer=(conductor_data(), conductor_data()),
        temperature_k=0.0,
    )

    assert [record.roxie_block for record in records] == [1, 2, 3]
    assert [(record.layer_index, record.block_index) for record in records] == [
        (0, 0),
        (0, 1),
        (1, 0),
    ]
    assert all(math.isfinite(record.margin_percent) for record in records)


def test_peak_field_uses_bare_conductor_geometry_not_insulation_boundary() -> None:
    insulated_design = _keystoned_design(current_a=120.0)
    bare_design = _keystoned_design(current_a=120.0, insulation_mm=0.0)

    _, insulated_peak_t = _peak_field_on_own_turns(insulated_design)
    _, bare_peak_t = _peak_field_on_own_turns(bare_design)

    assert insulated_peak_t == pytest.approx(bare_peak_t)


def _asymmetric_design(*, current_a: float) -> DipoleDesign:
    cable = CableSpec(width_mm=2.0, height_mm=2.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=12.0,
                blocks=(
                    Block(
                        phi_deg=12.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=current_a,
                    ),
                    Block(
                        phi_deg=41.0,
                        alpha_deg=0.0,
                        n_turns=2,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=current_a,
                    ),
                ),
            ),
        ),
    )


def _two_layer_design(*, current_a: float) -> DipoleDesign:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=10.0,
                blocks=(
                    Block(
                        phi_deg=15.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=10.0,
                        current_a=current_a,
                    ),
                ),
            ),
            Layer(
                inner_radius_mm=32.0,
                blocks=(
                    Block(
                        phi_deg=55.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=32.0,
                        current_a=current_a,
                    ),
                ),
            ),
        ),
    )


def _keystoned_design(*, current_a: float, insulation_mm: float = 0.5) -> DipoleDesign:
    cable = CableSpec(
        width_inner_mm=2.0,
        width_outer_mm=4.0,
        height_mm=2.0,
        insulation_thickness_mm=insulation_mm,
    )
    block = Block(
        phi_deg=0.0,
        alpha_deg=0.0,
        n_turns=1,
        cable=cable,
        inner_radius_mm=10.0,
        current_a=current_a,
    )
    return DipoleDesign(aperture_radius_mm=5.0, layers=(Layer(inner_radius_mm=10.0, blocks=(block,)),))


def _direct_peak_field_layer_and_value(design: DipoleDesign) -> tuple[int, float]:
    indexed_turns = _conductor_turns_by_layer(design)
    sources = tuple(
        source
        for indexed in indexed_turns
        for source in place_line_current_sources(
            indexed.turn,
            n1=PEAK_FIELD_FILAMENTS_PER_AXIS,
            n2=PEAK_FIELD_FILAMENTS_PER_AXIS,
        )
    )
    best_layer = -1
    best_field = -math.inf
    for indexed in indexed_turns:
        for x_mm, y_mm in _turn_boundary_sample_points(indexed.turn):
            bx_t, by_t = field_at(sources, x_mm, y_mm)
            magnitude = math.hypot(bx_t, by_t)
            if magnitude > best_field:
                best_layer = indexed.layer_index
                best_field = magnitude
    return best_layer, best_field

def conductor_data() -> LayerConductorData:
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    area_m2 = math.pi * 1.0**2 / 4.0 * 1.0e-6
    zero_field_cable_current_a = 5000.0
    remfit = Type1FitCoefficients(
        c1=10.0 * zero_field_cable_current_a / area_m2,
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=20.1,
    )
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)


def _weak_conductor_data() -> LayerConductorData:
    # Same strand/cable geometry as conductor_data(), but a much lower
    # zero-field critical current -- a stand-in for a lower-field-class
    # conductor (e.g. NbTi vs Nb3Sn) with an unfavorable critical-current
    # curve, used to prove an outer, lower-field layer can still be the
    # margin-limiting one.
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    area_m2 = math.pi * 1.0**2 / 4.0 * 1.0e-6
    zero_field_cable_current_a = 300.0
    remfit = Type1FitCoefficients(
        c1=10.0 * zero_field_cable_current_a / area_m2,
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=20.1,
    )
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)
