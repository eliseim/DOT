from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.physics import field_at, place_line_current_sources

ROXIE_SERVICE_URL = os.environ.get("ROXIE_SERVICE_URL", "http://127.0.0.1:8080")
ROXIE_TEMPLATE = Path("C:/Users/elisei/Desktop/dipole_designer/10042026_CTH-14T.data")
ROXIE_CADATA = Path("C:/Users/elisei/Desktop/dipole_designer/roxie_CTH_cables.cadata")
FIELD_TOLERANCE_REL = 0.02

CURRENT_A = 12238.0
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


def test_live_roxie_field_parity_cth14t(tmp_path: Path) -> None:
    _require_live_roxie()

    cth_comparison = _compare_with_roxie(
        tmp_path,
        case_name="cth14t_no_iron",
        design=_cth14t_design(),
        block_records=_cth_block_records(),
        r_ref_mm=16.6667,
    )

    assert cth_comparison.relative_error < FIELD_TOLERANCE_REL


def test_live_roxie_field_parity_alpha_zero_single_block(tmp_path: Path) -> None:
    _require_live_roxie()

    alpha_zero_comparison = _alpha_zero_single_block_comparison(tmp_path)

    assert alpha_zero_comparison.relative_error < FIELD_TOLERANCE_REL


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
        phi_deg=90.0 - phi_roxie_deg,
        alpha_deg=-alpha_roxie_deg,
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
            and block.phi_deg == 90.0 - phi_roxie_deg
            and block.alpha_deg == -alpha_roxie_deg
            and block.cable == cable
        ):
            return n2
    raise AssertionError("unexpected CTH-14T block")


def _write_no_iron_data_file(
    tmp_path: Path,
    case_name: str,
    block_records: tuple[RoxieBlockRecord, ...],
    r_ref_mm: float,
) -> Path:
    if not ROXIE_TEMPLATE.exists():
        pytest.skip(f"ROXIE template is unavailable: {ROXIE_TEMPLATE}")
    if not ROXIE_CADATA.exists():
        pytest.skip(f"ROXIE cable data is unavailable: {ROXIE_CADATA}")

    lines = ROXIE_TEMPLATE.read_text(encoding="utf-8").splitlines()
    lines[2] = _quoted_roxie_path("none")
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
    try:
        from roxieapi.tool_adapter.RoxieToolAdapter import RestRoxieToolAdapter
    except Exception as exc:
        pytest.skip(f"roxieapi REST adapter is unavailable: {exc}")

    adapter = RestRoxieToolAdapter(
        service_url=ROXIE_SERVICE_URL,
        input_files=[data_file, ROXIE_CADATA],
        session=_TimeoutSession(),
    )
    return_code = adapter.run()
    if return_code != 0:
        pytest.fail(f"ROXIE REST run failed with return code {return_code}\n{adapter.errors}")
    adapter.download_artefacts(output_dir, "*.output")
    output_files = tuple(output_dir.glob("*.output"))
    if not output_files:
        pytest.fail("ROXIE REST run did not produce a .output artefact")
    return _parse_main_field(output_files[0])


def _parse_main_field(output_file: Path) -> float:
    text = output_file.read_text(encoding="utf-8", errors="replace")
    number_pattern = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)"
    match = re.search(rf"MAIN FIELD\s*\(T\)\s*\.{{10,}}\s*{number_pattern}", text)
    if not match:
        pytest.fail(f"could not parse MAIN FIELD from {output_file}")
    return abs(float(match.group(1)))


def _require_live_roxie() -> None:
    requests = pytest.importorskip("requests", reason="requests is needed for ROXIE REST probing")
    try:
        response = requests.get(ROXIE_SERVICE_URL, timeout=1.0)
        response.raise_for_status()
    except Exception as exc:
        pytest.skip(f"ROXIE REST service is unreachable at {ROXIE_SERVICE_URL}: {exc}")


class _TimeoutSession:
    def __init__(self) -> None:
        requests = pytest.importorskip("requests", reason="requests is needed for ROXIE REST")
        self._session = requests.Session()

    def get(self, *args: object, **kwargs: object) -> object:
        kwargs.setdefault("timeout", 120.0)
        return self._session.get(*args, **kwargs)

    def post(self, *args: object, **kwargs: object) -> object:
        kwargs.setdefault("timeout", 120.0)
        return self._session.post(*args, **kwargs)
