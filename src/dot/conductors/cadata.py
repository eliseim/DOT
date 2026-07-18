"""Typed ROXIE ``.cadata`` records used by geometry and critical-current work.

The parser deliberately preserves links between ``CONDUCTOR``, ``CABLE``,
``STRAND``, ``FILAMENT``, ``INSUL`` and ``REMFIT`` records.  Selecting the
first record from each section independently is not safe: real catalogues
contain many unrelated conductor families.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class StrandRecord:
    """Strand inputs needed to convert non-copper ``Jc`` into strand ``Ic``.

    ROXIE labels the second quantity ``cu/sc``.  For the supported Nb-Ti and
    Nb3Sn fits it is interpreted as the engineering Cu/non-Cu area ratio: the
    fitted ``Jc`` is referred to the whole non-copper area, not only to the
    current-carrying Nb3Sn phase.
    """

    diameter_mm: float
    cu_to_sc_ratio: float

    def __post_init__(self) -> None:
        _require_finite_positive(self.diameter_mm, "diameter_mm")
        _require_finite_nonnegative(self.cu_to_sc_ratio, "cu_to_sc_ratio")

    @property
    def cu_to_non_cu_ratio(self) -> float:
        """Return ROXIE ``cu/sc`` with its physical Cu/non-Cu meaning."""

        return self.cu_to_sc_ratio


@dataclass(frozen=True, slots=True)
class CableRecord:
    """Cable electrical and geometric data.

    Geometry fields are optional for backwards compatibility with small
    critical-current-only fixtures.  A resolved design conductor requires
    them before it can be converted to :class:`dot.geometry.CableSpec`.
    """

    n_strands: int
    degradation_percent: float
    height_mm: float | None = None
    width_inner_mm: float | None = None
    width_outer_mm: float | None = None
    transposition_pitch_mm: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.n_strands, bool) or not isinstance(self.n_strands, int):
            raise ValueError(f"n_strands must be an integer, got {self.n_strands!r}")
        if self.n_strands <= 0:
            raise ValueError(f"n_strands must be positive, got {self.n_strands!r}")
        _require_finite_nonnegative(self.degradation_percent, "degradation_percent")
        if self.degradation_percent > 100.0:
            raise ValueError("degradation_percent must be <= 100")
        for name, value in (
            ("height_mm", self.height_mm),
            ("width_inner_mm", self.width_inner_mm),
            ("width_outer_mm", self.width_outer_mm),
        ):
            if value is not None:
                _require_finite_positive(value, name)
        if self.transposition_pitch_mm is not None:
            _require_finite_nonnegative(
                self.transposition_pitch_mm, "transposition_pitch_mm"
            )

    @property
    def has_geometry(self) -> bool:
        return (
            self.height_mm is not None
            and self.width_inner_mm is not None
            and self.width_outer_mm is not None
        )


@dataclass(frozen=True, slots=True)
class InsulationRecord:
    """Radial and azimuthal turn insulation from one ``INSUL`` row."""

    radial_mm: float
    azimuthal_mm: float

    def __post_init__(self) -> None:
        _require_finite_nonnegative(self.radial_mm, "radial_mm")
        _require_finite_nonnegative(self.azimuthal_mm, "azimuthal_mm")


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
class UnsupportedRemfitRecord:
    """A preserved REMFIT row whose equation is not implemented by DOT."""

    name: str
    fit_type: int
    values: tuple[float, ...]
    comment: str = ""


@dataclass(frozen=True, slots=True)
class ConductorRecord:
    """One ROXIE CONDUCTOR row linking its catalogue records."""

    number: int
    name: str
    conductor_type: int
    cable_name: str
    strand_name: str
    filament_name: str
    insul_name: str
    transient_name: str
    quench_material_name: str
    temperature_k: float
    comment: str

    @property
    def remfit_name(self) -> str:
        """Compatibility alias for the historically misnamed column.

        Column 8 of a ROXIE ``CONDUCTOR`` row is the quench-material name,
        not a critical-current REMFIT.  Critical-current resolution must go
        through the linked ``FILAMENT`` row.
        """

        return self.quench_material_name


ConductorResolutionStatus = Literal["resolved", "not_found", "unsupported_fit_type"]


@dataclass(frozen=True, slots=True)
class ConductorResolution:
    """Result of resolving a named CONDUCTOR row to supported margin data."""

    status: ConductorResolutionStatus
    conductor_name: str
    conductor: ConductorRecord | None = None
    strand: StrandRecord | None = None
    cable: CableRecord | None = None
    insulation: InsulationRecord | None = None
    remfit: RemfitCoefficients | None = None
    temperature_k: float | None = None
    unsupported_fit_type: int | None = None
    remfit_name: str | None = None
    message: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved"

    def cable_spec(self):  # noqa: ANN201
        """Return the linked cable geometry as a ``CableSpec``.

        The local import keeps the conductor catalogue independent of the
        geometry module at import time.
        """

        if self.cable is None or not self.cable.has_geometry:
            raise ValueError(f"CONDUCTOR record {self.conductor_name!r} has no complete cable geometry")
        if self.insulation is None:
            raise ValueError(f"CONDUCTOR record {self.conductor_name!r} has no linked INSUL record")
        from dot.geometry import CableSpec

        return CableSpec(
            height_mm=self.cable.height_mm,
            width_inner_mm=self.cable.width_inner_mm,
            width_outer_mm=self.cable.width_outer_mm,
            insulation_radial_mm=self.insulation.radial_mm,
            insulation_azimuthal_mm=self.insulation.azimuthal_mm,
        )


@dataclass(frozen=True, slots=True)
class CadataRecords:
    """Parsed critical-current records keyed by their catalogue names."""

    strands: dict[str, StrandRecord]
    cables: dict[str, CableRecord]
    remfits: dict[str, RemfitCoefficients]
    filaments: dict[str, FilamentRecord]
    conductors: dict[str, ConductorRecord]
    insulations: dict[str, InsulationRecord]
    unsupported_remfits: dict[str, UnsupportedRemfitRecord]


class UnsupportedFitTypeError(ValueError):
    """Raised when a REMFIT row uses a fit type outside this task's scope."""

    def __init__(self, fit_type: int, name: str) -> None:
        super().__init__(
            f"unsupported REMFIT type {fit_type} for {name!r}; supported types are 1 and 11"
        )
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

    * ``STRAND``: ``No Name diam. cu/sc ...`` (Cu/non-Cu area ratio)
    * ``CABLE``: ``No Name height width_i width_o ns transp. degrd ...``
    * ``REMFIT``: ``No Name Type C1 C2 C3 C4 C5 C6 C7 C8 ...``
    * ``FILAMENT``: ``No Name fildiao fildiai Jc-Fit fit-| Comment``
    * ``INSUL``: ``No Name Radial Azimut Comment``
    * ``CONDUCTOR``:
      ``No Name Type Cable Strand Filament Insul Transient QuenchMat T_o Comment``

    Other sections and trailing human-readable header rows are ignored. By
    By default, supported REMFIT rows are parsed and unsupported rows are
    preserved in ``unsupported_remfits``.  Selecting a named unsupported fit
    still raises :class:`UnsupportedFitTypeError`.
    """

    if remfit_name is not None and first_supported_remfit:
        raise ValueError("remfit_name and first_supported_remfit are mutually exclusive")

    sections = _section_rows(text.splitlines())
    strands = _parse_strands(sections.get("STRAND", ()))
    cables = _parse_cables(sections.get("CABLE", ()))
    insulations = _parse_insulations(sections.get("INSUL", ()))
    filaments = _parse_filaments(sections.get("FILAMENT", ()))
    conductors = _parse_conductors(sections.get("CONDUCTOR", ()))

    remfits, unsupported_remfits = _parse_remfits(
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
        insulations=insulations,
        unsupported_remfits=unsupported_remfits,
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
    insulations = _parse_insulations(sections.get("INSUL", ()))
    filaments = _parse_filaments(sections.get("FILAMENT", ()))
    try:
        strand = strands[conductor.strand_name]
    except KeyError as exc:
        raise ValueError(f"STRAND record {conductor.strand_name!r} not found") from exc
    try:
        cable = cables[conductor.cable_name]
    except KeyError as exc:
        raise ValueError(f"CABLE record {conductor.cable_name!r} not found") from exc
    try:
        insulation = insulations[conductor.insul_name]
    except KeyError as exc:
        raise ValueError(f"INSUL record {conductor.insul_name!r} not found") from exc

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
            insulation=insulation,
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
        insulation=insulation,
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
            height_mm=float(row[2]),
            width_inner_mm=float(row[3]),
            width_outer_mm=float(row[4]),
            transposition_pitch_mm=float(row[6]),
        )
    return cables


def _parse_insulations(rows: list[list[str]]) -> dict[str, InsulationRecord]:
    insulations: dict[str, InsulationRecord] = {}
    for row in rows:
        if len(row) < 4:
            raise ValueError(f"INSUL row has too few columns: {row!r}")
        insulations[row[1]] = InsulationRecord(
            radial_mm=float(row[2]),
            azimuthal_mm=float(row[3]),
        )
    return insulations


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
            quench_material_name=row[8],
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
    if filament is None:
        raise ValueError(
            f"FILAMENT record {conductor.filament_name!r} not found; "
            "the CONDUCTOR quench-material column is not a REMFIT fallback"
        )
    return filament.jc_fit_name


def _parse_remfits(
    rows: list[list[str]],
    *,
    remfit_name: str | None,
    first_supported_remfit: bool,
) -> tuple[dict[str, RemfitCoefficients], dict[str, UnsupportedRemfitRecord]]:
    if remfit_name is not None:
        for row in rows:
            if len(row) < 2:
                continue
            name = row[1]
            if name != remfit_name:
                continue
            return {name: _parse_supported_remfit_row(row)}, {}
        raise ValueError(f"REMFIT record {remfit_name!r} not found")

    remfits: dict[str, RemfitCoefficients] = {}
    unsupported: dict[str, UnsupportedRemfitRecord] = {}
    for row in rows:
        if first_supported_remfit:
            if len(row) < 3:
                continue
            fit_type = int(float(row[2]))
            if fit_type not in (1, 11):
                continue
        try:
            fit = _parse_supported_remfit_row(row)
        except UnsupportedFitTypeError:
            if first_supported_remfit:
                continue
            unsupported_row = _unsupported_remfit_row(row)
            unsupported[unsupported_row.name] = unsupported_row
            continue
        remfits[row[1]] = fit
        if first_supported_remfit:
            break
    return remfits, unsupported


def _unsupported_remfit_row(row: list[str]) -> UnsupportedRemfitRecord:
    if len(row) < 3:
        raise ValueError(f"REMFIT row has too few columns: {row!r}")
    values: list[float] = []
    for token in row[3:14]:
        try:
            values.append(float(token))
        except ValueError:
            break
    comment = row[14] if len(row) > 14 else ""
    return UnsupportedRemfitRecord(
        name=row[1],
        fit_type=int(float(row[2])),
        values=tuple(values),
        comment=comment,
    )


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
    known_sections = {"STRAND", "CABLE", "REMFIT", "FILAMENT", "CONDUCTOR", "INSUL"}
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
