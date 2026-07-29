from __future__ import annotations

import math

import pytest

from dot.geometry import TurnPolygon
from dot.physics import place_line_current_sources


def test_sources_are_bilinear_cell_centers_with_equal_current() -> None:
    turn = TurnPolygon(
        corners=((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)),
        current_a=120.0,
    )

    sources = place_line_current_sources(turn, n1=2, n2=2)

    assert [(source.x_mm, source.y_mm) for source in sources] == [
        (1.0, 0.5),
        (3.0, 0.5),
        (1.0, 1.5),
        (3.0, 1.5),
    ]
    assert all(math.isclose(source.current_a, 30.0) for source in sources)


def test_gauss_legendre_sources_preserve_current_and_integrate_quadratic_moment() -> None:
    turn = TurnPolygon(
        corners=((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)),
        current_a=120.0,
    )

    sources = place_line_current_sources(
        turn,
        n1=3,
        n2=3,
        quadrature="gauss-legendre",
    )

    assert len(sources) == 9
    assert sum(source.current_a for source in sources) == pytest.approx(120.0)
    weighted_x2 = sum(source.current_a * source.x_mm**2 for source in sources) / 120.0
    assert weighted_x2 == pytest.approx(16.0 / 3.0)


def test_sources_reject_unknown_quadrature() -> None:
    turn = TurnPolygon(
        corners=((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)),
        current_a=120.0,
    )

    with pytest.raises(ValueError, match="quadrature"):
        place_line_current_sources(turn, quadrature="unknown")
