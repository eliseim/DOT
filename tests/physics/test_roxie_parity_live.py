from __future__ import annotations

import math
import os
import re
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from dot.conductors import load_line_margin_percent, solve_short_sample_current
from dot.conductors.cadata import resolve_conductor
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize import LayerConductorData, load_line_margin_objective
from dot.optimize.operating_point import operating_point
from dot.optimize.objectives import _peak_field_on_own_turns
from dot.physics import field_at, place_line_current_sources

pytestmark = pytest.mark.live_roxie

ROXIE_SERVICE_URL = os.environ.get("ROXIE_SERVICE_URL", "http://127.0.0.1:8080")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ROXIE_TEMPLATE_ENV = os.environ.get("DOT_ROXIE_TEMPLATE")
ROXIE_TEMPLATE = Path(_ROXIE_TEMPLATE_ENV) if _ROXIE_TEMPLATE_ENV else None
ROXIE_CADATA = Path(
    os.environ.get(
        "DOT_ROXIE_CADATA",
        str(REPOSITORY_ROOT / "campaign" / "dot_cables.cadata"),
    )
)
FIELD_TOLERANCE_REL = 0.02
MARGIN_TOLERANCE_PERCENTAGE_POINTS = 2.0
FIT_PARITY_FIELD_TOLERANCE_REL = 0.03
FIT_PARITY_MARGIN_TOLERANCE_PERCENTAGE_POINTS = 0.05

CURRENT_A = 12238.0
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


@dataclass(frozen=True)
class RoxieBlockRecord:
    number: int
    n_turns: int
    radius_mm: float
    phi_roxie_deg: float
    alpha_roxie_deg: float
    current_a: float
    conductor_name: str
    n2: int


@dataclass(frozen=True)
class LiveComparison:
    dot_field_t: float
    roxie_field_t: float
    relative_error: float


@dataclass(frozen=True)
class LiveMarginComparison:
    case_name: str
    dot_peak_t: float
    roxie_peak_t: float
    peak_relative_error: float
    dot_margin_percent: float
    roxie_margin_percent: float
    margin_error_percentage_points: float


def test_live_roxie_field_parity_cth14t(tmp_path: Path) -> None:
    _require_live_roxie()

    cth_comparison = _compare_with_roxie(
        tmp_path,
        case_name="cth14t_no_iron",
        design=_cth14t_design(),
        block_records=_cth_block_records(),
        r_ref_mm=16.6667,
    )

    _print_field_comparison("cth14t_no_iron", cth_comparison)

    assert cth_comparison.relative_error < FIELD_TOLERANCE_REL


def test_live_roxie_field_parity_alpha_zero_single_block(tmp_path: Path) -> None:
    _require_live_roxie()

    alpha_zero_comparison = _alpha_zero_single_block_comparison(tmp_path)

    _print_field_comparison("alpha0_single_block_no_iron", alpha_zero_comparison)

    assert alpha_zero_comparison.relative_error < FIELD_TOLERANCE_REL


def test_live_roxie_field_parity_large_positive_alpha_multiturn_near_pole(tmp_path: Path) -> None:
    """Regression guard for the task 0029/0030 CTH campaign investigation.

    A near-pole block with a large positive ROXIE alpha and multiple turns was
    suspected of using an incorrect turn-stacking geometry (comparing
    against dipole_designer's simpler linear-step model, which turned out
    to NOT match ROXIE here). Directly validated against live ROXIE
    instead: DOT's existing Block.turns() stacking (_arc_stacked_anchor)
    matches real ROXIE conductor corners to ~0.2mm and bore field to
    <0.2% relative error even at alpha=75deg, confirming the geometry is
    correct and the near-pole self-overlap/pole-clearance failures seen at
    high turn counts are a genuine physical packing constraint, not a
    coordinate bug.
    """

    _require_live_roxie()

    pole_comparison = _large_positive_alpha_multiturn_comparison(tmp_path)

    _print_field_comparison("pole_alpha75_3turns_no_iron", pole_comparison)

    assert pole_comparison.relative_error < FIELD_TOLERANCE_REL


@pytest.mark.parametrize(
    ("inner_radius_mm", "phi_deg"),
    (
        (35.0, 40.0),
        (40.0, 30.0),
        (45.0, 50.0),
    ),
)
def test_live_roxie_field_parity_alpha_zero_single_turn_cases(
    tmp_path: Path,
    inner_radius_mm: float,
    phi_deg: float,
) -> None:
    _require_live_roxie()

    comparison = _alpha_zero_single_turn_comparison(
        tmp_path,
        inner_radius_mm=inner_radius_mm,
        phi_deg=phi_deg,
    )

    _print_field_comparison(
        f"alpha0_single_turn_r{inner_radius_mm:g}_phi{phi_deg:g}",
        comparison,
    )

    assert comparison.relative_error < FIELD_TOLERANCE_REL


