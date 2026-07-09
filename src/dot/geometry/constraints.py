"""Geometry feasibility constraints for one-quadrant dipole designs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator

from .primitives import DipoleDesign, Point, TurnPolygon

_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Violation:
    """One structured geometry constraint violation."""

    constraint_name: str
    message: str
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
                    layer_index=outer_layer_index,
                    other_layer_index=inner_layer_index,
                )
            )
    return violations


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
                violations.append(
                    Violation(
                        constraint_name="turn_non_intersection",
                        message=(
                            "Turn polygons have positive-area overlap: "
                            f"L{left.layer_index}/B{left.block_index}/T{left.turn_index} "
                            f"with L{right.layer_index}/B{right.block_index}/T{right.turn_index}."
                        ),
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
    max_angle_deg: float,
) -> list[Violation]:
    """Check no turn outer edge exceeds the angular winding limit from the pole."""

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        outer_edge = indexed.turn.corners[2], indexed.turn.corners[3]
        max_outer_angle = max(_angle_from_y_axis_deg(point) for point in outer_edge)
        if max_outer_angle > max_angle_deg + _EPSILON:
            violations.append(
                Violation(
                    constraint_name="pole_angle_limit",
                    message=(
                        f"Turn outer edge angle {max_outer_angle:.6g} deg "
                        f"exceeds limit {max_angle_deg:.6g} deg."
                    ),
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
    max_angle_deg: float,
    min_layer_clearance_mm: float = 0.1,
) -> FeasibilityResult:
    """Run all geometry feasibility constraints and aggregate violations."""

    violations: list[Violation] = []
    violations.extend(check_aperture_clearance(design, aperture_radius_mm))
    violations.extend(check_inter_layer_spacing(design, min_layer_clearance_mm))
    violations.extend(check_midplane_clearance(design, min_gap_mm))
    violations.extend(check_turn_non_intersection(design))
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
