"""Geometry feasibility constraints for one-quadrant dipole designs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Iterator

from .primitives import DipoleDesign, Point, TurnPolygon

_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Violation:
    """One structured geometry constraint violation.

    ``severity`` is the positive amount past the constraint boundary in the
    constraint's native unit: millimeters for clearance/overlap constraints
    and degrees for angular constraints. Satisfied constraints still do not
    emit a violation.
    """

    constraint_name: str
    message: str
    severity: float = 0.0
    layer_index: int | None = None
    block_index: int | None = None
    turn_index: int | None = None
    other_layer_index: int | None = None
    other_block_index: int | None = None
    other_turn_index: int | None = None


@dataclass(frozen=True, slots=True)
class FeasibilityResult:
    """Aggregate feasibility result for a dipole design."""

    is_feasible: bool
    violations: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class _IndexedTurn:
    layer_index: int
    block_index: int
    turn_index: int
    turn: TurnPolygon


def check_aperture_clearance(
    design: DipoleDesign,
    aperture_radius_mm: float,
) -> list[Violation]:
    """Check that no turn intrudes into the circular beam aperture."""

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        clearance = _distance_origin_to_polygon(indexed.turn.corners) - aperture_radius_mm
        if clearance < -_EPSILON:
            violations.append(
                Violation(
                    constraint_name="aperture_clearance",
                    message=(
                        "Turn intrudes into the circular aperture: "
                        f"clearance {clearance:.6g} mm < 0 mm."
                    ),
                    severity=-clearance,
                    layer_index=indexed.layer_index,
                    block_index=indexed.block_index,
                    turn_index=indexed.turn_index,
                )
            )
    return violations


def check_inter_layer_spacing(
    design: DipoleDesign,
    min_clearance_mm: float = 0.1,
) -> list[Violation]:
    """Check consecutive layers have the required radial clearance."""

    violations: list[Violation] = []
    non_empty_layers = [
        (layer_index, turns)
        for layer_index in range(len(design.layers))
        if (turns := tuple(_iter_layer_turns(design, layer_index)))
    ]
    for (inner_layer_index, inner_turns), (outer_layer_index, outer_turns) in zip(
        non_empty_layers,
        non_empty_layers[1:],
        strict=False,
    ):

        inner_outer_radius = max(
            _max_vertex_radius(indexed.turn.corners) for indexed in inner_turns
        )
        outer_inner_radius = min(
            _distance_origin_to_polygon(indexed.turn.corners) for indexed in outer_turns
        )
        required_radius = inner_outer_radius + min_clearance_mm
        if outer_inner_radius < required_radius - _EPSILON:
            violations.append(
                Violation(
                    constraint_name="inter_layer_spacing",
                    message=(
                        f"Layer {outer_layer_index} starts at radius "
                        f"{outer_inner_radius:.6g} mm, below required "
                        f"{required_radius:.6g} mm after layer "
                        f"{inner_layer_index}."
                    ),
                    severity=required_radius - outer_inner_radius,
                    layer_index=outer_layer_index,
                    other_layer_index=inner_layer_index,
                )
            )
    return violations


def check_layer_nesting(design: DipoleDesign) -> list[Violation]:
    """Check each layer nests below the previous layer's pole-most conductor.

    DOT's counterpart to dipole_designer's C10: a physical windability
    check independent of radial spacing (:func:`check_inter_layer_spacing`).
    Take the inner layer's pole-most block's pole-side turn edge (the
    stacking direction confirmed, via live ROXIE, to point toward the pole
    as turn index increases -- see task 0031), prolong it into an infinite
    line, and require every vertex of the outer layer's turns to stay on
    the same side as the origin. A vertex crossing to the far side means
    the outer layer cannot physically nest over the inner layer's winding.
    """

    violations: list[Violation] = []
    non_empty_layers = [
        (layer_index, turns)
        for layer_index in range(len(design.layers))
        if (turns := tuple(_iter_layer_turns(design, layer_index)))
    ]
    for (inner_layer_index, inner_turns), (outer_layer_index, outer_turns) in zip(
        non_empty_layers,
        non_empty_layers[1:],
        strict=False,
    ):
        edge = _layer_pole_side_nesting_edge(inner_turns)
        if edge is None:
            continue
        p1, p2 = edge
        edge_length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if edge_length <= _EPSILON:
            continue
        origin_side = _signed_half_plane_value(p1, p2, (0.0, 0.0))
        if abs(origin_side) <= _EPSILON:
            continue
        accepted_sign = 1.0 if origin_side >= 0.0 else -1.0
        for indexed in outer_turns:
            for vertex in indexed.turn.corners:
                distance = accepted_sign * _signed_half_plane_value(p1, p2, vertex) / edge_length
                if distance < -_EPSILON:
                    violations.append(
                        Violation(
                            constraint_name="layer_nesting",
                            message=(
                                f"Layer {outer_layer_index} conductor extends "
                                f"{-distance:.6g} mm past the prolonged pole-side "
                                f"edge of layer {inner_layer_index}'s pole-most "
                                "conductor -- it cannot physically nest over it."
                            ),
                            severity=-distance,
                            layer_index=outer_layer_index,
                            block_index=indexed.block_index,
                            turn_index=indexed.turn_index,
                            other_layer_index=inner_layer_index,
                        )
                    )
    return violations


def _layer_pole_side_nesting_edge(
    layer_turns: tuple[_IndexedTurn, ...],
) -> tuple[Point, Point] | None:
    if not layer_turns:
        return None
    pole_most_block_index = min(
        {indexed.block_index for indexed in layer_turns},
        key=lambda block_index: min(
            _angle_from_y_axis_deg(vertex)
            for indexed in layer_turns
            if indexed.block_index == block_index
            for vertex in indexed.turn.corners
        ),
    )
    block_turns = [indexed for indexed in layer_turns if indexed.block_index == pole_most_block_index]
    pole_most_turn = max(indexed.turn_index for indexed in block_turns)
    last_turn = next(indexed.turn for indexed in block_turns if indexed.turn_index == pole_most_turn)
    return last_turn.corners[1], last_turn.corners[2]


def check_midplane_clearance(
    design: DipoleDesign,
    min_gap_mm: float,
) -> list[Violation]:
    """Check every turn remains at least ``min_gap_mm`` above y=0."""

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        min_y = min(y for _, y in indexed.turn.corners)
        if min_y < min_gap_mm - _EPSILON:
            violations.append(
                Violation(
                    constraint_name="midplane_clearance",
                    message=(
                        f"Turn one-sided midplane clearance {min_y:.6g} mm "
                        f"is below required {min_gap_mm:.6g} mm."
                    ),
                    severity=min_gap_mm - min_y,
                    layer_index=indexed.layer_index,
                    block_index=indexed.block_index,
                    turn_index=indexed.turn_index,
                )
            )
    return violations


def check_pole_clearance(
    design: DipoleDesign,
    min_gap_mm: float,
) -> list[Violation]:
    """Check every turn remains at least ``min_gap_mm`` clear of x=0 (the pole axis).

    The pole-side counterpart to :func:`check_midplane_clearance`: no turn
    may cross into the adjacent quadrant through the y-axis, mirroring the
    fixed-mm pole gap convention used by ROXIE-consistent designs (distinct
    from any angular pole-edge limit).
    """

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        min_x = min(x for x, _ in indexed.turn.corners)
        if min_x < min_gap_mm - _EPSILON:
            violations.append(
                Violation(
                    constraint_name="pole_clearance",
                    message=(
                        f"Turn one-sided pole clearance {min_x:.6g} mm "
                        f"is below required {min_gap_mm:.6g} mm."
                    ),
                    severity=min_gap_mm - min_x,
                    layer_index=indexed.layer_index,
                    block_index=indexed.block_index,
                    turn_index=indexed.turn_index,
                )
            )
    return violations


def check_turn_non_intersection(design: DipoleDesign) -> list[Violation]:
    """Check all turn quadrilaterals are free of positive-area overlap."""

    violations: list[Violation] = []
    turns = tuple(_iter_indexed_turns(design))
    for left_index, left in enumerate(turns):
        for right in turns[left_index + 1 :]:
            if _convex_polygons_overlap(left.turn.corners, right.turn.corners):
                overlap_depth = _convex_polygon_overlap_depth(left.turn.corners, right.turn.corners)
                violations.append(
                    Violation(
                        constraint_name="turn_non_intersection",
                        message=(
                            "Turn polygons have positive-area overlap: "
                            f"L{left.layer_index}/B{left.block_index}/T{left.turn_index} "
                            f"with L{right.layer_index}/B{right.block_index}/T{right.turn_index}."
                        ),
                        severity=overlap_depth,
                        layer_index=left.layer_index,
                        block_index=left.block_index,
                        turn_index=left.turn_index,
                        other_layer_index=right.layer_index,
                        other_block_index=right.block_index,
                        other_turn_index=right.turn_index,
                    )
                )
    return violations


def check_inter_block_gap(
    design: DipoleDesign,
    min_gap_mm: float,
) -> list[Violation]:
    """Check turns from different blocks in the same layer clear a minimum gap.

    ``check_turn_non_intersection`` only rejects actual positive-area
    overlap (gap < 0); it says nothing about two blocks close enough that
    there is no physical room for the insulation/wedge between them. This
    is the counterpart to dipole_designer's C7 (electrical/wedge
    inter-block gap) -- a minimum *positive* clearance, checked only
    between turns of different blocks within the same layer (turns in
    different layers are already governed by
    :func:`check_inter_layer_spacing`).
    """

    violations: list[Violation] = []
    turns = tuple(_iter_indexed_turns(design))
    for left_index, left in enumerate(turns):
        for right in turns[left_index + 1 :]:
            if left.layer_index != right.layer_index or left.block_index == right.block_index:
                continue
            if _convex_polygons_overlap(left.turn.corners, right.turn.corners):
                continue
            gap = _convex_polygon_distance(left.turn.corners, right.turn.corners)
            if gap < min_gap_mm - _EPSILON:
                violations.append(
                    Violation(
                        constraint_name="inter_block_gap",
                        message=(
                            f"Inter-block clearance {gap:.6g} mm is below required "
                            f"{min_gap_mm:.6g} mm: "
                            f"L{left.layer_index}/B{left.block_index}/T{left.turn_index} "
                            f"with L{right.layer_index}/B{right.block_index}/T{right.turn_index}."
                        ),
                        severity=min_gap_mm - gap,
                        layer_index=left.layer_index,
                        block_index=left.block_index,
                        turn_index=left.turn_index,
                        other_layer_index=right.layer_index,
                        other_block_index=right.block_index,
                        other_turn_index=right.turn_index,
                    )
                )
    return violations


def check_pole_angle_limit(
    design: DipoleDesign,
    max_angle_deg: float | Sequence[float],
) -> list[Violation]:
    """Check no turn outer edge exceeds the angular winding limit from the pole."""

    limits = _max_angle_by_layer(design, max_angle_deg)
    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        layer_limit = limits[indexed.layer_index]
        outer_edge = indexed.turn.corners[2], indexed.turn.corners[3]
        max_outer_angle = max(_angle_from_y_axis_deg(point) for point in outer_edge)
        if max_outer_angle > layer_limit + _EPSILON:
            violations.append(
                Violation(
                    constraint_name="pole_angle_limit",
                    message=(
                        f"Turn outer edge angle {max_outer_angle:.6g} deg "
                        f"exceeds limit {layer_limit:.6g} deg."
                    ),
                    severity=max_outer_angle - layer_limit,
                    layer_index=indexed.layer_index,
                    block_index=indexed.block_index,
                    turn_index=indexed.turn_index,
                )
            )
    return violations


def check_feasibility(
    design: DipoleDesign,
    *,
    aperture_radius_mm: float,
    min_gap_mm: float,
    max_angle_deg: float | Sequence[float],
    min_layer_clearance_mm: float = 0.1,
    min_pole_gap_mm: float | None = None,
    min_inter_block_gap_mm: float | None = None,
    enforce_layer_nesting: bool = False,
) -> FeasibilityResult:
    """Run all geometry feasibility constraints and aggregate violations."""

    violations: list[Violation] = []
    violations.extend(check_aperture_clearance(design, aperture_radius_mm))
    violations.extend(check_inter_layer_spacing(design, min_layer_clearance_mm))
    violations.extend(check_midplane_clearance(design, min_gap_mm))
    if min_pole_gap_mm is not None:
        violations.extend(check_pole_clearance(design, min_pole_gap_mm))
    violations.extend(check_turn_non_intersection(design))
    if min_inter_block_gap_mm is not None:
        violations.extend(check_inter_block_gap(design, min_inter_block_gap_mm))
    if enforce_layer_nesting:
        violations.extend(check_layer_nesting(design))
    violations.extend(check_pole_angle_limit(design, max_angle_deg))
    return FeasibilityResult(is_feasible=not violations, violations=tuple(violations))


def _iter_indexed_turns(design: DipoleDesign) -> Iterator[_IndexedTurn]:
    for layer_index, layer in enumerate(design.layers):
        for block_index, block in enumerate(layer.blocks):
            for turn_index, turn in enumerate(block.turns()):
                yield _IndexedTurn(layer_index, block_index, turn_index, turn)


def _iter_layer_turns(design: DipoleDesign, layer_index: int) -> Iterator[_IndexedTurn]:
    layer = design.layers[layer_index]
    for block_index, block in enumerate(layer.blocks):
        for turn_index, turn in enumerate(block.turns()):
            yield _IndexedTurn(layer_index, block_index, turn_index, turn)


def _max_angle_by_layer(
    design: DipoleDesign,
    max_angle_deg: float | Sequence[float],
) -> tuple[float, ...]:
    if isinstance(max_angle_deg, Real):
        return tuple(float(max_angle_deg) for _ in design.layers)

    limits = tuple(float(limit) for limit in max_angle_deg)
    if len(limits) != len(design.layers):
        raise ValueError(
            "max_angle_deg sequence length must equal the number of design layers "
            f"({len(limits)} != {len(design.layers)})"
        )
    return limits


def _distance_origin_to_polygon(points: tuple[Point, ...]) -> float:
    origin = (0.0, 0.0)
    if _point_in_convex_polygon(origin, points):
        return 0.0
    return min(_distance_point_to_segment(origin, start, end) for start, end in _edges(points))


def _distance_point_to_segment(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= _EPSILON:
        return math.hypot(point[0] - start[0], point[1] - start[1])

    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    t = min(1.0, max(0.0, t))
    closest = (start[0] + t * dx, start[1] + t * dy)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _max_vertex_radius(points: tuple[Point, ...]) -> float:
    return max(math.hypot(x, y) for x, y in points)


def _convex_polygons_overlap(left: tuple[Point, ...], right: tuple[Point, ...]) -> bool:
    for axis in (*_edge_normals(left), *_edge_normals(right)):
        left_min, left_max = _project_onto_axis(left, axis)
        right_min, right_max = _project_onto_axis(right, axis)
        if min(left_max, right_max) - max(left_min, right_min) <= _EPSILON:
            return False
    return True


def _convex_polygon_overlap_depth(left: tuple[Point, ...], right: tuple[Point, ...]) -> float:
    depths = []
    for axis in (*_edge_normals(left), *_edge_normals(right)):
        left_min, left_max = _project_onto_axis(left, axis)
        right_min, right_max = _project_onto_axis(right, axis)
        depths.append(min(left_max, right_max) - max(left_min, right_min))
    return max(0.0, min(depths)) if depths else 0.0


def _convex_polygon_distance(left: tuple[Point, ...], right: tuple[Point, ...]) -> float:
    """Minimum distance between two disjoint (non-overlapping) convex polygons."""

    candidates = [
        _distance_point_to_segment(vertex, start, end)
        for vertex in left
        for start, end in _edges(right)
    ]
    candidates.extend(
        _distance_point_to_segment(vertex, start, end)
        for vertex in right
        for start, end in _edges(left)
    )
    return min(candidates)


def _edge_normals(points: tuple[Point, ...]) -> Iterator[Point]:
    for start, end in _edges(points):
        edge = (end[0] - start[0], end[1] - start[1])
        normal = (-edge[1], edge[0])
        length = math.hypot(*normal)
        if length > _EPSILON:
            yield (normal[0] / length, normal[1] / length)


def _project_onto_axis(points: tuple[Point, ...], axis: Point) -> tuple[float, float]:
    projections = tuple(point[0] * axis[0] + point[1] * axis[1] for point in points)
    return min(projections), max(projections)


def _signed_half_plane_value(p1: Point, p2: Point, q: Point) -> float:
    return (p2[0] - p1[0]) * (q[1] - p1[1]) - (p2[1] - p1[1]) * (q[0] - p1[0])


def _point_in_convex_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    sign = 0
    for start, end in _edges(polygon):
        cross = (end[0] - start[0]) * (point[1] - start[1]) - (
            end[1] - start[1]
        ) * (point[0] - start[0])
        if abs(cross) <= _EPSILON:
            continue
        current_sign = 1 if cross > 0.0 else -1
        if sign == 0:
            sign = current_sign
        elif sign != current_sign:
            return False
    return True


def _edges(points: tuple[Point, ...]) -> Iterator[tuple[Point, Point]]:
    yield from zip(points, (*points[1:], points[0]), strict=True)


def _angle_from_y_axis_deg(point: Point) -> float:
    return abs(math.degrees(math.atan2(point[0], point[1])))