def test_live_roxie_peak_field_and_margin_parity_cth_lf(tmp_path: Path) -> None:
    _require_live_roxie()

    comparisons = tuple(
        _cth_lf_peak_and_margin_comparison(tmp_path, case_name, design)
        for case_name, design in _cth_lf_margin_cases()
    )

    print("\n--- CTH_LF Peak Field and Margin Parity Results ---")
    for c in comparisons:
        print(f"CASE {c.case_name}:")
        print(f"  DOT Peak Field: {c.dot_peak_t:.6f} T, ROXIE Peak Field: {c.roxie_peak_t:.6f} T")
        print(f"  Peak Field Rel Error: {c.peak_relative_error * 100:.4f}%")
        print(f"  DOT Margin: {c.dot_margin_percent:.4f}%, ROXIE Margin: {c.roxie_margin_percent:.4f}%")
        print(f"  Margin Error pp: {c.margin_error_percentage_points:.4f}")
    print("--------------------------------------------------\n")

    assert len(comparisons) == 8
    assert any(sum(block.n_turns for layer in design.layers for block in layer.blocks) == 1 for _, design in _cth_lf_margin_cases())
    assert any(sum(block.n_turns for layer in design.layers for block in layer.blocks) > 1 for _, design in _cth_lf_margin_cases())
    assert any(len(design.layers) > 1 for _, design in _cth_lf_margin_cases())
    assert all(comparison.peak_relative_error < FIELD_TOLERANCE_REL for comparison in comparisons)
    assert all(
        comparison.margin_error_percentage_points < MARGIN_TOLERANCE_PERCENTAGE_POINTS
        for comparison in comparisons
    )


def test_live_roxie_peak_field_and_margin_parity_cth_hf_and_mixed(tmp_path: Path) -> None:
    _require_live_roxie()

    cases = (
        (
            "cth_hf_single_turn_r34_phi36",
            _cth_margin_design(((34.0, 36.0, 1, CTH_HF),)),
            ("CTH_HF",),
        ),
        (
            "cth_hf_lf_mixed_two_layer",
            _cth_margin_design(((33.0, 30.0, 1, CTH_HF), (55.0, 50.0, 1, CTH_LF))),
            ("CTH_HF", "CTH_LF"),
        ),
    )
    comparisons = tuple(
        _cth_peak_and_margin_comparison(tmp_path, case_name, design, conductor_names)
        for case_name, design, conductor_names in cases
    )

    print("\n--- CTH_HF and Mixed Peak Field and Margin Parity Results ---")
    for c in comparisons:
        print(f"CASE {c.case_name}:")
        print(f"  DOT Peak Field: {c.dot_peak_t:.6f} T, ROXIE Peak Field: {c.roxie_peak_t:.6f} T")
        print(f"  Peak Field Rel Error: {c.peak_relative_error * 100:.4f}%")
        print(f"  DOT Margin: {c.dot_margin_percent:.4f}%, ROXIE Margin: {c.roxie_margin_percent:.4f}%")
        print(f"  Margin Error pp: {c.margin_error_percentage_points:.4f}")
    print("------------------------------------------------------------\n")

    assert all(comparison.peak_relative_error < FIELD_TOLERANCE_REL for comparison in comparisons)
    assert all(
        comparison.margin_error_percentage_points < MARGIN_TOLERANCE_PERCENTAGE_POINTS
        for comparison in comparisons
    )


