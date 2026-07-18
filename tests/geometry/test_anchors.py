from __future__ import annotations

import math

import pytest

from dot.geometry import CableSpec, midplane_anchors_from_gaps


def test_midplane_anchors_reproduce_cth_test2_gap_geometry() -> None:
    hf = CableSpec(
        width_inner_mm=1.53,
        width_outer_mm=1.658,
        height_mm=18.363,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )
    lf = CableSpec(
        width_inner_mm=1.736,
        width_outer_mm=2.084,
        height_mm=16.17,
        insulation_radial_mm=0.145,
        insulation_azimuthal_mm=0.145,
    )

    anchors = midplane_anchors_from_gaps(
        25.0,
        (hf, hf, lf, lf),
        (0.15, 0.15, 0.15, 0.15),
        (0.5, 0.5, 0.5),
    )

    assert [row[0] for row in anchors] == pytest.approx(
        (25.0, 44.15255, 63.305295, 80.265118), abs=1.0e-6
    )
    assert [row[1] for row in anchors] == pytest.approx(
        (0.34377055, 0.19465091, 0.13576038, 0.10707462), abs=1.0e-7
    )
    assert all(row[2] == 0.0 for row in anchors)
    assert anchors[0][1] == pytest.approx(math.degrees(math.atan(0.15 / 25.0)))


def test_midplane_anchors_reject_gap_count_mismatch() -> None:
    cable = CableSpec(width_mm=1.0, height_mm=2.0)

    with pytest.raises(ValueError, match="azimuthal gaps must contain one value per layer"):
        midplane_anchors_from_gaps(10.0, (cable, cable), (0.1,), (0.5,))

    with pytest.raises(ValueError, match="one value per layer interface"):
        midplane_anchors_from_gaps(10.0, (cable, cable), (0.1, 0.1), ())


def test_midplane_anchors_accept_legacy_zero_first_gap_only() -> None:
    cable = CableSpec(width_mm=1.0, height_mm=2.0)

    canonical = midplane_anchors_from_gaps(
        10.0,
        (cable, cable),
        (0.1, 0.1),
        (0.5,),
    )
    legacy = midplane_anchors_from_gaps(
        10.0,
        (cable, cable),
        (0.1, 0.1),
        (0.0, 0.5),
    )

    assert legacy == canonical
    with pytest.raises(ValueError, match="Layer 1 has no radial gap"):
        midplane_anchors_from_gaps(10.0, (cable, cable), (0.1, 0.1), (0.2, 0.5))
