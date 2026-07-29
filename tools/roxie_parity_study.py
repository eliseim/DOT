"""Run a deterministic DOT-versus-ROXIE no-iron parity study.

The script generates physically non-overlapping one-quadrant dipole layouts,
runs the same layouts through DOT and a local ROXIE REST service, and reports
deviations in bore field, conductor peak field, load-line margin, and normal
harmonics. It is intentionally separate from the optimizer: this validates the
forward physics engine, not NSGA-II convergence.

ROXIE is commercial software and is not distributed with DOT. The caller must
provide a valid no-iron ROXIE ``.data`` template and a reachable REST service.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dot import __version__
from dot.conductors import resolve_conductor
from dot.geometry import Block, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize.objectives import (
    CERTIFICATION_FIDELITY,
    LayerConductorData,
    load_line_margin_detail,
)
from dot.physics import field_at, multipole_coefficients, place_line_current_sources

DEFAULT_SEED = 20260729
HARMONIC_ORDERS = (3, 5, 7, 9, 11)
CONDUCTOR_N2 = {
    "CTH_HF": 20,
    "CTH_LF": 15,
    "YELLONIN": 20,
    "YELLONOU": 20,
}
TWO_LAYER_PATTERNS = (
    ("YELLONIN", "YELLONOU"),
    ("CTH_HF", "CTH_HF"),
    ("CTH_HF", "CTH_LF"),
    ("CTH_LF", "CTH_LF"),
)
FOUR_LAYER_PATTERNS = (
    ("CTH_HF", "CTH_HF", "CTH_LF", "CTH_LF"),
    ("YELLONIN", "YELLONIN", "YELLONOU", "YELLONOU"),
    ("CTH_HF", "CTH_HF", "CTH_HF", "CTH_HF"),
    ("CTH_HF", "CTH_HF", "YELLONIN", "YELLONOU"),
)


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    topology_layers: int
    aperture_radius_mm: float
    reference_radius_mm: float
    current_a: float
    conductor_names: tuple[str, ...]
    design: DipoleDesign


@dataclass(frozen=True, slots=True)
class BlockRecord:
    number: int
    n_turns: int
    radius_mm: float
    phi_deg: float
    alpha_deg: float
    current_a: float
    conductor_name: str
    n2: int


def main() -> None:
    args = _arguments()
    _require_service(args.service_url)
    template = args.template.resolve()
    cadata = args.cadata.resolve()
    if not template.is_file():
        raise SystemExit(f"ROXIE template does not exist: {template}")
    if not cadata.is_file():
        raise SystemExit(f"cadata file does not exist: {cadata}")

    cases = _generate_cases(
        args.cases_per_topology,
        cadata,
        seed=args.seed,
    )
    expected = 2 * args.cases_per_topology
    if len(cases) != expected:
        raise RuntimeError(f"generated {len(cases)} cases instead of {expected}")

    checkpoint = args.checkpoint.resolve()
    completed = _load_checkpoint(checkpoint)
    pending = tuple(case for case in cases if case.case_id not in completed)
    print(
        f"Parity campaign: {expected} cases "
        f"({args.cases_per_topology} two-layer + "
        f"{args.cases_per_topology} four-layer), "
        f"{len(completed)} resumed, {len(pending)} pending."
    )

    lock = threading.Lock()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _evaluate_case,
                case,
                template,
                cadata,
                args.service_url,
            ): case
            for case in pending
        }
        for done_count, future in enumerate(as_completed(futures), start=1):
            case = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                raise RuntimeError(f"parity case {case.case_id} failed") from exc
            completed[case.case_id] = result
            with lock:
                _append_checkpoint(checkpoint, result)
            elapsed = time.perf_counter() - started
            rate = done_count / elapsed if elapsed else 0.0
            remaining = len(pending) - done_count
            eta_s = remaining / rate if rate else math.inf
            if (
                done_count == 1
                or done_count % args.progress_every == 0
                or done_count == len(pending)
            ):
                print(
                    f"{len(completed)}/{expected} {case.case_id} "
                    f"elapsed={_duration(elapsed)} ETA={_duration(eta_s)}",
                    flush=True,
                )

    if len(completed) != expected:
        missing = sorted(case.case_id for case in cases if case.case_id not in completed)
        raise RuntimeError(f"parity study incomplete; missing {len(missing)} cases")

    ordered = [completed[case.case_id] for case in cases]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_csv, ordered)
    summary = _summary(
        ordered,
        args.seed,
        args.cases_per_topology,
        template,
        cadata,
        args.service_url,
    )
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Saved case table: {args.output_csv.resolve()}")
    print(f"Saved summary: {args.output_summary.resolve()}")


def _arguments() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument(
        "--cadata",
        type=Path,
        default=root / "campaign" / "dot_cables.cadata",
    )
    parser.add_argument(
        "--service-url",
        default="http://127.0.0.1:8080",
    )
    parser.add_argument("--cases-per-topology", type=int, default=500)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("roxie_parity_checkpoint.jsonl"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("roxie_parity_1000_results.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("roxie_parity_1000_summary.json"),
    )
    args = parser.parse_args()
    if args.cases_per_topology < 1:
        parser.error("--cases-per-topology must be positive")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    return args


def _generate_cases(
    cases_per_topology: int,
    cadata_path: Path,
    *,
    seed: int,
) -> tuple[Case, ...]:
    text = cadata_path.read_text(encoding="utf-8", errors="replace")
    resolved = {
        name: resolve_conductor(text, name)
        for name in sorted({name for pattern in TWO_LAYER_PATTERNS + FOUR_LAYER_PATTERNS for name in pattern})
    }
    for name, record in resolved.items():
        if not record.is_resolved:
            raise ValueError(f"unsupported parity conductor {name!r}: {record.message}")

    cases: list[Case] = []
    for layer_count, patterns in (
        (2, TWO_LAYER_PATTERNS),
        (4, FOUR_LAYER_PATTERNS),
    ):
        for index in range(cases_per_topology):
            rng = random.Random(seed + layer_count * 10_000_019 + index * 104_729)
            names = patterns[index % len(patterns)]
            cases.append(
                _generate_case(
                    layer_count,
                    index,
                    names,
                    resolved,
                    rng,
                )
            )
    return tuple(cases)


def _generate_case(
    layer_count: int,
    index: int,
    conductor_names: tuple[str, ...],
    resolved: dict[str, Any],
    rng: random.Random,
) -> Case:
    for _attempt in range(500):
        aperture = rng.uniform(20.0, 40.0)
        reference = round((2.0 / 3.0) * aperture, 3)
        if all(name == "CTH_HF" for name in conductor_names):
            current = rng.uniform(5_000.0, 12_500.0)
        elif all(name in {"YELLONIN", "YELLONOU", "CTH_LF"} for name in conductor_names):
            current = rng.uniform(3_000.0, 8_000.0)
        else:
            current = rng.uniform(4_000.0, 9_500.0)

        layers: list[Layer] = []
        radius = aperture + rng.uniform(0.25, 0.8)
        valid = True
        for layer_index, name in enumerate(conductor_names):
            cable = resolved[name].cable_spec()
            layer = _generate_layer(radius, cable, current, rng)
            if layer is None:
                valid = False
                break
            layers.append(layer)
            outer_radius = max(
                math.hypot(*point)
                for block in layer.blocks
                for turn in block.turns()
                for point in turn.corners
            )
            radius = outer_radius + rng.uniform(0.5, 2.0)
        if not valid:
            continue

        design = DipoleDesign(aperture_radius_mm=aperture, layers=tuple(layers))
        feasibility = check_feasibility(
            design,
            aperture_radius_mm=aperture,
            min_gap_mm=0.0,
            min_layer_clearance_mm=0.25,
            min_inter_block_gap_mm=0.1,
            geometry_tolerance_mm=0.001,
        )
        if not feasibility.is_feasible:
            continue
        case_id = f"{layer_count}L-{index:04d}"
        return Case(
            case_id=case_id,
            topology_layers=layer_count,
            aperture_radius_mm=aperture,
            reference_radius_mm=reference,
            current_a=current,
            conductor_names=conductor_names,
            design=design,
        )
    raise RuntimeError(
        f"could not generate a feasible {layer_count}-layer parity case at index {index}"
    )


def _generate_layer(
    radius_mm: float,
    cable: Any,
    current_a: float,
    rng: random.Random,
) -> Layer | None:
    gap_mm = rng.uniform(0.1, 0.6)
    first_phi = math.degrees(math.atan2(gap_mm, radius_mm))
    blocks = [
        Block(
            phi_deg=first_phi,
            alpha_deg=0.0,
            n_turns=rng.randint(2, 6),
            cable=cable,
            inner_radius_mm=radius_mm,
            current_a=current_a,
        )
    ]
    requested_blocks = rng.randint(1, 3)
    for _ in range(1, requested_blocks):
        previous_edge = max(
            math.degrees(math.atan2(point[1], point[0]))
            for block in blocks
            for turn in block.turns()
            for point in turn.corners
        )
        phi = previous_edge + rng.uniform(3.0, 9.0)
        if phi >= 80.0:
            break
        alpha = min(max(phi + rng.uniform(-7.0, 7.0), 0.0), 78.0)
        candidate = Block(
            phi_deg=phi,
            alpha_deg=alpha,
            n_turns=rng.randint(1, 4),
            cable=cable,
            inner_radius_mm=radius_mm,
            current_a=current_a,
        )
        maximum_edge = max(
            math.degrees(math.atan2(point[1], point[0]))
            for turn in candidate.turns()
            for point in turn.corners
        )
        if maximum_edge >= 88.0:
            break
        blocks.append(candidate)
    return Layer(inner_radius_mm=radius_mm, blocks=tuple(blocks))


def _evaluate_case(
    case: Case,
    template_path: Path,
    cadata_path: Path,
    service_url: str,
) -> dict[str, Any]:
    block_records = _block_records(case)
    with tempfile.TemporaryDirectory(prefix=f"dot-parity-{case.case_id}-") as raw:
        directory = Path(raw)
        data_file = _write_data_file(
            template_path,
            directory,
            case,
            block_records,
            cadata_path.name,
        )
        output = _run_roxie(
            data_file,
            cadata_path,
            directory,
            service_url,
        )
        roxie = _parse_roxie_output(output)
    dot = _dot_metrics(case, cadata_path)

    result: dict[str, Any] = {
        "case_id": case.case_id,
        "topology_layers": case.topology_layers,
        "aperture_radius_mm": case.aperture_radius_mm,
        "reference_radius_mm": case.reference_radius_mm,
        "current_a": case.current_a,
        "conductors": "|".join(case.conductor_names),
        "total_blocks": sum(len(layer.blocks) for layer in case.design.layers),
        "total_turns": sum(
            block.n_turns for layer in case.design.layers for block in layer.blocks
        ),
        "dot_bore_field_t": dot["bore_field_t"],
        "roxie_bore_field_t": roxie["bore_field_t"],
        "dot_peak_field_t": dot["peak_field_t"],
        "roxie_peak_field_t": roxie["peak_field_t"],
        "dot_margin_percent": dot["margin_percent"],
        "roxie_margin_percent": roxie["margin_percent"],
    }
    result["bore_error_percent"] = (
        100.0
        * (result["dot_bore_field_t"] - result["roxie_bore_field_t"])
        / abs(result["roxie_bore_field_t"])
    )
    result["peak_error_percent"] = (
        100.0
        * (result["dot_peak_field_t"] - result["roxie_peak_field_t"])
        / abs(result["roxie_peak_field_t"])
    )
    result["margin_error_pp"] = (
        result["dot_margin_percent"] - result["roxie_margin_percent"]
    )
    for order in HARMONIC_ORDERS:
        result[f"dot_b{order}_units"] = dot["harmonics"][order]
        result[f"roxie_b{order}_units"] = roxie["harmonics"][order]
        result[f"b{order}_error_units"] = (
            dot["harmonics"][order] - roxie["harmonics"][order]
        )
    return result


def _dot_metrics(case: Case, cadata_path: Path) -> dict[str, Any]:
    sources = tuple(
        source
        for turn in case.design.all_turns()
        for source in place_line_current_sources(
            turn,
            n1=CERTIFICATION_FIDELITY.bore_filaments_per_axis,
            n2=CERTIFICATION_FIDELITY.bore_filaments_per_axis,
            quadrature=CERTIFICATION_FIDELITY.bore_quadrature,
        )
    )
    bx_t, by_t = field_at(sources, 0.0, 0.0)
    bore_field_t = math.hypot(bx_t, by_t)
    coefficients = multipole_coefficients(
        sources,
        order=max(HARMONIC_ORDERS),
        r_ref_mm=case.reference_radius_mm,
    )

    text = cadata_path.read_text(encoding="utf-8", errors="replace")
    resolutions = tuple(resolve_conductor(text, name) for name in case.conductor_names)
    data = tuple(
        LayerConductorData(
            strand=record.strand,
            cable=record.cable,
            remfit=record.remfit,
        )
        for record in resolutions
    )
    margins = load_line_margin_detail(
        case.design,
        data,
        1.9,
        fidelity=CERTIFICATION_FIDELITY,
    )
    return {
        "bore_field_t": bore_field_t,
        "peak_field_t": max(record.peak_field_t for record in margins),
        "margin_percent": min(record.margin_percent for record in margins),
        "harmonics": {
            order: float(coefficients[order - 1][0]) for order in HARMONIC_ORDERS
        },
    }


def _block_records(case: Case) -> tuple[BlockRecord, ...]:
    records: list[BlockRecord] = []
    number = 1
    for layer, conductor_name in zip(
        case.design.layers,
        case.conductor_names,
        strict=True,
    ):
        for block in layer.blocks:
            records.append(
                BlockRecord(
                    number=number,
                    n_turns=block.n_turns,
                    radius_mm=block.inner_radius_mm,
                    phi_deg=block.phi_deg,
                    alpha_deg=block.alpha_deg,
                    current_a=block.current_a,
                    conductor_name=conductor_name,
                    n2=CONDUCTOR_N2[conductor_name],
                )
            )
            number += 1
    return tuple(records)


def _write_data_file(
    template_path: Path,
    directory: Path,
    case: Case,
    records: tuple[BlockRecord, ...],
    cadata_name: str,
) -> Path:
    lines = template_path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines[1] = f"'DOT parity {case.case_id}'"
    lines[2] = _quoted_path("none")
    lines[3] = _quoted_path(cadata_name)
    lines[4] = _quoted_path("none")
    lines = [
        line.replace("LBEMFEM=T", "LBEMFEM=F")
        .replace("LIRON=T", "LIRON=F")
        .replace("LDXF=T", "LDXF=F")
        .replace("LPLOT=T", "LPLOT=F")
        for line in lines
    ]
    _replace_block_section(lines, records)
    _replace_layer_section(lines, len(records))
    _replace_harmonic_reference_radius(lines, case.reference_radius_mm)
    data_file = directory / f"dot_parity_{case.case_id.replace('-', '_')}.data"
    data_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return data_file


def _replace_block_section(
    lines: list[str],
    records: tuple[BlockRecord, ...],
) -> None:
    start = next(index for index, line in enumerate(lines) if line.startswith("BLOCK "))
    header = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].lstrip().startswith("no  type")
    )
    replacement = [f"BLOCK {len(records)}"]
    replacement.extend(
        (
            f"  {row.number:3d}  {1:3d}  {row.n_turns:3d}  "
            f"{row.radius_mm:12.7g}  {row.phi_deg:12.7g}  "
            f"{row.alpha_deg:12.7g}  {row.current_a:12.7g}  "
            f"{row.conductor_name:>10s}  {2:2d}  {row.n2:2d}  "
            f"{0:2d}  {0:11d} "
        )
        for row in records
    )
    lines[start:header] = replacement


def _replace_layer_section(lines: list[str], block_count: int) -> None:
    start = next(index for index, line in enumerate(lines) if line.startswith("LAYER "))
    header = next(
        index
        for index in range(start + 1, len(lines))
        if lines[index].lstrip().startswith("no  symm")
    )
    block_numbers = " ".join(str(index) for index in range(1, block_count + 1))
    lines[start:header] = ["LAYER 1", f"      1     2     1 {block_numbers} /"]


def _replace_harmonic_reference_radius(lines: list[str], r_ref_mm: float) -> None:
    start = next(
        index for index, line in enumerate(lines) if line.startswith("HARMONICTABLE ")
    )
    lines[start + 1] = (
        f"      1     1            0            0            0            0"
        f"      {r_ref_mm:.6g}        2                      0 "
    )


def _quoted_path(value: str) -> str:
    return f"'{value.ljust(83)}'"


def _run_roxie(
    data_file: Path,
    cadata_file: Path,
    output_dir: Path,
    service_url: str,
) -> Path:
    model_name = data_file.stem
    encoded = urllib.parse.quote(model_name, safe="")
    initialized = _json_request(service_url, f"/model/{encoded}", data=b"")
    timestamp = str(initialized["timestamp"])
    body, content_type = _multipart_form_data(
        fields={"model_name": model_name, "timestamp": timestamp},
        files=(data_file, cadata_file),
    )
    _json_request(
        service_url,
        "/model/",
        data=body,
        headers={"Content-Type": content_type},
    )
    result = _json_request(
        service_url,
        f"/model/{encoded}/{urllib.parse.quote(timestamp, safe='')}/run",
        data=b"",
    )
    if not bool(result.get("status")):
        raise RuntimeError(f"ROXIE run failed: {result.get('output', result)}")
    artefacts = tuple(str(name) for name in result.get("artefacts", ()))
    output_name = next((name for name in artefacts if name.endswith(".output")), None)
    if output_name is None:
        listing = _json_request(
            service_url,
            f"/artefacts/{encoded}/{urllib.parse.quote(timestamp, safe='')}",
        )
        output_name = next(
            (
                str(name)
                for name in listing.get("artefacts", ())
                if str(name).endswith(".output")
            ),
            None,
        )
    if output_name is None:
        raise RuntimeError("ROXIE produced no .output artefact")
    url = (
        f"{service_url.rstrip('/')}/artefact/{encoded}/"
        f"{urllib.parse.quote(timestamp, safe='')}/"
        f"{urllib.parse.quote(output_name, safe='')}"
    )
    with urllib.request.urlopen(url, timeout=180.0) as response:  # noqa: S310
        content = response.read()
    destination = output_dir / output_name
    destination.write_bytes(content)
    return destination


def _json_request(
    service_url: str,
    endpoint: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{service_url.rstrip('/')}{endpoint}",
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180.0) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


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


def _parse_roxie_output(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    number = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)"
    main = re.search(rf"MAIN FIELD\s*\(T\)\s*\.{{10,}}\s*{number}", text)
    peaks = re.findall(
        rf"PEAK FIELD IN CONDUCTOR\s+\d+\s*\(T\)\s*\.{{10,}}\s*{number}",
        text,
    )
    loadlines = re.findall(
        rf"PERCENTAGE ON THE LOAD LINE\s*\.{{10,}}\s*{number}",
        text,
    )
    normal_section = re.search(
        r"NORMAL RELATIVE MULTIPOLES \(1\.D-4\):(.*?)"
        r"SKEW RELATIVE MULTIPOLES",
        text,
        flags=re.DOTALL,
    )
    if main is None or not peaks or not loadlines or normal_section is None:
        raise ValueError(f"incomplete ROXIE metrics in {path}")
    normal = {
        int(order): _float(value)
        for order, value in re.findall(
            rf"\bb\s*(\d+):\s*{number}",
            normal_section.group(1),
        )
    }
    missing = set(HARMONIC_ORDERS).difference(normal)
    if missing:
        raise ValueError(f"missing ROXIE harmonics {sorted(missing)} in {path}")
    return {
        "bore_field_t": abs(_float(main.group(1))),
        "peak_field_t": max(abs(_float(value)) for value in peaks),
        "margin_percent": 100.0 - max(_float(value) for value in loadlines),
        "harmonics": {order: normal[order] for order in HARMONIC_ORDERS},
    }


def _float(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid checkpoint line {line_number}") from exc
        records[str(record["case_id"])] = record
    return records


def _append_checkpoint(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")


def _write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)


def _summary(
    results: list[dict[str, Any]],
    seed: int,
    cases_per_topology: int,
    template_path: Path,
    cadata_path: Path,
    service_url: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "study": (
            f"DOT {__version__} versus ROXIE 23.6/26.1.0.b3, "
            "2D coil-only no iron"
        ),
        "seed": seed,
        "case_count": len(results),
        "two_layer_cases": cases_per_topology,
        "four_layer_cases": cases_per_topology,
        "harmonic_orders": list(HARMONIC_ORDERS),
        "roxie_service_endpoint": service_url,
        "input_hashes_sha256": {
            "roxie_template": _sha256(template_path),
            "cadata": _sha256(cadata_path),
        },
        "numerical_fidelity": {
            "dot_bore_filaments_per_axis": (
                CERTIFICATION_FIDELITY.bore_filaments_per_axis
            ),
            "dot_peak_filaments_per_axis": (
                CERTIFICATION_FIDELITY.peak_filaments_per_axis
            ),
            "dot_bore_quadrature": CERTIFICATION_FIDELITY.bore_quadrature,
            "roxie_block_n1": 2,
            "roxie_block_n2_by_conductor": CONDUCTOR_N2,
        },
        "error_definitions": {
            "field_error_percent": "100*(DOT-ROXIE)/abs(ROXIE)",
            "margin_error_pp": "DOT margin - ROXIE margin, percentage points",
            "harmonic_error_units": "DOT b_n - ROXIE b_n, accelerator units",
        },
        "coverage": {
            "aperture_radius_mm": _range(results, "aperture_radius_mm"),
            "current_a": _range(results, "current_a"),
            "total_blocks": _range(results, "total_blocks"),
            "total_turns": _range(results, "total_turns"),
            "conductor_patterns": sorted({row["conductors"] for row in results}),
        },
        "overall": _metric_summary(results),
        "two_layer": _metric_summary(
            [row for row in results if row["topology_layers"] == 2]
        ),
        "four_layer": _metric_summary(
            [row for row in results if row["topology_layers"] == 4]
        ),
    }


def _metric_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        "bore_field_relative_error_percent": "bore_error_percent",
        "peak_field_relative_error_percent": "peak_error_percent",
        "loadline_margin_error_percentage_points": "margin_error_pp",
    }
    metrics.update(
        {f"b{order}_error_units": f"b{order}_error_units" for order in HARMONIC_ORDERS}
    )
    return {
        name: _distribution([float(row[column]) for row in results])
        for name, column in metrics.items()
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    absolute = sorted(abs(value) for value in values)
    return {
        "count": len(values),
        "signed_mean": statistics.fmean(values),
        "absolute_mean": statistics.fmean(absolute),
        "absolute_median": statistics.median(absolute),
        "absolute_p95": _percentile(absolute, 0.95),
        "absolute_max": max(absolute),
    }


def _percentile(sorted_values: list[float], fraction: float) -> float:
    position = fraction * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _range(results: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in results]
    return {"minimum": min(values), "maximum": max(values)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_service(url: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:  # noqa: S310
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(f"ROXIE service is unreachable at {url}: {exc}") from exc


def _duration(seconds: float) -> str:
    if not math.isfinite(seconds):
        return "--:--"
    total = max(int(round(seconds)), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


if __name__ == "__main__":
    main()