@pytest.mark.parametrize(
    ("fit_name", "remfit_row"),
    (
        (
            "MQXFS5",
            "  2 MQXFS5 11     1.6051E+11           30           16         0.96 "
            "        1.52          0.5            2            0            0            0 "
            "           0 'PIT 192 MQXFS5'",
        ),
        (
            "PIT192",
            "  2 PIT192 11     1.7834E+11           30           16         0.96 "
            "        1.52          0.5            2            0            0            0 "
            "           0 'PIT 192 REF'",
        ),
    ),
)
def test_live_roxie_margin_parity_for_non_cth_supported_type11_fits(
    tmp_path: Path,
    fit_name: str,
    remfit_row: str,
) -> None:
    """Exercise every supported non-CTH type-11 coefficient set in ROXIE.

    Each case makes a controlled copy of the already validated CTH_HF fixture
    and replaces only its HFM1 REMFIT row and filament link.  Cable, strand,
    insulation, geometry, current, and temperature therefore remain identical;
    only the critical-surface coefficients change in both engines.
    """

    _require_live_roxie()
    source = ROXIE_CADATA.read_text(encoding="utf-8", errors="replace")
    replacement_body = re.sub(r"^\s*\d+\s+", "", remfit_row)
    replacement, count = re.subn(
        r"(?m)^(\s*\d+\s+)HFM1\s+11\s+.*$",
        rf"\g<1>{replacement_body}",
        source,
    )
    assert count == 1, "expected one HFM1 REMFIT row in the validated fixture"
    replacement = re.sub(
        r"(?m)^(\s*\d+\s+QXF89H_HF\s+56\s+0\s+)HFM1\s+HFM1\b",
        rf"\g<1>{fit_name} {fit_name}",
        replacement,
    )
    catalogue_dir = tmp_path / f"{fit_name.lower()}_catalogue"
    catalogue_dir.mkdir()
    cadata_file = catalogue_dir / "cth14t.cadata"
    cadata_file.write_text(replacement, encoding="utf-8", newline="\n")

    resolution = resolve_conductor(
        cadata_file.read_text(encoding="utf-8", errors="replace"),
        "CTH_HF",
    )
    assert resolution.is_resolved, resolution.message
    assert resolution.remfit_name == fit_name
    cable = resolution.cable_spec()
    unit_design = _cth_margin_design(((34.0, 5.0, 20, cable),))

    comparison = _cth_peak_and_margin_comparison(
        tmp_path,
        f"{fit_name.lower()}_20turn_3t",
        unit_design,
        ("CTH_HF",),
        cadata_file=cadata_file,
        target_field_t=3.0,
        evaluate_dot_margin_on_roxie_peak=True,
    )

    print(f"\n--- {fit_name} non-CTH fit parity ---")
    print(
        f"DOT peak={comparison.dot_peak_t:.6f} T; "
        f"ROXIE peak={comparison.roxie_peak_t:.6f} T; "
        f"relative error={100.0 * comparison.peak_relative_error:.4f}%"
    )
    print(
        f"DOT margin={comparison.dot_margin_percent:.6f}%; "
        f"ROXIE margin={comparison.roxie_margin_percent:.6f}%; "
        f"error={comparison.margin_error_percentage_points:.4f} percentage points"
    )
    assert comparison.peak_relative_error < FIT_PARITY_FIELD_TOLERANCE_REL
    assert (
        comparison.margin_error_percentage_points
        < FIT_PARITY_MARGIN_TOLERANCE_PERCENTAGE_POINTS
    )


def test_cth14t_design_passes_corrected_pole_angle_limit() -> None:
    """The real CTH-14T design passes the legacy ROXIE phi edge limit."""

    result = check_feasibility(
        _cth14t_design(),
        aperture_radius_mm=16.6667,
        min_gap_mm=0.15,
        max_angle_deg=(80.0, 85.0, 85.0, 85.0),
    )

    assert not any(v.constraint_name == "pole_angle_limit" for v in result.violations), "\n".join(
        v.message for v in result.violations if v.constraint_name == "pole_angle_limit"
    )


def test_cth14t_design_passes_layer_nesting() -> None:
    """The real CTH-14T design (ROXIE-verified valid) must pass C10 nesting.

    dipole_designer's own test suite confirms this exact design passes its
    C10 check (test_cth14t_passes_corrected_side_edge_c10); this is the
    DOT-side equivalent, no live ROXIE call needed since layer nesting is a
    pure geometric check.
    """

    result = check_feasibility(
        _cth14t_design(),
        aperture_radius_mm=16.6667,
        min_gap_mm=0.15,
        max_angle_deg=90.0,
        enforce_layer_nesting=True,
    )

    assert not any(v.constraint_name == "layer_nesting" for v in result.violations), "\n".join(
        v.message for v in result.violations if v.constraint_name == "layer_nesting"
    )


