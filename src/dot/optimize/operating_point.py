"""Exact linear current scaling for no-iron dipole physics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from dot.geometry import Block, DipoleDesign, Layer
from dot.physics import field_at, place_line_current_sources


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    """Solved operating point for a decoded unit-current design."""

    unit_bore_field_t: float
    scale_factor: float
    operating_current_a: float
    design: DipoleDesign


def operating_point(unit_current_design: DipoleDesign, target_bore_field_t: float) -> OperatingPoint:
    """Scale a uniform-series-current design to the requested center ``By``.

    With no iron, the field is exactly linear in current by superposition, so
    ``target_bore_field_t / By(input current)`` is the exact scale factor.
    Unit-current decoded designs remain the usual input, but already-scaled
    already-scaled candidates are supported without losing their actual current.
    """

    if not math.isfinite(target_bore_field_t):
        raise ValueError("target_bore_field_t must be finite")
    sources = tuple(
        source
        for turn in unit_current_design.all_turns()
        for source in place_line_current_sources(turn)
    )
    _, by_t = field_at(sources, 0.0, 0.0)
    if by_t == 0.0 or not math.isfinite(by_t):
        raise ValueError("unit-current bore field must be finite and nonzero")
    scale_factor = target_bore_field_t / by_t
    block_currents = [
        block.current_a
        for layer in unit_current_design.layers
        for block in layer.blocks
    ]
    if not block_currents:
        raise ValueError("design must contain at least one block")
    reference_current = block_currents[0]
    if any(
        not math.isclose(current, reference_current, rel_tol=1.0e-10, abs_tol=1.0e-10)
        for current in block_currents[1:]
    ):
        raise ValueError("all blocks must carry the same series current")
    scaled_design = scale_design_currents(unit_current_design, scale_factor)
    return OperatingPoint(
        unit_bore_field_t=by_t,
        scale_factor=scale_factor,
        operating_current_a=reference_current * scale_factor,
        design=scaled_design,
    )


def scale_design_currents(design: DipoleDesign, scale_factor: float) -> DipoleDesign:
    """Return a copy of ``design`` with every block current multiplied."""

    if not math.isfinite(scale_factor):
        raise ValueError("scale_factor must be finite")
    layers: list[Layer] = []
    for layer in design.layers:
        blocks = tuple(
            Block(
                phi_deg=block.phi_deg,
                alpha_deg=block.alpha_deg,
                n_turns=block.n_turns,
                cable=block.cable,
                inner_radius_mm=block.inner_radius_mm,
                current_a=block.current_a * scale_factor,
            )
            for block in layer.blocks
        )
        layers.append(Layer(inner_radius_mm=layer.inner_radius_mm, blocks=blocks))
    return DipoleDesign(aperture_radius_mm=design.aperture_radius_mm, layers=tuple(layers))
