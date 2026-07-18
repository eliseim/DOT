from __future__ import annotations

import math

from dot.conductors import (
    CableRecord,
    StrandRecord,
    cable_critical_current,
    strand_critical_current,
)


def test_strand_and_cable_critical_current_use_non_copper_area() -> None:
    strand = StrandRecord(diameter_mm=1.2, cu_to_sc_ratio=1.4)
    cable = CableRecord(n_strands=30, degradation_percent=5.0)
    jc_a_per_m2 = 2.5e9
    total_area_mm2 = math.pi * 1.2**2 / 4.0
    non_copper_area_m2 = total_area_mm2 / (1.0 + 1.4) * 1.0e-6
    expected_strand_ic = jc_a_per_m2 * non_copper_area_m2
    expected_cable_ic = expected_strand_ic * 30 * 0.95

    assert strand_critical_current(jc_a_per_m2, strand) == expected_strand_ic
    assert cable_critical_current(jc_a_per_m2, strand, cable) == expected_cable_ic