def test_cth14t_design_with_pole_ward_outer_block_fails_layer_nesting() -> None:
    """A block moved too close to the pole must be caught by C10."""

    design = _cth14t_design()
    layers = list(design.layers)
    perturbed_blocks = list(layers[1].blocks)
    original = perturbed_blocks[0]
    perturbed_blocks[0] = Block(
        phi_deg=88.0,
        alpha_deg=original.alpha_deg,
        n_turns=original.n_turns,
        cable=original.cable,
        inner_radius_mm=original.inner_radius_mm,
        current_a=original.current_a,
    )
    layers[1] = Layer(inner_radius_mm=layers[1].inner_radius_mm, blocks=tuple(perturbed_blocks))
    perturbed_design = DipoleDesign(aperture_radius_mm=design.aperture_radius_mm, layers=tuple(layers))

    result = check_feasibility(
        perturbed_design,
        aperture_radius_mm=16.6667,
        min_gap_mm=0.15,
        max_angle_deg=90.0,
        enforce_layer_nesting=True,
    )

    assert any(v.constraint_name == "layer_nesting" for v in result.violations)


def _alpha_zero_single_block_comparison(tmp_path: Path) -> LiveComparison:
    unit_current_design = _alpha_zero_single_block_design(current_a=1.0)
    unit_field_t = _dot_field(unit_current_design)
    current_a = 5.0 / unit_field_t
    design = _alpha_zero_single_block_design(current_a=current_a)
    record = RoxieBlockRecord(
        number=1,
        n_turns=6,
        radius_mm=30.0,
        phi_roxie_deg=45.0,
        alpha_roxie_deg=0.0,
        current_a=current_a,
        conductor_name="CTH_HF",
        n2=20,
    )
    return _compare_with_roxie(
        tmp_path,
        case_name="alpha0_single_block_no_iron",
        design=design,
        block_records=(record,),
        r_ref_mm=25.0,
    )


def _large_positive_alpha_multiturn_comparison(tmp_path: Path) -> LiveComparison:
    phi_deg = 75.0
    alpha_deg = 75.0
    n_turns = 3
    radius_mm = 30.0

    def build(current_a: float) -> DipoleDesign:
        block = Block(
            phi_deg=phi_deg,
            alpha_deg=alpha_deg,
            n_turns=n_turns,
            cable=CTH_HF,
            inner_radius_mm=radius_mm,
            current_a=current_a,
        )
        return DipoleDesign(aperture_radius_mm=25.0, layers=(Layer(inner_radius_mm=radius_mm, blocks=(block,)),))

    unit_current_design = build(current_a=1.0)
    unit_field_t = _dot_field(unit_current_design)
    current_a = 5.0 / unit_field_t
    design = build(current_a=current_a)
    record = RoxieBlockRecord(
        number=1,
        n_turns=n_turns,
        radius_mm=radius_mm,
        phi_roxie_deg=phi_deg,
        alpha_roxie_deg=alpha_deg,
        current_a=current_a,
        conductor_name="CTH_HF",
        n2=20,
    )
    return _compare_with_roxie(
        tmp_path,
        case_name="pole_alpha75_3turns_no_iron",
        design=design,
        block_records=(record,),
        r_ref_mm=25.0,
    )


def _alpha_zero_single_turn_comparison(
    tmp_path: Path,
    *,
    inner_radius_mm: float,
    phi_deg: float,
) -> LiveComparison:
    unit_current_design = _alpha_zero_single_turn_design(
        current_a=1.0,
        inner_radius_mm=inner_radius_mm,
        phi_deg=phi_deg,
    )
    unit_field_t = _dot_field(unit_current_design)
    current_a = 5.0 / unit_field_t
    design = _alpha_zero_single_turn_design(
        current_a=current_a,
        inner_radius_mm=inner_radius_mm,
        phi_deg=phi_deg,
    )
    record = RoxieBlockRecord(
        number=1,
        n_turns=1,
        radius_mm=inner_radius_mm,
        phi_roxie_deg=phi_deg,
        alpha_roxie_deg=0.0,
        current_a=current_a,
        conductor_name="CTH_HF",
        n2=20,
    )
    return _compare_with_roxie(
        tmp_path,
        case_name=f"alpha0_single_turn_r{inner_radius_mm:g}_phi{phi_deg:g}_no_iron",
        design=design,
        block_records=(record,),
        r_ref_mm=25.0,
    )


def _alpha_zero_single_turn_design(
    *,
    current_a: float,
    inner_radius_mm: float,
    phi_deg: float,
) -> DipoleDesign:
    block = Block(
        phi_deg=phi_deg,
        alpha_deg=0.0,
        n_turns=1,
        cable=CTH_HF,
        inner_radius_mm=inner_radius_mm,
        current_a=current_a,
    )
    return DipoleDesign(aperture_radius_mm=25.0, layers=(Layer(inner_radius_mm=inner_radius_mm, blocks=(block,)),))


