from __future__ import annotations

import math

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
