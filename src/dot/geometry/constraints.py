"""Geometry feasibility constraints for one-quadrant dipole designs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Iterator

from ._kernels import (
    convex_polygon_distance as _convex_polygon_distance,
    convex_polygon_overlap_depth as _convex_polygon_overlap_depth,
    convex_polygons_overlap as _convex_polygons_overlap,
)
from .primitives import DipoleDesign, Point, TurnPolygon

_EPSILON = 1e-9
DEFAULT_GEOMETRY_TOLERANCE_MM = 0.005


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
class InterBlockClearance:
    """Closest polygon-to-polygon distance for one pair of blocks.

    Indices are zero based in the physics API.  ``distance_mm`` is negative
    when the closest turn polygons overlap; otherwise it is the exact
    Euclidean distance between their closest points.
    """

    layer_index: int
    block_index: int
    other_block_index: int
    turn_index: int
    other_turn_index: int
    distance_mm: float


@dataclass(frozen=True, slots=True)
class _IndexedTurn:
    layer_index: int
    block_index: int
    turn_index: int
    turn: TurnPolygon


def check_aperture_clearance(
    design: DipoleDesign,
    aperture_radius_mm: float,
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Check that no turn intrudes into the circular beam aperture."""

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        clearance = _distance_origin_to_polygon(indexed.turn.corners) - aperture_radius_mm
        if clearance < -tolerance_mm:
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
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Check the specified radial spacer between consecutive layer mandrels.

    For generated windings, the radial gap is the difference between nominal
    layer radii after subtracting the inner layer cable's insulated radial
    height. This matches how ROXIE layer radii and inter-layer spacers are
    specified. Polygon collision remains an independent constraint. Hand-built
    polygon fixtures without cable metadata use local polygon distance.
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

        inner_layer = design.layers[inner_layer_index]
        outer_layer = design.layers[outer_layer_index]
        radial_heights = tuple(
            block.cable.insulated_height_mm
            for block in inner_layer.blocks
            if getattr(block, "cable", None) is not None
        )
        if radial_heights:
            gap = (
                outer_layer.inner_radius_mm
                - inner_layer.inner_radius_mm
                - max(radial_heights)
            )
            if gap < min_clearance_mm - tolerance_mm:
                violations.append(
                    Violation(
                        constraint_name="inter_layer_spacing",
                        message=(
                            f"Radial spacer between layers {inner_layer_index} and "
                            f"{outer_layer_index} is {gap:.6g} mm, below required "
                            f"{min_clearance_mm:.6g} mm."
                        ),
                        severity=min_clearance_mm - gap,
                        layer_index=outer_layer_index,
                        other_layer_index=inner_layer_index,
                    )
                )
            continue

        closest: tuple[float, _IndexedTurn, _IndexedTurn] | None = None
        for inner in inner_turns:
            for outer in outer_turns:
                if _convex_polygons_overlap(inner.turn.corners, outer.turn.corners):
                    gap = -_convex_polygon_overlap_depth(
                        inner.turn.corners, outer.turn.corners
                    )
                else:
                    gap = _convex_polygon_distance(inner.turn.corners, outer.turn.corners)
                if closest is None or gap < closest[0]:
                    closest = (gap, inner, outer)
        if closest is None:
            continue
        gap, inner, outer = closest
        if gap < min_clearance_mm - tolerance_mm:
            violations.append(
                Violation(
                    constraint_name="inter_layer_spacing",
                    message=(
                        f"Local clearance between layers {inner_layer_index} and "
                        f"{outer_layer_index} is {gap:.6g} mm, below required "
                        f"{min_clearance_mm:.6g} mm."
                    ),
                    severity=min_clearance_mm - gap,
                    layer_index=outer.layer_index,
                    block_index=outer.block_index,
                    turn_index=outer.turn_index,
                    other_layer_index=inner.layer_index,
                    other_block_index=inner.block_index,
                    other_turn_index=inner.turn_index,
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


def check_extended_lower_edge_nesting(design: DipoleDesign) -> list[Violation]:
    """Require outer layers below the prolonged lower side of the pole turn.

    This supplements the classical pole-side nesting line with the more
    conservative construction shown in ``corr2``: prolong the lower
    (midplane-side) long edge of the inner layer's pole-most turn and keep
    the complete next layer on the origin side of that line.
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
        edge = _layer_lower_side_nesting_edge(inner_turns)
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
                distance = (
                    accepted_sign
                    * _signed_half_plane_value(p1, p2, vertex)
                    / edge_length
                )
                if distance < -_EPSILON:
                    violations.append(
                        Violation(
                            constraint_name="extended_lower_edge_nesting",
                            message=(
                                f"Layer {outer_layer_index} conductor extends "
                                f"{-distance:.6g} mm past the prolonged lower side "
                                f"of layer {inner_layer_index}'s pole-most turn -- "
                                "the conservative winding envelope is violated."
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
    pole_most_block_index = max(
        {indexed.block_index for indexed in layer_turns},
        key=lambda block_index: max(
            _angle_from_midplane_deg(vertex)
            for indexed in layer_turns
            if indexed.block_index == block_index
            for vertex in indexed.turn.corners
        ),
    )
    block_turns = [indexed for indexed in layer_turns if indexed.block_index == pole_most_block_index]
    pole_most_turn = max(indexed.turn_index for indexed in block_turns)
    last_turn = next(indexed.turn for indexed in block_turns if indexed.turn_index == pole_most_turn)
    return last_turn.corners[1], last_turn.corners[2]


def _layer_lower_side_nesting_edge(
    layer_turns: tuple[_IndexedTurn, ...],
) -> tuple[Point, Point] | None:
    if not layer_turns:
        return None
    pole_most_block_index = max(
        {indexed.block_index for indexed in layer_turns},
        key=lambda block_index: max(
            _angle_from_midplane_deg(vertex)
            for indexed in layer_turns
            if indexed.block_index == block_index
            for vertex in indexed.turn.corners
        ),
    )
    block_turns = [
        indexed for indexed in layer_turns if indexed.block_index == pole_most_block_index
    ]
    pole_most_turn = max(indexed.turn_index for indexed in block_turns)
    last_turn = next(
        indexed.turn for indexed in block_turns if indexed.turn_index == pole_most_turn
    )
    return last_turn.corners[0], last_turn.corners[3]


def check_midplane_clearance(
    design: DipoleDesign,
    min_gap_mm: float,
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Check every turn remains at least ``min_gap_mm`` above y=0."""

    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        min_y = min(y for _, y in indexed.turn.corners)
        if min_y < min_gap_mm - tolerance_mm:
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
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
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
        if min_x < min_gap_mm - tolerance_mm:
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


def check_turn_non_intersection(
    design: DipoleDesign,
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Check all turn quadrilaterals are free of positive-area overlap."""

    violations: list[Violation] = []
    turns = tuple(_iter_indexed_turns(design))
    for left_index, left in enumerate(turns):
        for right in turns[left_index + 1 :]:
            if _convex_polygons_overlap(left.turn.corners, right.turn.corners):
                overlap_depth = _convex_polygon_overlap_depth(left.turn.corners, right.turn.corners)
                if overlap_depth <= tolerance_mm:
                    continue
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


#: dipole_designer's C7a electrical-insulation inter-block gap minimum (mm).
ELECTRICAL_GAP_MIN_MM = 0.10

#: dipole_designer's C7b manufacturability wedge inter-block gap minimum (mm).
WEDGE_GAP_MIN_MM = 1.0


def check_inter_block_gap(
    design: DipoleDesign,
    min_gap_mm: float | Sequence[float],
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Check turns from different blocks in the same layer clear a minimum gap.

    ``check_turn_non_intersection`` only rejects actual positive-area
    overlap (gap < 0); it says nothing about two blocks close enough that
    there is no physical room for the insulation/wedge between them. This
    is a general-purpose counterpart to dipole_designer's C7 (electrical/
    wedge inter-block gap) -- a minimum *positive* clearance, checked only
    between turns of different blocks within the same layer (turns in
    different layers are already governed by
    :func:`check_inter_layer_spacing`). See :func:`check_electrical_gap`
    and :func:`check_wedge_gap` for dd's exact two-tier thresholds.
    """

    return _inter_block_gap_violations(
        design, min_gap_mm, "inter_block_gap", tolerance_mm
    )


def check_electrical_gap(design: DipoleDesign, min_gap_mm: float = ELECTRICAL_GAP_MIN_MM) -> list[Violation]:
    """dd's C7a: minimum electrical-insulation gap between adjacent blocks."""

    return _inter_block_gap_violations(design, min_gap_mm, "electrical_gap")


def check_wedge_gap(design: DipoleDesign, min_gap_mm: float = WEDGE_GAP_MIN_MM) -> list[Violation]:
    """dd's C7b: minimum manufacturability wedge gap between adjacent blocks."""

    return _inter_block_gap_violations(design, min_gap_mm, "wedge_gap")


def _inter_block_gap_violations(
    design: DipoleDesign,
    min_gap_mm: float | Sequence[float],
    constraint_name: str,
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    limits = _value_by_layer(design, min_gap_mm, "min_gap_mm")
    violations: list[Violation] = []
    for clearance in inter_block_clearances(design):
        # Positive-area overlap belongs to check_turn_non_intersection and is
        # intentionally not double-reported as a gap violation.
        if clearance.distance_mm < 0.0:
            continue
        limit = limits[clearance.layer_index]
        if clearance.distance_mm < limit - tolerance_mm:
            violations.append(
                Violation(
                    constraint_name=constraint_name,
                    message=(
                        f"Closest-point clearance {clearance.distance_mm:.6g} mm is below "
                        f"the Layer {clearance.layer_index + 1} requirement {limit:.6g} mm: "
                        f"L{clearance.layer_index}/B{clearance.block_index}/"
                        f"T{clearance.turn_index} with L{clearance.layer_index}/"
                        f"B{clearance.other_block_index}/T{clearance.other_turn_index}."
                    ),
                    severity=limit - clearance.distance_mm,
                    layer_index=clearance.layer_index,
                    block_index=clearance.block_index,
                    turn_index=clearance.turn_index,
                    other_layer_index=clearance.layer_index,
                    other_block_index=clearance.other_block_index,
                    other_turn_index=clearance.other_turn_index,
                )
            )
    return violations


def first_layer_pole_turn_clearance_mm(design: DipoleDesign) -> float | None:
    """Return Layer 1's closest insulated-cable distance to the pole axis.

    DOT's pole symmetry axis is ``x=0``. If a turn polygon crosses that
    axis, its distance is zero; otherwise the distance is the smallest
    absolute vertex x-coordinate. The minimum is taken over Layer 1 only,
    because that layer defines the tightest pole-turn winding radius.
    """

    if not design.layers:
        return None
    closest: float | None = None
    for indexed in _iter_layer_turns(design, 0):
        x_values = tuple(x for x, _y in indexed.turn.corners)
        distance = (
            0.0
            if min(x_values) <= 0.0 <= max(x_values)
            else min(abs(x) for x in x_values)
        )
        closest = distance if closest is None else min(closest, distance)
    return closest


def check_first_layer_pole_turn_radius(
    design: DipoleDesign,
    min_radius_mm: float,
    tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> list[Violation]:
    """Require Layer 1's closest cable point to clear the pole axis.

    In DOT's straight-block 2D model this is a conservative proxy for the
    available pole-turn bend radius; an actual centerline curvature radius
    requires a coil-end/curved-path model outside DOT's present scope.
    """

    if not math.isfinite(min_radius_mm) or min_radius_mm < 0.0:
        raise ValueError("min_radius_mm must be finite and non-negative")
    if not design.layers:
        return []
    closest: tuple[float, _IndexedTurn] | None = None
    for indexed in _iter_layer_turns(design, 0):
        x_values = tuple(x for x, _y in indexed.turn.corners)
        distance = (
            0.0
            if min(x_values) <= 0.0 <= max(x_values)
            else min(abs(x) for x in x_values)
        )
        if closest is None or distance < closest[0]:
            closest = (distance, indexed)
    if closest is None or closest[0] >= min_radius_mm - tolerance_mm:
        return []
    distance, indexed = closest
    return [
        Violation(
            constraint_name="first_layer_pole_turn_radius",
            message=(
                f"Layer 1 pole-turn closest-point distance {distance:.6g} mm is below "
                f"the required radius proxy {min_radius_mm:.6g} mm."
            ),
            severity=min_radius_mm - distance,
            layer_index=0,
            block_index=indexed.block_index,
            turn_index=indexed.turn_index,
        )
    ]


def inter_block_clearances(design: DipoleDesign) -> tuple[InterBlockClearance, ...]:
    """Measure the closest turn-polygon distance for every same-layer block pair."""

    clearances: list[InterBlockClearance] = []
    for layer_index, layer in enumerate(design.layers):
        turns_by_block = [tuple(block.turns()) for block in layer.blocks]
        for block_index, left_turns in enumerate(turns_by_block):
            for other_block_index in range(block_index + 1, len(turns_by_block)):
                right_turns = turns_by_block[other_block_index]
                closest: tuple[float, int, int] | None = None
                for turn_index, left in enumerate(left_turns):
                    for other_turn_index, right in enumerate(right_turns):
                        if _convex_polygons_overlap(left.corners, right.corners):
                            distance = -_convex_polygon_overlap_depth(
                                left.corners, right.corners
                            )
                        else:
                            distance = _convex_polygon_distance(left.corners, right.corners)
                        if closest is None or distance < closest[0]:
                            closest = (distance, turn_index, other_turn_index)
                if closest is not None:
                    distance, turn_index, other_turn_index = closest
                    clearances.append(
                        InterBlockClearance(
                            layer_index=layer_index,
                            block_index=block_index,
                            other_block_index=other_block_index,
                            turn_index=turn_index,
                            other_turn_index=other_turn_index,
                            distance_mm=distance,
                        )
                    )
    return tuple(clearances)


def check_pole_angle_limit(
    design: DipoleDesign,
    max_angle_deg: float | Sequence[float],
) -> list[Violation]:
    """Legacy pole-edge limit in the native ROXIE phi convention.

    New campaigns use :func:`check_first_layer_pole_turn_radius` instead.
    This compatibility check simply requires every conductor vertex to stay
    below ``max_angle_deg`` measured from the midplane toward the pole.
    """

    limits = _max_angle_by_layer(design, max_angle_deg)
    violations: list[Violation] = []
    for indexed in _iter_indexed_turns(design):
        layer_limit = limits[indexed.layer_index]
        max_vertex_angle = max(
            _angle_from_midplane_deg(point) for point in indexed.turn.corners
        )
        if max_vertex_angle > layer_limit + _EPSILON:
            violations.append(
                Violation(
                    constraint_name="pole_angle_limit",
                    message=(
                        f"Turn vertex angle {max_vertex_angle:.6g} deg from the midplane "
                        f"exceeds the pole-edge limit {layer_limit:.6g} deg."
                    ),
                    severity=max_vertex_angle - layer_limit,
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
    max_angle_deg: float | Sequence[float] | None = None,
    min_layer_clearance_mm: float = 0.1,
    min_pole_gap_mm: float | None = None,
    min_pole_turn_radius_mm: float | None = None,
    min_inter_block_gap_mm: float | Sequence[float] | None = None,
    enforce_layer_nesting: bool = False,
    geometry_tolerance_mm: float = DEFAULT_GEOMETRY_TOLERANCE_MM,
) -> FeasibilityResult:
    """Run all geometry feasibility constraints and aggregate violations."""

    violations: list[Violation] = []
    if geometry_tolerance_mm < 0.0 or not math.isfinite(geometry_tolerance_mm):
        raise ValueError("geometry_tolerance_mm must be finite and non-negative")
    violations.extend(
        check_aperture_clearance(design, aperture_radius_mm, geometry_tolerance_mm)
    )
    violations.extend(
        check_inter_layer_spacing(
            design, min_layer_clearance_mm, geometry_tolerance_mm
        )
    )
    violations.extend(check_midplane_clearance(design, min_gap_mm, geometry_tolerance_mm))
    if min_pole_gap_mm is not None:
        violations.extend(
            check_pole_clearance(design, min_pole_gap_mm, geometry_tolerance_mm)
        )
    if min_pole_turn_radius_mm is not None:
        violations.extend(
            check_first_layer_pole_turn_radius(
                design,
                min_pole_turn_radius_mm,
                geometry_tolerance_mm,
            )
        )
    violations.extend(check_turn_non_intersection(design, geometry_tolerance_mm))
    if min_inter_block_gap_mm is not None:
        violations.extend(
            check_inter_block_gap(
                design, min_inter_block_gap_mm, geometry_tolerance_mm
            )
        )
    if enforce_layer_nesting:
        violations.extend(check_layer_nesting(design))
        violations.extend(check_extended_lower_edge_nesting(design))
    if max_angle_deg is not None:
        # Legacy compatibility only. New user workflows use the physical
        # first-layer pole-turn radius proxy above instead of an angle limit.
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


def _value_by_layer(
    design: DipoleDesign,
    value: float | Sequence[float],
    name: str,
) -> tuple[float, ...]:
    if isinstance(value, Real):
        values = tuple(float(value) for _ in design.layers)
    else:
        values = tuple(float(item) for item in value)
        if len(values) != len(design.layers):
            raise ValueError(
                f"{name} sequence length must equal the number of design layers "
                f"({len(values)} != {len(design.layers)})"
            )
    if any(not math.isfinite(item) or item < 0.0 for item in values):
        raise ValueError(f"{name} values must be finite and non-negative")
    return values


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


def _angle_from_midplane_deg(point: Point) -> float:
    return abs(math.degrees(math.atan2(point[1], point[0])))