def _cth_lf_margin_cases() -> tuple[tuple[str, DipoleDesign], ...]:
    return (
        ("cth_lf_single_turn_diag_a", _cth_lf_design(((36.539, 27.667, 1),))),
        ("cth_lf_two_layer_diag_b", _cth_lf_design(((38.657, 41.683, 1), (59.041, 46.598, 1)))),
        ("cth_lf_single_turn_r34_phi36", _cth_lf_design(((34.0, 36.0, 1),))),
        ("cth_lf_custom_two_turns_block", _cth_lf_design(((35.0, 35.0, 2),))),
        ("cth_lf_three_turn_r42_phi48", _cth_lf_design(((42.0, 48.0, 3),))),
        ("cth_lf_custom_four_turns_r50_phi40", _cth_lf_design(((50.0, 40.0, 4),))),
        ("cth_lf_two_layer_single_turns", _cth_lf_design(((33.0, 30.0, 1), (55.0, 50.0, 1)))),
        ("cth_lf_three_layer_single_turns", _cth_lf_design(((32.0, 42.0, 1), (53.0, 38.0, 1), (74.0, 48.0, 1)))),
    )


def _cth_lf_design(records: tuple[tuple[float, float, int], ...], current_a: float = 1.0) -> DipoleDesign:
    return _cth_margin_design(
        tuple((radius_mm, phi_deg, n_turns, CTH_LF) for radius_mm, phi_deg, n_turns in records),
        current_a=current_a,
    )


def _cth_margin_design(
    records: tuple[tuple[float, float, int, CableSpec], ...],
    current_a: float = 1.0,
) -> DipoleDesign:
    return DipoleDesign(
        aperture_radius_mm=25.0,
        layers=tuple(
            Layer(
                inner_radius_mm=radius_mm,
                blocks=(
                    Block(
                        phi_deg=phi_deg,
                        alpha_deg=0.0,
                        n_turns=n_turns,
                        cable=cable,
                        inner_radius_mm=radius_mm,
                        current_a=current_a,
                    ),
                ),
            )
            for radius_mm, phi_deg, n_turns, cable in records
        ),
    )


def _alpha_zero_single_block_design(*, current_a: float) -> DipoleDesign:
    block = Block(
        phi_deg=45.0,
        alpha_deg=0.0,
        n_turns=6,
        cable=CTH_HF,
        inner_radius_mm=30.0,
        current_a=current_a,
    )
    return DipoleDesign(aperture_radius_mm=25.0, layers=(Layer(inner_radius_mm=30.0, blocks=(block,)),))


def _compare_with_roxie(
    tmp_path: Path,
    *,
    case_name: str,
    design: DipoleDesign,
    block_records: tuple[RoxieBlockRecord, ...],
    r_ref_mm: float,
) -> LiveComparison:
    data_file = _write_no_iron_data_file(tmp_path, case_name, block_records, r_ref_mm)
    output_dir = tmp_path / f"{case_name}_output"
    output_dir.mkdir()
    roxie_field_t = _run_roxie_main_field(data_file, output_dir)
    dot_field_t = _dot_field(design)
    relative_error = abs(dot_field_t - roxie_field_t) / abs(roxie_field_t)
    return LiveComparison(
        dot_field_t=dot_field_t,
        roxie_field_t=roxie_field_t,
        relative_error=relative_error,
    )


def _cth_lf_peak_and_margin_comparison(
    tmp_path: Path,
    case_name: str,
    unit_current_design: DipoleDesign,
) -> LiveMarginComparison:
    return _cth_peak_and_margin_comparison(
        tmp_path,
        case_name,
        unit_current_design,
        tuple("CTH_LF" for _ in unit_current_design.layers),
    )


