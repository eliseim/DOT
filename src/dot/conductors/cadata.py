"""Minimal ROXIE ``.cadata`` conductor records used for critical-current work."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


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
class CadataRecords:
    """Parsed critical-current records keyed by their catalogue names."""

    strands: dict[str, StrandRecord]
    cables: dict[str, CableRecord]
    remfits: dict[str, Type1FitCoefficients]


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

    Other sections and trailing human-readable header rows are ignored. By
    default, all REMFIT rows are parsed eagerly and any unsupported type raises.
    Pass ``remfit_name`` or ``first_supported_remfit`` to parse only the REMFIT
    row the caller needs.
    """

    if remfit_name is not None and first_supported_remfit:
        raise ValueError("remfit_name and first_supported_remfit are mutually exclusive")

    sections = _section_rows(text.splitlines())
    strands: dict[str, StrandRecord] = {}
    cables: dict[str, CableRecord] = {}
    remfits: dict[str, Type1FitCoefficients] = {}

    for row in sections.get("STRAND", ()):
        if len(row) < 4:
            raise ValueError(f"STRAND row has too few columns: {row!r}")
        strands[row[1]] = StrandRecord(
            diameter_mm=float(row[2]),
            cu_to_sc_ratio=float(row[3]),
        )

    for row in sections.get("CABLE", ()):
        if len(row) < 8:
            raise ValueError(f"CABLE row has too few columns: {row!r}")
        cables[row[1]] = CableRecord(
            n_strands=int(float(row[5])),
            degradation_percent=float(row[7]),
        )

    remfits = _parse_remfits(
        sections.get("REMFIT", ()),
        remfit_name=remfit_name,
        first_supported_remfit=first_supported_remfit,
    )

    return CadataRecords(strands=strands, cables=cables, remfits=remfits)


def find_type1_remfit(text: str, name: str) -> Type1FitCoefficients:
    """Return the named type-1 REMFIT coefficients without validating others."""

    records = parse_cadata_text(text, remfit_name=name)
    return records.remfits[name]


def _parse_remfits(
    rows: list[list[str]],
    *,
    remfit_name: str | None,
    first_supported_remfit: bool,
) -> dict[str, Type1FitCoefficients]:
    if remfit_name is not None:
        for row in rows:
            if len(row) < 2:
                continue
            name = row[1]
            if name != remfit_name:
                continue
            return {name: _parse_type1_remfit_row(row)}
        raise ValueError(f"REMFIT record {remfit_name!r} not found")

    remfits: dict[str, Type1FitCoefficients] = {}
    for row in rows:
        if first_supported_remfit:
            if len(row) < 3:
                continue
            fit_type = int(float(row[2]))
            if fit_type != 1:
                continue
        fit = _parse_type1_remfit_row(row)
        remfits[row[1]] = fit
        if first_supported_remfit:
            break
    return remfits


def _parse_type1_remfit_row(row: list[str]) -> Type1FitCoefficients:
    if len(row) < 10:
        raise ValueError(f"REMFIT row has too few columns: {row!r}")
    name = row[1]
    fit_type = int(float(row[2]))
    if fit_type != 1:
        raise UnsupportedFitTypeError(fit_type, name)
    return Type1FitCoefficients(*(float(value) for value in row[3:10]))


def _section_rows(lines: list[str]) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    known_sections = {"STRAND", "CABLE", "REMFIT"}
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
