"""Optimization objective functions."""

from __future__ import annotations

import math
from dataclasses import dataclass

from dot.conductors import (
    CableRecord,
    StrandRecord,
    Type1FitCoefficients,
    load_line_margin_percent,
    solve_short_sample_current,
)
from dot.geometry import DipoleDesign, Point, TurnPolygon
from dot.physics import field_at, multipole_coefficients, place_line_current_sources


@dataclass(frozen=True, slots=True)
class LayerConductorData:
    """Critical-current records assigned to one geometry layer."""

    strand: StrandRecord
    cable: CableRecord
    remfit: Type1FitCoefficients


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
    cadata_by_layer: tuple[LayerConductorData, ...],
    temperature_k: float,
) -> float:
    """Return load-line current margin percent for the peak-field turn proxy.

    The field-limiting location is the sampled turn boundary point with the
    largest magnetic-field magnitude.  Its layer selects the conductor records,
    and ``B_peak / I_operating`` defines the load-line slope.
    """

    del cable_specs_by_layer
    limiting_turn, peak_field_t = _peak_field_on_own_turns(design)
    operating_current_a = abs(limiting_turn.turn.current_a)
    if operating_current_a == 0.0:
        raise ValueError("operating current must be nonzero")
    if limiting_turn.layer_index >= len(cadata_by_layer):
        raise ValueError("missing conductor data for limiting layer")
    layer_data = cadata_by_layer[limiting_turn.layer_index]
    short_sample_current_a = solve_short_sample_current(
        layer_data.remfit,
        layer_data.strand,
        layer_data.cable,
        temperature_k,
        peak_field_t / operating_current_a,
    )
    return load_line_margin_percent(operating_current_a, short_sample_current_a)


def _design_sources(design: DipoleDesign):
    return tuple(source for turn in design.all_turns() for source in place_line_current_sources(turn))


def _peak_field_on_own_turns(design: DipoleDesign) -> tuple[_IndexedTurn, float]:
    sources = _design_sources(design)
    best_turn: _IndexedTurn | None = None
    best_field = -math.inf
    for layer_index, layer in enumerate(design.layers):
        for block in layer.blocks:
            for turn in block.turns():
                indexed = _IndexedTurn(layer_index=layer_index, turn=turn)
                for x_mm, y_mm in _turn_boundary_sample_points(turn):
                    bx_t, by_t = field_at(sources, x_mm, y_mm)
                    magnitude = math.hypot(bx_t, by_t)
                    if magnitude > best_field:
                        best_turn = indexed
                        best_field = magnitude
    if best_turn is None or not math.isfinite(best_field):
        raise ValueError("could not compute a finite peak field on turns")
    return best_turn, best_field


def _turn_boundary_sample_points(turn: TurnPolygon) -> tuple[Point, ...]:
    corners = turn.corners
    edge_midpoints = tuple(
        ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        for start, end in zip(corners, (*corners[1:], corners[0]), strict=True)
    )
    return (*corners, *edge_midpoints)