def _cth_peak_and_margin_comparison(
    tmp_path: Path,
    case_name: str,
    unit_current_design: DipoleDesign,
    conductor_names_by_layer: tuple[str, ...],
    *,
    cadata_file: Path = ROXIE_CADATA,
    target_field_t: float = 1.0,
    evaluate_dot_margin_on_roxie_peak: bool = False,
) -> LiveMarginComparison:
    solved = operating_point(unit_current_design, target_field_t)
    records = tuple(
        _cth_margin_block_record(number, block, conductor_names_by_layer[layer_index])
        for number, (layer_index, block) in enumerate(_all_indexed_blocks(solved.design), start=1)
    )
    data_file = _write_no_iron_data_file(
        tmp_path,
        case_name,
        records,
        r_ref_mm=25.0,
        cadata_file=cadata_file,
    )
    output_dir = tmp_path / f"{case_name}_output"
    output_dir.mkdir()
    output_file = _run_roxie_output(data_file, output_dir, cadata_file=cadata_file)
    roxie_peak_t, roxie_loadline_percent = _parse_peak_and_loadline(output_file)
    roxie_margin_percent = 100.0 - roxie_loadline_percent

    cadata_text = cadata_file.read_text(encoding="utf-8", errors="replace")
    conductors = tuple(resolve_conductor(cadata_text, conductor_name) for conductor_name in conductor_names_by_layer)
    for conductor_name, conductor in zip(conductor_names_by_layer, conductors, strict=True):
        if not conductor.is_resolved:
            pytest.fail(f"{conductor_name} conductor did not resolve: {conductor.status} {conductor.message}")
    cadata_by_layer = tuple(
        LayerConductorData(
            strand=conductor.strand,
            cable=conductor.cable,
            remfit=conductor.remfit,
        )
        for conductor in conductors
    )
    if evaluate_dot_margin_on_roxie_peak:
        if len(conductors) != 1:
            raise ValueError("fit-only parity requires exactly one conductor")
        conductor = conductors[0]
        operating_current_a = abs(solved.design.layers[0].blocks[0].current_a)
        short_sample_current_a = solve_short_sample_current(
            conductor.remfit,
            conductor.strand,
            conductor.cable,
            temperature_k=conductor.temperature_k,
            k_field_per_current=roxie_peak_t / operating_current_a,
        )
        dot_margin_percent = load_line_margin_percent(
            operating_current_a,
            short_sample_current_a,
        )
    else:
        dot_margin_percent = load_line_margin_objective(
            solved.design,
            cable_specs_by_layer=tuple(layer.blocks[0].cable for layer in solved.design.layers),
            cadata_by_layer=cadata_by_layer,
            temperature_k=conductors[0].temperature_k,
        )
    _, dot_peak_t = _peak_field_on_own_turns(solved.design, evaluated_layers=tuple(range(len(solved.design.layers))))
    return LiveMarginComparison(
        case_name=case_name,
        dot_peak_t=dot_peak_t,
        roxie_peak_t=roxie_peak_t,
        peak_relative_error=abs(dot_peak_t - roxie_peak_t) / abs(roxie_peak_t),
        dot_margin_percent=dot_margin_percent,
        roxie_margin_percent=roxie_margin_percent,
        margin_error_percentage_points=abs(dot_margin_percent - roxie_margin_percent),
    )


def _all_blocks(design: DipoleDesign) -> tuple[Block, ...]:
    return tuple(block for layer in design.layers for block in layer.blocks)


def _all_indexed_blocks(design: DipoleDesign) -> tuple[tuple[int, Block], ...]:
    return tuple(
        (layer_index, block)
        for layer_index, layer in enumerate(design.layers)
        for block in layer.blocks
    )


def _cth_margin_block_record(number: int, block: Block, conductor_name: str) -> RoxieBlockRecord:
    return RoxieBlockRecord(
        number=number,
        n_turns=block.n_turns,
        radius_mm=block.inner_radius_mm,
        phi_roxie_deg=block.phi_deg,
        alpha_roxie_deg=block.alpha_deg,
        current_a=block.current_a,
        conductor_name=conductor_name,
        n2=20 if conductor_name == "CTH_HF" else 15,
    )


def _cth_block_records() -> tuple[RoxieBlockRecord, ...]:
    return tuple(
        RoxieBlockRecord(
            number=number,
            n_turns=n_turns,
            radius_mm=radius_mm,
            phi_roxie_deg=phi_roxie_deg,
            alpha_roxie_deg=alpha_roxie_deg,
            current_a=CURRENT_A,
            conductor_name="CTH_HF" if cable == CTH_HF else "CTH_LF",
            n2=n2,
        )
        for number, n_turns, radius_mm, phi_roxie_deg, alpha_roxie_deg, cable, n2 in BLOCK_TABLE
    )


def _cth14t_design() -> DipoleDesign:
    layers: list[Layer] = []
    for radius_mm in (25.0, 44.153, 63.306, 80.269):
        blocks = tuple(_cth_block(record) for record in BLOCK_TABLE if record[2] == radius_mm)
        layers.append(Layer(inner_radius_mm=radius_mm, blocks=blocks))
    return DipoleDesign(aperture_radius_mm=16.6667, layers=tuple(layers))


