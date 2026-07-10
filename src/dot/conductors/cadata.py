"""Minimal ROXIE ``.cadata`` conductor records used for critical-current work."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class StrandRecord:
    """Strand inputs needed to convert superconductor Jc into strand Ic."""

    diameter_mm: float
    cu_to_sc_ratio: float

    def __post_init__(self) -> None:
        _require_finite_positive(self.diameter_mm, "diameter_mm")
        _require_finite_nonnegative(self.cu_to_sc_ratio, "cu_to_sc_ratio")


@dataclass(frozen=True, slots=True)
class CableRecord:
    """Cable inputs needed to compose strand Ic into cable Ic."""

    n_strands: int
    degradation_percent: float

    def __post_init__(self) -> None:
        if isinstance(self.n_strands, bool) or not isinstance(self.n_strands, int):
            raise ValueError(f"n_strands must be an integer, got {self.n_strands!r}")
        if self.n_strands <= 0:
            raise ValueError(f"n_strands must be positive, got {self.n_strands!r}")
        _require_finite_nonnegative(self.degradation_percent, "degradation_percent")
        if self.degradation_percent > 100.0:
            raise ValueError("degradation_percent must be <= 100")


@dataclass(frozen=True, slots=True)
class Type1FitCoefficients:
    """Bottura Nb-Ti REMFIT type-1 coefficients C1..C7."""

    c1: float
    c2: float
    c3: float
    c4: float
    c5: float
    c6: float
    c7: float

    def __post_init__(self) -> None:
        for index, value in enumerate(
            (self.c1, self.c2, self.c3, self.c4, self.c5, self.c6, self.c7),
            start=1,
        ):
            _require_finite_positive(value, f"c{index}")


@dataclass(frozen=True, slots=True)
class Type11FitCoefficients:
    """CERN high-field Nb3Sn REMFIT type-11 coefficients C1..C7."""

    c0: float
    bc20_t: float
    tc0_k: float
    alpha: float
    v: float
    p: float
    q: float

    def __post_init__(self) -> None:
        for name, value in (
            ("c0", self.c0),
            ("bc20_t", self.bc20_t),
            ("tc0_k", self.tc0_k),
            ("alpha", self.alpha),
            ("v", self.v),
            ("p", self.p),
            ("q", self.q),
        ):
            _require_finite_positive(value, name)


RemfitCoefficients = Type1FitCoefficients | Type11FitCoefficients


@dataclass(frozen=True, slots=True)
class FilamentRecord:
    """FILAMENT row carrying the critical-current REMFIT name."""

    name: str
    jc_fit_name: str


@dataclass(frozen=True, slots=True)
class ConductorRecord:
    """One ROXIE CONDUCTOR row linking cable, strand, and REMFIT names."""

    number: int
    name: str
    conductor_type: int
    cable_name: str
    strand_name: str
    filament_name: str
    insul_name: str
    transient_name: str
    remfit_name: str
    temperature_k: float
    comment: str


ConductorResolutionStatus = Literal["resolved", "not_found", "unsupported_fit_type"]


@dataclass(frozen=True, slots=True)
class ConductorResolution:
    """Result of resolving a named CONDUCTOR row to supported margin data."""

    status: ConductorResolutionStatus
    conductor_name: str
    conductor: ConductorRecord | None = None
    strand: StrandRecord | None = None
    cable: CableRecord | None = None
    remfit: RemfitCoefficients | None = None
    temperature_k: float | None = None
    unsupported_fit_type: int | None = None
    remfit_name: str | None = None
    message: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved"


@dataclass(frozen=True, slots=True)
class CadataRecords:
    """Parsed critical-current records keyed by their catalogue names."""

    strands: dict[str, StrandRecord]
    cables: dict[str, CableRecord]
    remfits: dict[str, RemfitCoefficients]
    filaments: dict[str, FilamentRecord]
    conductors: dict[str, ConductorRecord]


class UnsupportedFitTypeError(ValueError):
    """Raised when a REMFIT row uses a fit type outside this task's scope."""

    def __init__(self, fit_type: int, name: str) -> None:
        super().__init__(f"unsupported REMFIT type {fit_type} for {name!r}; only type 1 is supported")
        self.fit_type = fit_type
        self.name = name


