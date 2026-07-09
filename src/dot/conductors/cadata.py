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


def parse_cadata_text(text: str) -> CadataRecords:
    """Parse STRAND, CABLE, and REMFIT records from ``.cadata`` text.

    The ROXIE catalogue format is section-count based. Relevant rows use these
    columns after tokenization:

    * ``STRAND``: ``No Name diam. cu/sc ...``
    * ``CABLE``: ``No Name height width_i width_o ns transp. degrd ...``
    * ``REMFIT``: ``No Name Type C1 C2 C3 C4 C5 C6 C7 C8 ...``

    Other sections and trailing human-readable header rows are ignored.
    """

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

    for row in sections.get("REMFIT", ()):
        if len(row) < 10:
            raise ValueError(f"REMFIT row has too few columns: {row!r}")
        name = row[1]
        fit_type = int(float(row[2]))
        if fit_type != 1:
            raise UnsupportedFitTypeError(fit_type, name)
        remfits[name] = Type1FitCoefficients(*(float(value) for value in row[3:10]))

    return CadataRecords(strands=strands, cables=cables, remfits=remfits)


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