def _cth_block(record: tuple[int, int, float, float, float, CableSpec, int]) -> Block:
    _, n_turns, radius_mm, phi_roxie_deg, alpha_roxie_deg, cable, _ = record
    return Block(
        phi_deg=phi_roxie_deg,
        alpha_deg=alpha_roxie_deg,
        n_turns=n_turns,
        cable=cable,
        inner_radius_mm=radius_mm,
        current_a=CURRENT_A,
    )


def _dot_field(design: DipoleDesign) -> float:
    sources = tuple(
        source
        for layer in design.layers
        for block in layer.blocks
        for turn in block.turns()
        for source in place_line_current_sources(turn, n1=2, n2=_n2_for_block_or_default(block))
    )
    bx_t, by_t = field_at(sources, 0.0, 0.0)
    return math.hypot(bx_t, by_t)


def _print_field_comparison(case_name: str, comparison: LiveComparison) -> None:
    print(
        f"ROXIE parity {case_name}: DOT={comparison.dot_field_t:.8f} T, "
        f"ROXIE={comparison.roxie_field_t:.8f} T, "
        f"relative error={100.0 * comparison.relative_error:.5f}%"
    )


def _n2_for_block_or_default(block: Block) -> int:
    try:
        return _n2_for_block(block)
    except AssertionError:
        return 20


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


def _write_no_iron_data_file(
    tmp_path: Path,
    case_name: str,
    block_records: tuple[RoxieBlockRecord, ...],
    r_ref_mm: float,
    *,
    cadata_file: Path = ROXIE_CADATA,
) -> Path:
    template = ROXIE_TEMPLATE
    if template is None:
        pytest.skip("ROXIE template is unavailable; set DOT_ROXIE_TEMPLATE")
    if not template.exists():
        pytest.skip(f"ROXIE template is unavailable: {template}")
    if not cadata_file.exists():
        pytest.skip(f"ROXIE cable data is unavailable: {cadata_file}")

    lines = template.read_text(encoding="utf-8").splitlines()
    lines[2] = _quoted_roxie_path("none")
    lines[3] = _quoted_roxie_path(cadata_file.name)
    lines[4] = _quoted_roxie_path("none")
    lines = [
        line.replace("LBEMFEM=T", "LBEMFEM=F").replace("LIRON=T", "LIRON=F")
        for line in lines
    ]
    _replace_block_section(lines, block_records)
    _replace_layer_section(lines, len(block_records))
    _replace_harmonic_reference_radius(lines, r_ref_mm)

    data_file = tmp_path / f"{case_name}.data"
    data_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return data_file


def _replace_block_section(lines: list[str], block_records: tuple[RoxieBlockRecord, ...]) -> None:
    block_index = next(index for index, line in enumerate(lines) if line.startswith("BLOCK "))
    header_index = next(
        index
        for index in range(block_index + 1, len(lines))
        if lines[index].lstrip().startswith("no  type")
    )
    replacement = [f"BLOCK {len(block_records)}"]
    replacement.extend(_format_block_line(record) for record in block_records)
    lines[block_index:header_index] = replacement


def _replace_layer_section(lines: list[str], block_count: int) -> None:
    layer_index = next(index for index, line in enumerate(lines) if line.startswith("LAYER "))
    header_index = next(
        index
        for index in range(layer_index + 1, len(lines))
        if lines[index].lstrip().startswith("no  symm")
    )
    block_numbers = " ".join(str(index) for index in range(1, block_count + 1))
    lines[layer_index:header_index] = ["LAYER 1", f"      1     2     1 {block_numbers} /"]


def _replace_harmonic_reference_radius(lines: list[str], r_ref_mm: float) -> None:
    harmonic_index = next(index for index, line in enumerate(lines) if line.startswith("HARMONICTABLE "))
    lines[harmonic_index + 1] = (
        f"      1     1            0            0            0            0"
        f"      {r_ref_mm:g}        2                      0 "
    )


def _format_block_line(record: RoxieBlockRecord) -> str:
    return (
        f"  {record.number:3d}  {1:3d}  {record.n_turns:3d}  {record.radius_mm:10.5g}  "
        f"{record.phi_roxie_deg:10.6g}  {record.alpha_roxie_deg:10.6g}  "
        f"{record.current_a:10.6g}  {record.conductor_name:>10s}  "
        f"{2:2d}  {record.n2:2d}  {0:2d}  {0:11d} "
    )


def _quoted_roxie_path(value: str) -> str:
    return f"'{value.ljust(83)}'"


