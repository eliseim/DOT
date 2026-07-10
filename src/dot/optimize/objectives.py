"""Optimization objective functions."""

from __future__ import annotations

import math
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
class LayerConductorData:
    """Critical-current records assigned to one geometry layer."""

    strand: StrandRecord
    cable: CableRecord
    remfit: RemfitCoefficients


@dataclass(frozen=True, slots=True)
class _IndexedTurn:
    layer_index: int
    turn: TurnPolygon


def field_quality_objective(design: DipoleDesign, r_ref_mm: float, max_order: int) -> float:
    """Return max relative harmonic magnitude over orders 2..``max_order``."""

    if max_order < 2:
        raise ValueError("max_order must be at least 2")
    sources = _design_sources(design)
    coefficients = multipole_coefficients(sources, order=max_order, r_ref_mm=r_ref_mm)
    return max(max(abs(b_n), abs(a_n)) for b_n, a_n in coefficients[1:])


def load_line_margin_objective(
    design: DipoleDesign,
    cable_specs_by_layer: object,
    cadata_by_layer: tuple[LayerConductorData | None, ...],
    temperature_k: float,
) -> float:
    """Return load-line current margin percent for the peak-field turn proxy.

    The field-limiting location is the sampled turn boundary point with the
    largest magnetic-field magnitude.  Its layer selects the conductor records,
    and ``B_peak / I_operating`` defines the load-line slope.
    """

    del cable_specs_by_layer
    evaluated_layers = tuple(index for index, layer_data in enumerate(cadata_by_layer) if layer_data is not None)
    if not evaluated_layers:
        raise ValueError("load-line margin requires conductor data for at least one layer")
    margins: list[float] = []
    indexed_turns = _conductor_turns_by_layer(design)
    sources = _near_field_source_array(indexed_turns)
    for layer_index in evaluated_layers:
        limiting_turn, peak_field_t = _peak_field_on_indexed_turns(
            indexed_turns,
            sources,
            evaluated_layers=(layer_index,),
        )
        operating_current_a = abs(limiting_turn.turn.current_a)
        if operating_current_a == 0.0:
            raise ValueError("operating current must be nonzero")
        layer_data = cadata_by_layer[layer_index]
        if layer_data is None:
            raise ValueError("missing conductor data for limiting layer")
        k_field_per_current = peak_field_t / operating_current_a
        short_sample_current_a = solve_short_sample_current(
            layer_data.remfit,
            layer_data.strand,
            layer_data.cable,
            temperature_k,
            k_field_per_current,
            i_hi=_load_line_upper_bracket(layer_data.remfit, temperature_k, k_field_per_current),
        )
        margins.append(load_line_margin_percent(operating_current_a, short_sample_current_a))
    return min(margins)


def _design_sources(design: DipoleDesign):
    return tuple(source for turn in design.all_turns() for source in place_line_current_sources(turn))


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


def _near_field_source_array(indexed_turns: tuple[_IndexedTurn, ...]) -> LineCurrentSourceArray:
    compact_x: list[np.ndarray] = []
    compact_y: list[np.ndarray] = []
    compact_current: list[np.ndarray] = []
    u, v = _filament_cell_centers(PEAK_FIELD_FILAMENTS_PER_AXIS, PEAK_FIELD_FILAMENTS_PER_AXIS)
    for indexed in indexed_turns:
        x, y = _bilinear_arrays(indexed.turn.corners, u, v)
        compact_x.append(x)
        compact_y.append(y)
        compact_current.append(
            np.full(
                x.shape,
                indexed.turn.current_a
                / (PEAK_FIELD_FILAMENTS_PER_AXIS * PEAK_FIELD_FILAMENTS_PER_AXIS),
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
        one_u * one_v * p00[0]
        + u * one_v * p10[0]
        + u * v * p11[0]
        + one_u * v * p01[0],
        one_u * one_v * p00[1]
        + u * one_v * p10[1]
        + u * v * p11[1]
        + one_u * v * p01[1],
    )


def _conductor_turns_by_layer(design: DipoleDesign) -> tuple[_IndexedTurn, ...]:
    return tuple(
        _IndexedTurn(layer_index=layer_index, turn=_conductor_turn(turn, block.alpha_deg, block.cable))
        for layer_index, layer in enumerate(design.layers)
        for block in layer.blocks
        for turn in block.turns()
    )


def _conductor_turn(turn: TurnPolygon, alpha_deg: float, cable: CableSpec) -> TurnPolygon:
    inner_anchor = _inner_face_anchor(turn, cable)
    return TurnPolygon.from_anchor(
        anchor=inner_anchor,
        alpha_deg=alpha_deg,
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
    corners = turn.corners
    edge_midpoints = tuple(
        ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        for start, end in zip(corners, (*corners[1:], corners[0]), strict=True)
    )
    return (*corners, *edge_midpoints)