def parse_cadata_text(
    text: str,
    *,
    remfit_name: str | None = None,
    first_supported_remfit: bool = False,
) -> CadataRecords:
    """Parse STRAND, CABLE, and REMFIT records from ``.cadata`` text.

    The ROXIE catalogue format is section-count based. Relevant rows use these
    columns after tokenization:

    * ``STRAND``: ``No Name diam. cu/sc ...``
    * ``CABLE``: ``No Name height width_i width_o ns transp. degrd ...``
    * ``REMFIT``: ``No Name Type C1 C2 C3 C4 C5 C6 C7 C8 ...``
    * ``FILAMENT``: ``No Name fildiao fildiai Jc-Fit fit-| Comment``
    * ``CONDUCTOR``:
      ``No Name Type Cable Strand Filament Insul Transient REMFIT T_o Comment``

    Other sections and trailing human-readable header rows are ignored. By
    default, all REMFIT rows are parsed eagerly and any unsupported type raises.
    Pass ``remfit_name`` or ``first_supported_remfit`` to parse only the REMFIT
    row the caller needs.
    """

    if remfit_name is not None and first_supported_remfit:
        raise ValueError("remfit_name and first_supported_remfit are mutually exclusive")

    sections = _section_rows(text.splitlines())
    strands = _parse_strands(sections.get("STRAND", ()))
    cables = _parse_cables(sections.get("CABLE", ()))
    filaments = _parse_filaments(sections.get("FILAMENT", ()))
    conductors = _parse_conductors(sections.get("CONDUCTOR", ()))

    remfits = _parse_remfits(
        sections.get("REMFIT", ()),
        remfit_name=remfit_name,
        first_supported_remfit=first_supported_remfit,
    )

    return CadataRecords(
        strands=strands,
        cables=cables,
        remfits=remfits,
        filaments=filaments,
        conductors=conductors,
    )


def find_type1_remfit(text: str, name: str) -> Type1FitCoefficients:
    """Return the named type-1 REMFIT coefficients without validating others."""

    records = parse_cadata_text(text, remfit_name=name)
    remfit = records.remfits[name]
    if not isinstance(remfit, Type1FitCoefficients):
        raise UnsupportedFitTypeError(11, name)
    return remfit


def resolve_conductor(text: str, name: str) -> ConductorResolution:
    """Resolve a named CONDUCTOR row to linked supported conductor data.

    Unsupported REMFIT types are returned as typed resolution results instead
    of escaping as ``UnsupportedFitTypeError``.
    """

    sections = _section_rows(text.splitlines())
    conductors = _parse_conductors(sections.get("CONDUCTOR", ()))
    conductor = conductors.get(name)
    if conductor is None:
        return ConductorResolution(
            status="not_found",
            conductor_name=name,
            message=f"CONDUCTOR record {name!r} not found",
        )

    strands = _parse_strands(sections.get("STRAND", ()))
    cables = _parse_cables(sections.get("CABLE", ()))
    filaments = _parse_filaments(sections.get("FILAMENT", ()))
    try:
        strand = strands[conductor.strand_name]
    except KeyError as exc:
        raise ValueError(f"STRAND record {conductor.strand_name!r} not found") from exc
    try:
        cable = cables[conductor.cable_name]
    except KeyError as exc:
        raise ValueError(f"CABLE record {conductor.cable_name!r} not found") from exc

    remfit_name = _critical_current_remfit_name(conductor, filaments)
    remfit_row = _find_remfit_row(sections.get("REMFIT", ()), remfit_name)
    try:
        remfit = _parse_supported_remfit_row(remfit_row)
    except UnsupportedFitTypeError as exc:
        return ConductorResolution(
            status="unsupported_fit_type",
            conductor_name=name,
            conductor=conductor,
            strand=strand,
            cable=cable,
            temperature_k=conductor.temperature_k,
            unsupported_fit_type=exc.fit_type,
            remfit_name=exc.name,
            message=str(exc),
        )

    return ConductorResolution(
        status="resolved",
        conductor_name=name,
        conductor=conductor,
        strand=strand,
        cable=cable,
        remfit=remfit,
        temperature_k=conductor.temperature_k,
        remfit_name=remfit_name,
        message=f"CONDUCTOR record {name!r} resolved",
    )


def _parse_strands(rows: list[list[str]]) -> dict[str, StrandRecord]:
    strands: dict[str, StrandRecord] = {}
    for row in rows:
        if len(row) < 4:
            raise ValueError(f"STRAND row has too few columns: {row!r}")
        strands[row[1]] = StrandRecord(
            diameter_mm=float(row[2]),
            cu_to_sc_ratio=float(row[3]),
        )
    return strands