def _run_roxie_main_field(data_file: Path, output_dir: Path) -> float:
    return _parse_main_field(_run_roxie_output(data_file, output_dir))


def _run_roxie_output(
    data_file: Path,
    output_dir: Path,
    *,
    cadata_file: Path = ROXIE_CADATA,
) -> Path:
    model_name = data_file.stem
    encoded_model_name = urllib.parse.quote(model_name, safe="")
    initialized = _roxie_json_request(f"/model/{encoded_model_name}", data=b"")
    timestamp = str(initialized["timestamp"])
    body, content_type = _multipart_form_data(
        fields={"model_name": model_name, "timestamp": timestamp},
        files=(data_file, cadata_file),
    )
    _roxie_json_request(
        "/model/",
        data=body,
        headers={"Content-Type": content_type},
    )
    result = _roxie_json_request(
        f"/model/{encoded_model_name}/{urllib.parse.quote(timestamp, safe='')}/run",
        data=b"",
    )
    if not bool(result.get("status")):
        pytest.fail(f"ROXIE REST run failed for {model_name}: {result.get('output', result)}")
    artefacts = tuple(str(name) for name in result.get("artefacts", ()))
    output_name = next((name for name in artefacts if name.endswith(".output")), None)
    if output_name is None:
        listing = _roxie_json_request(
            f"/artefacts/{encoded_model_name}/{urllib.parse.quote(timestamp, safe='')}"
        )
        output_name = next(
            (str(name) for name in listing.get("artefacts", ()) if str(name).endswith(".output")),
            None,
        )
    if output_name is None:
        pytest.fail(f"ROXIE REST run did not produce a .output artefact: {artefacts}")
    url = (
        f"{ROXIE_SERVICE_URL.rstrip('/')}/artefact/{encoded_model_name}/"
        f"{urllib.parse.quote(timestamp, safe='')}/{urllib.parse.quote(output_name, safe='')}"
    )
    try:
        with urllib.request.urlopen(url, timeout=120.0) as response:  # noqa: S310
            content = response.read()
    except (OSError, urllib.error.URLError) as exc:
        pytest.fail(f"could not download ROXIE output artefact: {exc}")
    destination = output_dir / output_name
    destination.write_bytes(content)
    return destination


def _roxie_json_request(
    endpoint: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    request = urllib.request.Request(
        f"{ROXIE_SERVICE_URL.rstrip('/')}{endpoint}",
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=120.0) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        pytest.fail(f"ROXIE REST request failed for {endpoint}: HTTP {exc.code}: {details}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        pytest.fail(f"ROXIE REST request failed for {endpoint}: {exc}")


def _multipart_form_data(
    *,
    fields: dict[str, str],
    files: tuple[Path, ...],
) -> tuple[bytes, str]:
    boundary = f"dot-parity-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            )
        )
    for path in files:
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="files"; '
                    f'filename="{path.name}"\r\n'
                ).encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                path.read_bytes(),
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _parse_main_field(output_file: Path) -> float:
    text = output_file.read_text(encoding="utf-8", errors="replace")
    number_pattern = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
    match = re.search(rf"MAIN FIELD\s*\(T\)\s*\.{{10,}}\s*{number_pattern}", text)
    if not match:
        pytest.fail(f"could not parse MAIN FIELD from {output_file}")
    return abs(float(match.group(1)))


def _parse_peak_and_loadline(output_file: Path) -> tuple[float, float]:
    text = output_file.read_text(encoding="utf-8", errors="replace")
    number_pattern = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
    peaks = [
        abs(float(match.group(1)))
        for match in re.finditer(rf"PEAK FIELD IN CONDUCTOR\s+\d+\s*\(T\)\s*\.{{10,}}\s*{number_pattern}", text)
    ]
    loadlines = [
        float(match.group(1))
        for match in re.finditer(rf"PERCENTAGE ON THE LOAD LINE\s*\.{{10,}}\s*{number_pattern}", text)
    ]
    if not peaks:
        pytest.fail(f"could not parse PEAK FIELD IN CONDUCTOR from {output_file}")
    if not loadlines:
        pytest.fail(f"could not parse PERCENTAGE ON THE LOAD LINE from {output_file}")
    return max(peaks), max(loadlines)


def _require_live_roxie() -> None:
    try:
        with urllib.request.urlopen(ROXIE_SERVICE_URL, timeout=1.0) as response:  # noqa: S310
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        pytest.skip(f"ROXIE REST service is unreachable at {ROXIE_SERVICE_URL}: {exc}")
