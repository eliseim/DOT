"""Line-current source placement."""

from __future__ import annotations

import math
from dataclasses import dataclass

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
) -> tuple[LineCurrentSource, ...]:
    """Discretize one turn into ``n1`` by ``n2`` equal-current filaments.

    ``n1`` subdivides the inner-to-outer height direction and ``n2`` subdivides
    the cable-width direction.  The source position is the bilinear cell center
    and each source carries ``turn.current_a / (n1 * n2)``.
    """

    _require_positive_int(n1, "n1")
    _require_positive_int(n2, "n2")
    source_current = turn.current_a / (n1 * n2)
    sources: list[LineCurrentSource] = []
    for row in range(n1):
        v = (row + 0.5) / n1
        for column in range(n2):
            u = (column + 0.5) / n2
            x, y = _bilinear(turn.corners, u, v)
            sources.append(LineCurrentSource(x, y, source_current))
    return tuple(sources)


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
