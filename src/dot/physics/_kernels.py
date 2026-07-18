"""Compiled serial numerical kernels for field evaluation."""

from __future__ import annotations

import numpy as np

from dot.acceleration import compiled


@compiled
def biot_savart_many(
    source_x_mm: np.ndarray,
    source_y_mm: np.ndarray,
    source_current_a: np.ndarray,
    probe_x_mm: np.ndarray,
    probe_y_mm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Evaluate explicit line currents without dense probe/source matrices."""

    mu0_over_2pi = 2.0e-7
    mm_to_m = 1.0e-3
    bx_t = np.zeros(probe_x_mm.size, dtype=np.float64)
    by_t = np.zeros(probe_x_mm.size, dtype=np.float64)
    singular = False
    for probe_index in range(probe_x_mm.size):
        bx_value = 0.0
        by_value = 0.0
        for source_index in range(source_x_mm.size):
            dx_m = (probe_x_mm[probe_index] - source_x_mm[source_index]) * mm_to_m
            dy_m = (probe_y_mm[probe_index] - source_y_mm[source_index]) * mm_to_m
            rho2_m2 = dx_m * dx_m + dy_m * dy_m
            if rho2_m2 == 0.0:
                singular = True
                continue
            scale = mu0_over_2pi * source_current_a[source_index] / rho2_m2
            bx_value -= scale * dy_m
            by_value += scale * dx_m
        bx_t[probe_index] = bx_value
        by_t[probe_index] = by_value
    return bx_t, by_t, singular
