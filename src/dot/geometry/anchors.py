"""Derive user-facing midplane block anchors from physical gaps."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .cable import CableSpec
from .primitives import TurnPolygon


def midplane_anchors_from_gaps(
    aperture_radius_mm: float,
    cables_by_layer: Sequence[CableSpec],
    azimuthal_gaps_mm: Sequence[float],
    radial_gaps_mm: Sequence[float],
) -> tuple[tuple[float, float, float], ...]:
    """Return ``(R, phi, alpha)`` for every first block.

    The Layer-1 radius is the physical aperture radius.  For each following
    layer, the new radius is the outermost x coordinate of the previous
    layer's first insulated turn plus the requested radial gap. There is one
    radial-gap value per interface, so an N-layer coil supplies N-1 values;
    Layer 1 has no radial gap because its radius is the aperture radius. The ROXIE
    midplane angle follows the designer convention requested by DOT:
    ``phi = atan(azimuthal_gap / R)`` and ``alpha = 0``.
    """

    if not math.isfinite(aperture_radius_mm) or aperture_radius_mm <= 0.0:
        raise ValueError("aperture_radius_mm must be finite and positive")
    cables = tuple(cables_by_layer)
    azimuthal = tuple(float(value) for value in azimuthal_gaps_mm)
    radial = tuple(float(value) for value in radial_gaps_mm)
    if not cables:
        raise ValueError("at least one cable is required")
    if len(azimuthal) != len(cables):
        raise ValueError("azimuthal gaps must contain one value per layer")
    if len(radial) == len(cables):
        # Backward compatibility for saved pre-0.1 callers that supplied an
        # unused zero for Layer 1. New callers should provide only interfaces.
        if radial[0] != 0.0:
            raise ValueError("Layer 1 has no radial gap; its R is the aperture radius")
        radial = radial[1:]
    if len(radial) != len(cables) - 1:
        raise ValueError("radial gaps must contain one value per layer interface")
    for name, values in (("azimuthal gap", azimuthal), ("radial gap", radial)):
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError(f"every {name} must be finite and non-negative")

    anchors: list[tuple[float, float, float]] = []
    radius = aperture_radius_mm
    for layer_index, cable in enumerate(cables):
        if layer_index > 0:
            previous_radius, previous_phi, _ = anchors[-1]
            previous_turn = TurnPolygon.from_parameters(
                inner_radius_mm=previous_radius,
                phi_deg=previous_phi,
                alpha_deg=0.0,
                cable=cables[layer_index - 1],
                current_a=1.0,
            )
            radius = max(x for x, _y in previous_turn.corners) + radial[layer_index - 1]
        phi_deg = math.degrees(math.atan2(azimuthal[layer_index], radius))
        anchors.append((radius, phi_deg, 0.0))
    return tuple(anchors)
