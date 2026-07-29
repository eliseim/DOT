"""Designer-facing radial alignment measures for conductor blocks."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .primitives import Block, DipoleDesign, Point, TurnPolygon


@dataclass(frozen=True, slots=True)
class BlockRadiality:
    """Alignment of a block's central cable with its local radial direction."""

    layer_index: int
    block_index: int
    center_turn_indices: tuple[int, ...]
    center_phi_deg: float
    center_alpha_deg: float
    deviation_deg: float


@dataclass(frozen=True, slots=True)
class RadialitySummary:
    """Aggregate central-cable alignment for one complete design."""

    mean_deviation_deg: float
    rms_deviation_deg: float
    max_deviation_deg: float
    blocks: tuple[BlockRadiality, ...]


def block_radiality(
    block: Block,
    *,
    layer_index: int = 0,
    block_index: int = 0,
) -> BlockRadiality:
    """Measure the middle cable, or the two middle cables for an even block.

    ``phi`` is the polar angle of the insulated cable polygon centroid.
    ``alpha`` is the cable-height-axis angle retained by :class:`TurnPolygon`.
    Cable orientation is an axis, so the reported absolute difference is
    reduced modulo 180 degrees.
    """

    turns = block.turns()
    if not turns:
        raise ValueError("a block must contain at least one turn")
    if len(turns) % 2:
        indices = (len(turns) // 2,)
    else:
        indices = (len(turns) // 2 - 1, len(turns) // 2)
    selected = tuple(turns[index] for index in indices)
    phi_deg = _mean_position_angle_deg(tuple(_polygon_centroid(turn) for turn in selected))
    alpha_values = tuple(_turn_alpha_deg(turn) for turn in selected)
    alpha_deg = _mean_axis_angle_deg(alpha_values)
    deviation_deg = abs(_axis_difference_deg(phi_deg, alpha_deg))
    return BlockRadiality(
        layer_index=layer_index,
        block_index=block_index,
        center_turn_indices=indices,
        center_phi_deg=phi_deg,
        center_alpha_deg=alpha_deg,
        deviation_deg=deviation_deg,
    )


def radiality_summary(
    design: DipoleDesign,
    *,
    include_midplane_blocks: bool = True,
) -> RadialitySummary:
    """Return mean, RMS, maximum, and per-block radial deviations.

    The first block of every layer has a fixed cable-frame angle in DOT.
    Optimization code therefore sets ``include_midplane_blocks=False`` when
    comparing layouts: a preference must not reward or punish a quantity the
    search cannot change.  Reports retain the default and show every block.
    """

    records = tuple(
        block_radiality(
            block,
            layer_index=layer_index,
            block_index=block_index,
        )
        for layer_index, layer in enumerate(design.layers)
        for block_index, block in enumerate(layer.blocks)
        if include_midplane_blocks or block_index > 0
    )
    if not records:
        return RadialitySummary(0.0, 0.0, 0.0, ())
    deviations = tuple(record.deviation_deg for record in records)
    return RadialitySummary(
        mean_deviation_deg=sum(deviations) / len(deviations),
        rms_deviation_deg=math.sqrt(
            sum(deviation * deviation for deviation in deviations) / len(deviations)
        ),
        max_deviation_deg=max(deviations),
        blocks=records,
    )


def radialized_block_alpha_deg(
    block: Block,
    alpha_bounds_deg: tuple[float, float],
    *,
    max_iterations: int = 12,
    tolerance_deg: float = 1.0e-7,
) -> float:
    """Find a bounded first-turn alpha that radially aligns the central cable.

    A short fixed-point iteration is sufficient because changing ``alpha``
    rotates the cable axis directly while the central cable position changes
    only weakly through arc stacking. If the requested alignment lies outside
    the allowed alpha interval, the closest bound is returned.
    """

    lower, upper = (float(alpha_bounds_deg[0]), float(alpha_bounds_deg[1]))
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError("alpha_bounds_deg must be finite and ordered")
    alpha = min(max(float(block.alpha_deg), lower), upper)
    for _ in range(max_iterations):
        record = block_radiality(replace(block, alpha_deg=alpha))
        signed_error = _axis_difference_deg(
            record.center_phi_deg,
            record.center_alpha_deg,
        )
        if abs(signed_error) <= tolerance_deg:
            break
        updated = min(max(alpha + signed_error, lower), upper)
        if math.isclose(updated, alpha, rel_tol=0.0, abs_tol=tolerance_deg):
            alpha = updated
            break
        alpha = updated
    return alpha


def _turn_alpha_deg(turn: TurnPolygon) -> float:
    if turn.alpha_deg is None:
        raise ValueError("turn alpha is required for radiality evaluation")
    return float(turn.alpha_deg)


def _polygon_centroid(turn: TurnPolygon) -> Point:
    corners = turn.corners
    twice_area = 0.0
    cx_numerator = 0.0
    cy_numerator = 0.0
    for start, end in zip(corners, corners[1:] + corners[:1], strict=True):
        cross = start[0] * end[1] - end[0] * start[1]
        twice_area += cross
        cx_numerator += (start[0] + end[0]) * cross
        cy_numerator += (start[1] + end[1]) * cross
    if math.isclose(twice_area, 0.0, rel_tol=0.0, abs_tol=1.0e-15):
        return (
            sum(point[0] for point in corners) / len(corners),
            sum(point[1] for point in corners) / len(corners),
        )
    scale = 1.0 / (3.0 * twice_area)
    return cx_numerator * scale, cy_numerator * scale


def _mean_position_angle_deg(points: tuple[Point, ...]) -> float:
    angles = tuple(math.atan2(y, x) for x, y in points)
    return math.degrees(
        math.atan2(
            sum(math.sin(angle) for angle in angles),
            sum(math.cos(angle) for angle in angles),
        )
    )


def _mean_axis_angle_deg(angles_deg: tuple[float, ...]) -> float:
    doubled = tuple(math.radians(2.0 * angle) for angle in angles_deg)
    return 0.5 * math.degrees(
        math.atan2(
            sum(math.sin(angle) for angle in doubled),
            sum(math.cos(angle) for angle in doubled),
        )
    )


def _axis_difference_deg(left_deg: float, right_deg: float) -> float:
    return (left_deg - right_deg + 90.0) % 180.0 - 90.0