def _parse_cables(rows: list[list[str]]) -> dict[str, CableRecord]:
    cables: dict[str, CableRecord] = {}
    for row in rows:
        if len(row) < 8:
            raise ValueError(f"CABLE row has too few columns: {row!r}")
        cables[row[1]] = CableRecord(
            n_strands=int(float(row[5])),
            degradation_percent=float(row[7]),
        )
    return cables


def _parse_filaments(rows: list[list[str]]) -> dict[str, FilamentRecord]:
    filaments: dict[str, FilamentRecord] = {}
    for row in rows:
        if len(row) < 5:
            raise ValueError(f"FILAMENT row has too few columns: {row!r}")
        filaments[row[1]] = FilamentRecord(name=row[1], jc_fit_name=row[4])
    return filaments


def _parse_conductors(rows: list[list[str]]) -> dict[str, ConductorRecord]:
    conductors: dict[str, ConductorRecord] = {}
    for row in rows:
        if len(row) < 10:
            raise ValueError(f"CONDUCTOR row has too few columns: {row!r}")
        comment = row[10] if len(row) > 10 else ""
        conductor = ConductorRecord(
            number=int(float(row[0])),
            name=row[1],
            conductor_type=int(float(row[2])),
            cable_name=row[3],
            strand_name=row[4],
            filament_name=row[5],
            insul_name=row[6],
            transient_name=row[7],
            remfit_name=row[8],
            temperature_k=float(row[9]),
            comment=comment,
        )
        conductors[conductor.name] = conductor
    return conductors


def _critical_current_remfit_name(
    conductor: ConductorRecord,
    filaments: dict[str, FilamentRecord],
) -> str:
    filament = filaments.get(conductor.filament_name)
    if filament is not None:
        return filament.jc_fit_name
    return conductor.remfit_name


def _parse_remfits(
    rows: list[list[str]],
    *,
    remfit_name: str | None,
    first_supported_remfit: bool,
) -> dict[str, RemfitCoefficients]:
    if remfit_name is not None:
        for row in rows:
            if len(row) < 2:
                continue
            name = row[1]
            if name != remfit_name:
                continue
            return {name: _parse_supported_remfit_row(row)}
        raise ValueError(f"REMFIT record {remfit_name!r} not found")

    remfits: dict[str, RemfitCoefficients] = {}
    for row in rows:
        if first_supported_remfit:
            if len(row) < 3:
                continue
            fit_type = int(float(row[2]))
            if fit_type not in (1, 11):
                continue
        fit = _parse_supported_remfit_row(row)
        remfits[row[1]] = fit
        if first_supported_remfit:
            break
    return remfits


def _find_remfit_row(rows: list[list[str]], remfit_name: str) -> list[str]:
    for row in rows:
        if len(row) >= 2 and row[1] == remfit_name:
            return row
    raise ValueError(f"REMFIT record {remfit_name!r} not found")


def _parse_supported_remfit_row(row: list[str]) -> RemfitCoefficients:
    if len(row) < 10:
        raise ValueError(f"REMFIT row has too few columns: {row!r}")
    name = row[1]
    fit_type = int(float(row[2]))
    if fit_type == 1:
        return Type1FitCoefficients(*(float(value) for value in row[3:10]))
    if fit_type == 11:
        return Type11FitCoefficients(*(float(value) for value in row[3:10]))
    raise UnsupportedFitTypeError(fit_type, name)


def _section_rows(lines: list[str]) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    known_sections = {"STRAND", "CABLE", "REMFIT", "FILAMENT", "CONDUCTOR"}
    index = 0
    while index < len(lines):
        match = re.match(r"^([A-Z][A-Z0-9_]*)\s+(\d+)\s*$", lines[index].strip())
        if match is None or match.group(1) not in known_sections:
            index += 1
            continue

        section = match.group(1)
        count = int(match.group(2))
        rows: list[list[str]] = []
        index += 1
        for _ in range(count):
            if index >= len(lines):
                raise ValueError(f"{section} section ended before {count} rows were read")
            rows.append([token.strip("'") for token in _tokens(lines[index])])
            index += 1
        sections[section] = rows
    return sections


def _tokens(line: str) -> list[str]:
    return re.findall(r"'[^']*'|\S+", line.strip())


def _require_finite_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive, got {value!r}")


def _require_finite_nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
