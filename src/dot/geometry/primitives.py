"""One-quadrant coil geometry primitives.

The angle ``phi_deg`` is measured clockwise from the positive y-axis toward
positive x.  Thus ``phi_deg = 0`` lies on the pole axis and ``phi_deg = 90``
lies on the midplane.  A turn is anchored at the midpoint of its inner face.
The turn anchor remains defined by ``inner_radius_mm`` and ``phi_deg``.  ROXIE's
``alpha`` convention is absolute in the global x-y plane: the cable height axis
depends only on ``alpha_deg``, not on the turn's polar angle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .cable import CableSpec

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class TurnPolygon:
    """Four corner points of one turn cross-section and its current."""

    corners: tuple[Point, Point, Point, Point]
    current_a: float

    @classmethod
    def from_parameters(
        cls,
        *,
        inner_radius_mm: float,
        phi_deg: float,
        alpha_deg: float,
        cable: CableSpec,
        current_a: float,
    ) -> "TurnPolygon":
        _require_finite_positive(inner_radius_mm, "inner_radius_mm")
        _require_finite(phi_deg, "phi_deg")
        _require_finite(alpha_deg, "alpha_deg")
        _require_finite(current_a, "current_a")

        phi = math.radians(phi_deg)
        radial = (math.sin(phi), math.cos(phi))
        anchor = (inner_radius_mm * radial[0], inner_radius_mm * radial[1])
        return cls.from_anchor(
            anchor=anchor,
            alpha_deg=alpha_deg,
            cable=cable,
            current_a=current_a,
        )

    @classmethod
    def from_anchor(
        cls,
        *,
        anchor: Point,
        alpha_deg: float,
        cable: CableSpec,
        current_a: float,
    ) -> "TurnPolygon":
        _require_finite(anchor[0], "anchor x")
        _require_finite(anchor[1], "anchor y")
        _require_finite(alpha_deg, "alpha_deg")
        _require_finite(current_a, "current_a")

        alpha = math.radians(alpha_deg)
        height_axis, width_axis = _turn_axes(alpha)
        half_width = 0.5 * cable.insulated_width_mm
        height = cable.insulated_height_mm

        inner_minus = _add(anchor, _scale(width_axis, -half_width))
        inner_plus = _add(anchor, _scale(width_axis, half_width))
        outer_plus = _add(inner_plus, _scale(height_axis, height))
        outer_minus = _add(inner_minus, _scale(height_axis, height))
        return cls(
            corners=(inner_minus, inner_plus, outer_plus, outer_minus),
            current_a=current_a,
        )

    def __post_init__(self) -> None:
        if len(self.corners) != 4:
            raise ValueError("corners must contain exactly four points")
        for point in self.corners:
            if len(point) != 2:
                raise ValueError("each corner must be an (x, y) point")
            _require_finite(point[0], "corner x")
            _require_finite(point[1], "corner y")
        _require_finite(self.current_a, "current_a")


@dataclass(frozen=True, slots=True)
class Block:
    """A block of turns wound azimuthally at fixed inner radius."""

    phi_deg: float
    alpha_deg: float
    n_turns: int
    cable: CableSpec
    inner_radius_mm: float
    current_a: float

    def turns(self) -> tuple[TurnPolygon, ...]:
        _require_positive_int(self.n_turns, "n_turns")
        _require_finite_positive(self.inner_radius_mm, "inner_radius_mm")
        _require_finite(self.phi_deg, "phi_deg")
        _require_finite(self.alpha_deg, "alpha_deg")
        phi = math.radians(self.phi_deg)
        turn_0_anchor = (
            self.inner_radius_mm * math.sin(phi),
            self.inner_radius_mm * math.cos(phi),
        )
        height_axis, width_axis = _turn_axes(math.radians(self.alpha_deg))
        final_width_coordinate = _dot(turn_0_anchor, width_axis) + (
            (self.n_turns - 1) * self.cable.insulated_width_mm
        )
        if abs(final_width_coordinate) <= self.inner_radius_mm:
            delta_phi_deg = math.degrees(self.cable.insulated_width_mm / self.inner_radius_mm)
            return tuple(
                TurnPolygon.from_parameters(
                    inner_radius_mm=self.inner_radius_mm,
                    phi_deg=self.phi_deg - index * delta_phi_deg,
                    alpha_deg=self.alpha_deg,
                    cable=self.cable,
                    current_a=self.current_a,
                )
                for index in range(self.n_turns)
            )

        return tuple(
            TurnPolygon.from_anchor(
                anchor=_arc_stacked_anchor(
                    turn_0_anchor=turn_0_anchor,
                    height_axis=height_axis,
                    width_axis=width_axis,
                    inner_radius_mm=self.inner_radius_mm,
                    width_offset_mm=index * self.cable.insulated_width_mm,
                ),
                alpha_deg=self.alpha_deg,
                cable=self.cable,
                current_a=self.current_a,
            )
            for index in range(self.n_turns)
        )


@dataclass(frozen=True, slots=True)
class Layer:
    """A set of blocks sharing one nominal inner radius."""

    inner_radius_mm: float
    blocks: tuple[Block, ...]

    def turns(self) -> tuple[TurnPolygon, ...]:
        return tuple(turn for block in self.blocks for turn in block.turns())


@dataclass(frozen=True, slots=True)
class DipoleDesign:
    """One-quadrant dipole coil layout."""

    aperture_radius_mm: float
    layers: tuple[Layer, ...]

    def all_turns(self) -> tuple[TurnPolygon, ...]:
        return tuple(turn for layer in self.layers for turn in layer.turns())


def _turn_axes(alpha_rad: float) -> tuple[Point, Point]:
    height_axis = (math.cos(alpha_rad), -math.sin(alpha_rad))
    width_axis = (math.sin(alpha_rad), math.cos(alpha_rad))
    return height_axis, width_axis


def _arc_stacked_anchor(
    *,
    turn_0_anchor: Point,
    height_axis: Point,
    width_axis: Point,
    inner_radius_mm: float,
    width_offset_mm: float,
) -> Point:
    width_coordinate = _dot(turn_0_anchor, width_axis) + width_offset_mm
    width_coordinate = _clamp(width_coordinate, -inner_radius_mm, inner_radius_mm)
    height_coordinate_0 = _dot(turn_0_anchor, height_axis)
    height_sign = 1.0 if height_coordinate_0 >= 0.0 else -1.0
    height_coordinate = height_sign * math.sqrt(
        max(0.0, inner_radius_mm * inner_radius_mm - width_coordinate * width_coordinate)
    )
    return _add(
        _scale(width_axis, width_coordinate),
        _scale(height_axis, height_coordinate),
    )


def _dot(left: Point, right: Point) -> float:
    return left[0] * right[0] + left[1] * right[1]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _scale(vector: Point, factor: float) -> Point:
    return (vector[0] * factor, vector[1] * factor)


def _add(left: Point, right: Point) -> Point:
    return (left[0] + right[0], left[1] + right[1])


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_finite_positive(value: float, name: str) -> None:
    _require_finite(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _require_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
