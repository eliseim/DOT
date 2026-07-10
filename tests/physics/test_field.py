from __future__ import annotations

import math

import numpy as np
import pytest

from dot.physics import LineCurrentSource, dipole_mirror_sources, field_at, field_at_explicit_sources
from dot.physics import field as field_module
from dot.physics.field import MU0_OVER_2PI, LineCurrentSourceArray, field_at_many_explicit_sources


@pytest.mark.parametrize(
    ("current_a", "distance_mm"),
    [(1000.0, 10.0), (5000.0, 50.0), (-2500.0, 25.0)],
)
def test_explicit_single_infinite_wire_matches_biot_savart(
    current_a: float,
    distance_mm: float,
) -> None:
    bx, by = field_at_explicit_sources(
        (LineCurrentSource(0.0, 0.0, current_a),),
        distance_mm,
        0.0,
    )

    expected_by = MU0_OVER_2PI * current_a / (distance_mm * 1.0e-3)
    assert bx == pytest.approx(0.0, abs=1e-15)
    assert by == pytest.approx(expected_by, rel=1e-12)
    assert math.hypot(bx, by) == pytest.approx(abs(expected_by), rel=1e-12)


def test_two_opposite_wires_above_and_below_have_closed_form_center_field() -> None:
    current_a = 7500.0
    distance_mm = 30.0
    sources = (
        LineCurrentSource(0.0, distance_mm, current_a),
        LineCurrentSource(0.0, -distance_mm, -current_a),
    )

    bx, by = field_at_explicit_sources(sources, 0.0, 0.0)

    expected_bx = 2.0 * MU0_OVER_2PI * current_a / (distance_mm * 1.0e-3)
    assert bx == pytest.approx(expected_bx, rel=1e-12)
    assert by == pytest.approx(0.0, abs=1e-15)


def test_dipole_mirror_sources_apply_expected_current_signs() -> None:
    images = dipole_mirror_sources(LineCurrentSource(3.0, 5.0, 7.0))

    assert images == (
        LineCurrentSource(3.0, 5.0, 7.0),
        LineCurrentSource(-3.0, 5.0, -7.0),
        LineCurrentSource(-3.0, -5.0, -7.0),
        LineCurrentSource(3.0, -5.0, 7.0),
    )


def test_mirror_orbit_has_normal_dipole_field_symmetry() -> None:
    source = LineCurrentSource(10.0, 20.0, 1000.0)

    bx, by = field_at((source,), 3.0, 4.0)
    bx_mx, by_mx = field_at((source,), -3.0, 4.0)
    bx_my, by_my = field_at((source,), 3.0, -4.0)
    bx_both, by_both = field_at((source,), -3.0, -4.0)

    assert bx_mx == pytest.approx(-bx, rel=1e-12)
    assert bx_my == pytest.approx(-bx, rel=1e-12)
    assert bx_both == pytest.approx(bx, rel=1e-12)
    assert by_mx == pytest.approx(by, rel=1e-12)
    assert by_my == pytest.approx(by, rel=1e-12)
    assert by_both == pytest.approx(by, rel=1e-12)


def test_explicit_many_sources_chunking_matches_single_dense_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    n_sources = 257
    sources = LineCurrentSourceArray.from_arrays(
        np.linspace(-35.0, 42.0, n_sources),
        np.linspace(18.0, -27.0, n_sources),
        np.linspace(100.0, 2500.0, n_sources),
    )
    x_probe = np.linspace(-12.0, 14.0, 11)
    y_probe = np.linspace(9.0, -8.0, 11)

    dense = field_at_many_explicit_sources(sources, x_probe, y_probe)

    monkeypatch.setattr(field_module, "FIELD_DENSE_INTERMEDIATE_LIMIT_BYTES", 5 * 8 * 11 * 17)
    chunked = field_at_many_explicit_sources(sources, x_probe, y_probe)

    np.testing.assert_allclose(chunked[0], dense[0], rtol=2e-15, atol=1e-15)
    np.testing.assert_allclose(chunked[1], dense[1], rtol=2e-15, atol=1e-15)
