"""Optimization objective functions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from dot.conductors import (
    CableRecord,
    StrandRecord,
    load_line_margin_percent,
    solve_short_sample_current,
)
from dot.conductors.cadata import RemfitCoefficients
from dot.conductors.critical_surface import upper_critical_field
from dot.geometry import CableSpec, DipoleDesign, Point, TurnPolygon
from dot.physics import (
    LineCurrentSourceArray,
    field_at_many,
    multipole_coefficients,
    place_line_current_sources,
)

PEAK_FIELD_FILAMENTS_PER_AXIS = 80


@dataclass(frozen=True, slots=True)
class EvaluationFidelity:
    """Versioned source resolutions for a physics evaluation."""

    name: str
    bore_filaments_per_axis: int
    peak_filaments_per_axis: int
    bore_quadrature: str = "midpoint"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("fidelity name must be non-empty")
        for field_name, value in (
            ("bore_filaments_per_axis", self.bore_filaments_per_axis),
            ("peak_filaments_per_axis", self.peak_filaments_per_axis),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.bore_quadrature not in {"midpoint", "gauss-legendre"}:
            raise ValueError(
                "bore_quadrature must be 'midpoint' or 'gauss-legendre'"
            )


# A 6x6 near-field source grid has a repeatable quadrature-alignment bias for
# CTH-like Rutherford turns: it overestimates the peak field by roughly 0.5 T
# and understates a genuinely 25% load-line margin by more than two percentage
# points. 8x8 removes that false margin barrier at modest additional cost.
SEARCH_FIDELITY = EvaluationFidelity(
    "search-v3-gauss",
    3,
    8,
    bore_quadrature="gauss-legendre",
)
CERTIFICATION_FIDELITY = EvaluationFidelity("certify-v1", 12, 80)


@dataclass(frozen=True, slots=True)
class LayerConductorData:
    """Critical-current records assigned to one geometry layer."""

    strand: StrandRecord
    cable: CableRecord
    remfit: RemfitCoefficients


@dataclass(frozen=True, slots=True)
class _IndexedTurn:
    layer_index: int
    block_index: int
    turn: TurnPolygon


@dataclass(frozen=True, slots=True)
class LayerMarginRecord:
    """Load-line margin detail for one layer.

    ``load_line_margin_objective`` computes exactly these values internally
    already, but only ever returns ``min(margin_percent for all layers)`` --
    discarding which layer that minimum came from and why (a layer can be
    the limiting one either because its peak field is high, e.g. the
    innermost layer closest to the bore, or because its conductor's
    critical-current curve is comparatively unfavorable at that field, e.g.
    a lower-field-class conductor in an outer layer). This record surfaces
    that detail directly instead of requiring it to be re-derived.
    """

    layer_index: int
    peak_field_t: float
    operating_current_a: float
    short_sample_current_a: float
    margin_percent: float


@dataclass(frozen=True, slots=True)
class BlockMarginRecord:
    """Load-line result for one active block using global ROXIE numbering."""

    layer_index: int
    block_index: int
    roxie_block: int
    peak_field_t: float
    operating_current_a: float
    short_sample_current_a: float
    margin_percent: float


def harmonic_table(
    design: DipoleDesign,
    r_ref_mm: float,
    max_order: int,
    fidelity: EvaluationFidelity | None = None,
) -> tuple[tuple[int, float, float], ...]:
    """Return ``(order, b_n, a_n)`` in CERN/European units."""

    if max_order < 2:
        raise ValueError("max_order must be at least 2")
    sources = _design_sources(
        design,
        3 if fidelity is None else fidelity.bore_filaments_per_axis,
        "midpoint" if fidelity is None else fidelity.bore_quadrature,
    )
    coefficients = multipole_coefficients(sources, order=max_order, r_ref_mm=r_ref_mm)
    return tuple(
        (order, float(coefficients[order - 1][0]), float(coefficients[order - 1][1]))
        for order in range(1, max_order + 1)
    )


def field_quality_objective(
    design: DipoleDesign,
    r_ref_mm: float,
    max_order: int,
    *,
    normal_orders: tuple[int, ...] | None = None,
    normal_targets: Mapping[int, float] | None = None,
    include_skew: bool = True,
    fidelity: EvaluationFidelity | None = None,
) -> float:
    """Return the worst requested harmonic in accelerator ``units``.

    ``normal_orders`` makes the engineering specification explicit.  Each
    selected normal term is scored as ``abs(b_n - normal_targets[n])``;
    omitted targets default to zero. When ``normal_orders``
    is omitted the legacy behaviour (all normal and skew orders from 2 through
    ``max_order``) is retained.  Ideal dipole target synthesis normally passes
    the allowed normal orders ``(3, 5, 7, ...)`` and reports skew terms without
    optimizing them, because the one-quadrant symmetry makes them identically
    zero.
    """

    table = harmonic_table(design, r_ref_mm, max_order, fidelity)
    target_by_order = {} if normal_targets is None else dict(normal_targets)
    invalid_targets = tuple(
        order
        for order, target in target_by_order.items()
        if order < 2 or order > max_order or not math.isfinite(target)
    )
    if invalid_targets:
        raise ValueError(
            f"normal harmonic target orders outside 2..{max_order}: {invalid_targets!r}"
        )
    if normal_orders is None:
        selected = table[1:]
    else:
        if not normal_orders:
            raise ValueError("normal_orders must not be empty")
        invalid = tuple(order for order in normal_orders if order < 2 or order > max_order)
        if invalid:
            raise ValueError(f"normal harmonic orders outside 2..{max_order}: {invalid!r}")
        wanted = set(normal_orders)
        unselected_targets = tuple(order for order in target_by_order if order not in wanted)
        if unselected_targets:
            raise ValueError(
                "normal harmonic targets must belong to normal_orders: "
                f"{unselected_targets!r}"
            )
        selected = tuple(row for row in table if row[0] in wanted)
    values = [abs(b_n - target_by_order.get(order, 0.0)) for order, b_n, _ in selected]
    if include_skew:
        values.extend(abs(a_n) for _, _, a_n in selected)
    return max(values)


def load_line_margin_objective(
    design: DipoleDesign,
    cable_specs_by_layer: object,
    cadata_by_layer: tuple[LayerConductorData, ...],
    temperature_k: float,
    fidelity: EvaluationFidelity | None = None,
) -> float:
    """Return load-line current margin percent for the peak-field turn proxy.

    The field-limiting location is the sampled turn boundary point with the
    largest magnetic-field magnitude.  Its layer selects the conductor records,
    and ``B_peak / I_operating`` defines the load-line slope.
    """

    del cable_specs_by_layer
    records = load_line_margin_detail(design, cadata_by_layer, temperature_k, fidelity=fidelity)
    return min(record.margin_percent for record in records)


def load_line_margin_detail(
    design: DipoleDesign,
    cadata_by_layer: tuple[LayerConductorData, ...],
    temperature_k: float,
    *,
    fidelity: EvaluationFidelity | None = None,
) -> tuple[LayerMarginRecord, ...]:
    """Return the full per-layer load-line margin breakdown.

    ``load_line_margin_objective`` reduces this to a single
    ``min(margin_percent)`` for use as a pymoo objective; this function is
    the underlying detail, for reporting which layer is actually limiting
    the design and why -- a low margin can come from either a high peak
    field (e.g. the innermost, highest-field layer) or an unfavorable
    conductor critical-current curve at that field (e.g. a lower-field-class
    conductor in an outer layer), and only the per-layer breakdown
    distinguishes the two.
    """

    evaluated_layers = _margin_layer_indices(design, cadata_by_layer)
    records: list[LayerMarginRecord] = []
    indexed_turns = _conductor_turns_by_layer(design)
    peak_axis = (
        PEAK_FIELD_FILAMENTS_PER_AXIS if fidelity is None else fidelity.peak_filaments_per_axis
    )
    sources = _near_field_source_array(indexed_turns, peak_axis)
    peaks_by_layer = _peak_fields_by_layer(
        indexed_turns,
        sources,
        evaluated_layers=evaluated_layers,
    )
    for layer_index in evaluated_layers:
        limiting_turn, peak_field_t = peaks_by_layer[layer_index]
        operating_current_a = abs(limiting_turn.turn.current_a)
        if operating_current_a == 0.0:
            raise ValueError("operating current must be nonzero")
        layer_data = cadata_by_layer[layer_index]
        k_field_per_current = peak_field_t / operating_current_a
        short_sample_current_a = solve_short_sample_current(
            layer_data.remfit,
            layer_data.strand,
            layer_data.cable,
            temperature_k,
            k_field_per_current,
            i_hi=_load_line_upper_bracket(layer_data.remfit, temperature_k, k_field_per_current),
        )
        margin_percent = load_line_margin_percent(operating_current_a, short_sample_current_a)
        records.append(
            LayerMarginRecord(
                layer_index=layer_index,
                peak_field_t=peak_field_t,
                operating_current_a=operating_current_a,
                short_sample_current_a=short_sample_current_a,
                margin_percent=margin_percent,
            )
        )
    return tuple(records)


def load_line_margin_by_block_detail(
    design: DipoleDesign,
    cadata_by_layer: tuple[LayerConductorData, ...],
    temperature_k: float,
    *,
    fidelity: EvaluationFidelity | None = None,
) -> tuple[BlockMarginRecord, ...]:
    """Return peak field and load-line margin for every active ROXIE block."""

    evaluated_layers = _margin_layer_indices(design, cadata_by_layer)
    indexed_turns = _conductor_turns_by_layer(design)
    peak_axis = (
        PEAK_FIELD_FILAMENTS_PER_AXIS
        if fidelity is None
        else fidelity.peak_filaments_per_axis
    )
    sources = _near_field_source_array(indexed_turns, peak_axis)
    peaks_by_block = _peak_fields_by_block(
        indexed_turns,
        sources,
        evaluated_layers=evaluated_layers,
    )
    roxie_numbers = {
        (layer_index, block_index): roxie_block
        for roxie_block, (layer_index, block_index) in enumerate(
            (
                (layer_index, block_index)
                for layer_index, layer in enumerate(design.layers)
                for block_index, _block in enumerate(layer.blocks)
            ),
            start=1,
        )
    }
    records: list[BlockMarginRecord] = []
    for (layer_index, block_index), (limiting_turn, peak_field_t) in sorted(
        peaks_by_block.items()
    ):
        operating_current_a = abs(limiting_turn.turn.current_a)
        if operating_current_a == 0.0:
            raise ValueError("operating current must be nonzero")
        layer_data = cadata_by_layer[layer_index]
        k_field_per_current = peak_field_t / operating_current_a
        short_sample_current_a = solve_short_sample_current(
            layer_data.remfit,
            layer_data.strand,
            layer_data.cable,
            temperature_k,
            k_field_per_current,
            i_hi=_load_line_upper_bracket(
                layer_data.remfit,
                temperature_k,
                k_field_per_current,
            ),
        )
        records.append(
            BlockMarginRecord(
                layer_index=layer_index,
                block_index=block_index,
                roxie_block=roxie_numbers[(layer_index, block_index)],
                peak_field_t=peak_field_t,
                operating_current_a=operating_current_a,
                short_sample_current_a=short_sample_current_a,
                margin_percent=load_line_margin_percent(
                    operating_current_a, short_sample_current_a
                ),
            )
        )
    return tuple(records)


def _margin_layer_indices(
    design: DipoleDesign,
    cadata_by_layer: tuple[LayerConductorData, ...],
) -> tuple[int, ...]:
    if len(cadata_by_layer) != len(design.layers):
        raise ValueError("load-line margin requires one conductor-data record per layer")
    if any(layer_data is None for layer_data in cadata_by_layer):
        raise ValueError("load-line margin requires supported conductor data for every layer")
    return tuple(range(len(cadata_by_layer)))


def _design_sources(
    design: DipoleDesign,
    filaments_per_axis: int = 3,
    quadrature: str = "midpoint",
):
    return tuple(
        source
        for turn in design.all_turns()
        for source in place_line_current_sources(
            turn,
            n1=filaments_per_axis,
            n2=filaments_per_axis,
            quadrature=quadrature,
        )
    )


def _peak_field_on_own_turns(
    design: DipoleDesign,
    *,
    evaluated_layers: tuple[int, ...] | None = None,
) -> tuple[_IndexedTurn, float]:
    indexed_turns = _conductor_turns_by_layer(design)
    sources = _near_field_source_array(indexed_turns)
    return _peak_field_on_indexed_turns(indexed_turns, sources, evaluated_layers=evaluated_layers)


def _peak_field_on_indexed_turns(
    indexed_turns: tuple[_IndexedTurn, ...],
    sources: LineCurrentSourceArray,
    *,
    evaluated_layers: tuple[int, ...] | None = None,
) -> tuple[_IndexedTurn, float]:
    evaluated_layer_set = set(evaluated_layers) if evaluated_layers is not None else None
    best_turn: _IndexedTurn | None = None
    best_field = -math.inf
    candidates: list[tuple[_IndexedTurn, Point]] = []
    for indexed in indexed_turns:
        if evaluated_layer_set is not None and indexed.layer_index not in evaluated_layer_set:
            continue
        candidates.extend((indexed, point) for point in _turn_boundary_sample_points(indexed.turn))
    if not candidates:
        raise ValueError("could not compute a finite peak field on turns")
    bx_t, by_t = field_at_many(
        sources,
        tuple(point[0] for _, point in candidates),
        tuple(point[1] for _, point in candidates),
    )
    for (indexed, _), bx, by in zip(candidates, bx_t, by_t, strict=True):
        magnitude = math.hypot(float(bx), float(by))
        if magnitude > best_field:
            best_turn = indexed
            best_field = magnitude
    if best_turn is None or not math.isfinite(best_field):
        raise ValueError("could not compute a finite peak field on turns")
    return best_turn, best_field


def _peak_fields_by_layer(
    indexed_turns: tuple[_IndexedTurn, ...],
    sources: LineCurrentSourceArray,
    *,
    evaluated_layers: tuple[int, ...],
) -> dict[int, tuple[_IndexedTurn, float]]:
    """Find every requested layer peak with one vectorized field evaluation."""

    evaluated = set(evaluated_layers)
    candidates: list[tuple[_IndexedTurn, Point]] = []
    for indexed in indexed_turns:
        if indexed.layer_index in evaluated:
            candidates.extend(
                (indexed, point) for point in _turn_boundary_sample_points(indexed.turn)
            )
    if not candidates:
        raise ValueError("could not compute a finite peak field on turns")
    bx_t, by_t = field_at_many(
        sources,
        tuple(point[0] for _, point in candidates),
        tuple(point[1] for _, point in candidates),
    )
    peaks: dict[int, tuple[_IndexedTurn, float]] = {}
    for (indexed, _), bx, by in zip(candidates, bx_t, by_t, strict=True):
        magnitude = math.hypot(float(bx), float(by))
        previous = peaks.get(indexed.layer_index)
        if previous is None or magnitude > previous[1]:
            peaks[indexed.layer_index] = (indexed, magnitude)
    missing = evaluated.difference(peaks)
    if missing:
        raise ValueError(f"could not compute peak field for layers {sorted(missing)!r}")
    return peaks


def _peak_fields_by_block(
    indexed_turns: tuple[_IndexedTurn, ...],
    sources: LineCurrentSourceArray,
    *,
    evaluated_layers: tuple[int, ...],
) -> dict[tuple[int, int], tuple[_IndexedTurn, float]]:
    """Find every requested active-block peak with one field evaluation."""

    evaluated = set(evaluated_layers)
    candidates: list[tuple[_IndexedTurn, Point]] = []
    for indexed in indexed_turns:
        if indexed.layer_index in evaluated:
            candidates.extend(
                (indexed, point) for point in _turn_boundary_sample_points(indexed.turn)
            )
    if not candidates:
        raise ValueError("could not compute a finite peak field on turns")
    bx_t, by_t = field_at_many(
        sources,
        tuple(point[0] for _, point in candidates),
        tuple(point[1] for _, point in candidates),
    )
    peaks: dict[tuple[int, int], tuple[_IndexedTurn, float]] = {}
    for (indexed, _), bx, by in zip(candidates, bx_t, by_t, strict=True):
        magnitude = math.hypot(float(bx), float(by))
        key = (indexed.layer_index, indexed.block_index)
        previous = peaks.get(key)
        if previous is None or magnitude > previous[1]:
            peaks[key] = (indexed, magnitude)
    return peaks


def _near_field_sources(indexed_turns: tuple[_IndexedTurn, ...]):
    return tuple(
        source
        for indexed in indexed_turns
        for source in place_line_current_sources(
            indexed.turn,
            n1=PEAK_FIELD_FILAMENTS_PER_AXIS,
            n2=PEAK_FIELD_FILAMENTS_PER_AXIS,
        )
    )


def _near_field_source_array(
    indexed_turns: tuple[_IndexedTurn, ...],
    filaments_per_axis: int = PEAK_FIELD_FILAMENTS_PER_AXIS,
) -> LineCurrentSourceArray:
    compact_x: list[np.ndarray] = []
    compact_y: list[np.ndarray] = []
    compact_current: list[np.ndarray] = []
    u, v = _filament_cell_centers(filaments_per_axis, filaments_per_axis)
    for indexed in indexed_turns:
        x, y = _bilinear_arrays(indexed.turn.corners, u, v)
        compact_x.append(x)
        compact_y.append(y)
        compact_current.append(
            np.full(
                x.shape,
                indexed.turn.current_a / (filaments_per_axis * filaments_per_axis),
            )
        )
    x_mm = np.concatenate(compact_x)
    y_mm = np.concatenate(compact_y)
    current_a = np.concatenate(compact_current)
    return LineCurrentSourceArray.from_arrays(
        np.concatenate((x_mm, -x_mm, -x_mm, x_mm)),
        np.concatenate((y_mm, y_mm, -y_mm, -y_mm)),
        np.concatenate((current_a, -current_a, -current_a, current_a)),
    )


def _filament_cell_centers(n1: int, n2: int) -> tuple[np.ndarray, np.ndarray]:
    v = (np.arange(n1, dtype=np.float64) + 0.5) / n1
    u = (np.arange(n2, dtype=np.float64) + 0.5) / n2
    uu, vv = np.meshgrid(u, v)
    return (uu.ravel(), vv.ravel())


def _bilinear_arrays(
    corners: tuple[Point, Point, Point, Point],
    u: np.ndarray,
    v: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    p00, p10, p11, p01 = corners
    one_u = 1.0 - u
    one_v = 1.0 - v
    return (
        one_u * one_v * p00[0] + u * one_v * p10[0] + u * v * p11[0] + one_u * v * p01[0],
        one_u * one_v * p00[1] + u * one_v * p10[1] + u * v * p11[1] + one_u * v * p01[1],
    )


def _conductor_turns_by_layer(design: DipoleDesign) -> tuple[_IndexedTurn, ...]:
    return tuple(
        _IndexedTurn(
            layer_index=layer_index,
            block_index=block_index,
            turn=_conductor_turn(turn, block.alpha_deg, block.cable),
        )
        for layer_index, layer in enumerate(design.layers)
        for block_index, block in enumerate(layer.blocks)
        for turn in block.turns()
    )


def _conductor_turn(turn: TurnPolygon, alpha_deg: float, cable: CableSpec) -> TurnPolygon:
    # Generated turns retain their exact per-turn frame.  The fallback keeps
    # legacy hand-built polygon fixtures working, but production winding paths
    # no longer reuse the block's first-turn alpha for every keystoned turn.
    turn_alpha_deg = turn.alpha_deg if turn.alpha_deg is not None else alpha_deg
    inner_anchor = turn.anchor if turn.anchor is not None else _inner_face_anchor(turn, cable)
    return TurnPolygon.from_anchor(
        anchor=inner_anchor,
        alpha_deg=turn_alpha_deg,
        cable=_bare_cable(cable),
        current_a=turn.current_a,
    )


def _inner_face_anchor(turn: TurnPolygon, cable: CableSpec) -> Point:
    if math.isclose(cable.width_inner_mm, cable.width_outer_mm, rel_tol=0.0, abs_tol=1.0e-12):
        inner_minus, inner_plus = turn.corners[0], turn.corners[1]
        return ((inner_minus[0] + inner_plus[0]) / 2.0, (inner_minus[1] + inner_plus[1]) / 2.0)
    return turn.corners[0]


def _bare_cable(cable: CableSpec) -> CableSpec:
    return CableSpec(
        width_inner_mm=cable.width_inner_mm,
        width_outer_mm=cable.width_outer_mm,
        height_mm=cable.height_mm,
    )


def _load_line_upper_bracket(
    coeffs: RemfitCoefficients,
    temperature_k: float,
    k_field_per_current: float,
) -> float:
    bc2_t = upper_critical_field(coeffs, temperature_k)
    domain_upper = bc2_t / k_field_per_current
    return math.nextafter(domain_upper * (1.0 - 1.0e-12), 0.0)


def _turn_boundary_sample_points(turn: TurnPolygon) -> tuple[Point, ...]:
    """Sample each bare-conductor edge at quarter intervals.

    Corners plus edge midpoints can miss the peak between adjacent turns in a
    multi-turn keystoned block.  Quarter-edge samples close that ROXIE parity
    gap while keeping the vectorized certification cost bounded.  The end of
    each edge is omitted because it is the start of the next edge.
    """

    fractions = (0.0, 0.25, 0.5, 0.75)
    corners = turn.corners
    return tuple(
        (
            start[0] * (1.0 - fraction) + end[0] * fraction,
            start[1] * (1.0 - fraction) + end[1] * fraction,
        )
        for start, end in zip(corners, (*corners[1:], corners[0]), strict=True)
        for fraction in fractions
    )
