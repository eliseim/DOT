"""Line-current source placement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from dot.geometry import Point, TurnPolygon


@dataclass(frozen=True, slots=True)
class LineCurrentSource:
    """One infinitely long z-directed line current."""

    x_mm: float
    y_mm: float
    current_a: float

    def __post_init__(self) -> None:
        for name, value in (
            ("x_mm", self.x_mm),
            ("y_mm", self.y_mm),
            ("current_a", self.current_a),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")

    @property
    def radius_mm(self) -> float:
        return math.hypot(self.x_mm, self.y_mm)


def place_line_current_sources(
    turn: TurnPolygon,
    n1: int = 3,
    n2: int = 3,
    *,
    quadrature: str = "midpoint",
) -> tuple[LineCurrentSource, ...]:
    """Discretize one turn into an ``n1`` by ``n2`` current quadrature.

    ``n1`` subdivides the inner-to-outer height direction and ``n2`` subdivides
    the cable-width direction. ``midpoint`` preserves the traditional
    equal-current cell-centre grid. ``gauss-legendre`` uses tensor-product
    Gauss-Legendre nodes and weights on the same bilinear turn coordinates;
    it resolves smooth bore multipoles much more accurately for the same
    filament count. Near-field/load-line calculations continue to use the
    midpoint grid because singular-field sampling has different convergence
    behaviour.
    """

    _require_positive_int(n1, "n1")
    _require_positive_int(n2, "n2")
    height_axis = _quadrature_axis(n1, quadrature)
    width_axis = _quadrature_axis(n2, quadrature)
    sources: list[LineCurrentSource] = []
    for v, height_weight in height_axis:
        for u, width_weight in width_axis:
            x, y = _bilinear(turn.corners, u, v)
            sources.append(
                LineCurrentSource(
                    x,
                    y,
                    turn.current_a * height_weight * width_weight,
                )
            )
    return tuple(sources)


@lru_cache(maxsize=32)
def _quadrature_axis(order: int, quadrature: str) -> tuple[tuple[float, float], ...]:
    if quadrature == "midpoint":
        weight = 1.0 / order
        return tuple(((index + 0.5) / order, weight) for index in range(order))
    if quadrature == "gauss-legendre":
        nodes, weights = np.polynomial.legendre.leggauss(order)
        return tuple(
            (float((node + 1.0) / 2.0), float(weight / 2.0))
            for node, weight in zip(nodes, weights, strict=True)
        )
    raise ValueError("quadrature must be 'midpoint' or 'gauss-legendre'")


def _bilinear(corners: tuple[Point, Point, Point, Point], u: float, v: float) -> Point:
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


def _require_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
