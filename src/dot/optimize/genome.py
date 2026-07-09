"""Genome encoding for fixed-topology coil optimization.

The topology is fixed by the caller: layer count, block count per layer, and
the cable assigned to each layer are not search variables.  The genome stores
one continuous inner radius per layer and, per block, one continuous azimuthal
angle plus one integer turn count.  Block ``alpha_deg`` is fixed to zero here as
an intentional simplification for the first optimizer core.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from dot.geometry import Block, CableSpec, DipoleDesign, Layer


@dataclass(frozen=True, slots=True)
class LayerTopology:
    """Fixed topology and variable bounds for one coil layer."""

    cable_id: str
    n_blocks: int
    inner_radius_bounds_mm: tuple[float, float]
    phi_bounds_deg: tuple[float, float]
    n_turns_bounds: tuple[int, int]

    def __post_init__(self) -> None:
        if not self.cable_id:
            raise ValueError("cable_id must be non-empty")
        _require_positive_int(self.n_blocks, "n_blocks")
        _require_ordered_float_bounds(self.inner_radius_bounds_mm, "inner_radius_bounds_mm")
        _require_ordered_float_bounds(self.phi_bounds_deg, "phi_bounds_deg")
        lower, upper = self.n_turns_bounds
        _require_positive_int(lower, "n_turns_bounds lower")
        _require_positive_int(upper, "n_turns_bounds upper")
        if lower > upper:
            raise ValueError("n_turns_bounds lower must be <= upper")


@dataclass(frozen=True, slots=True)
class Topology:
    """Fixed layer/block/cable topology plus global design constants."""

    aperture_radius_mm: float
    layers: tuple[LayerTopology, ...]
    cables: Mapping[str, CableSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_finite_positive(self.aperture_radius_mm, "aperture_radius_mm")
        if not self.layers:
            raise ValueError("topology must contain at least one layer")

    @property
    def n_var(self) -> int:
        return sum(1 + 2 * layer.n_blocks for layer in self.layers)


def encode(design: DipoleDesign) -> np.ndarray:
    """Encode a fixed-topology ``DipoleDesign`` into a flat genome array."""

    values: list[float] = []
    for layer in design.layers:
        values.append(layer.inner_radius_mm)
        for block in layer.blocks:
            values.append(block.phi_deg)
            values.append(float(block.n_turns))
    return np.asarray(values, dtype=float)


def decode(
    genome_array: Sequence[float],
    topology: Topology,
    cable_map: Mapping[str, CableSpec] | None = None,
) -> DipoleDesign:
    """Decode a flat genome into a unit-current ``DipoleDesign``.

    ``n_turns`` slots are rounded to the nearest integer and clipped to the
    layer bounds.  Decoded block currents are placeholders of ``1.0 A``; the
    true operating current is applied later by ``operating_point``.
    """

    values = np.asarray(genome_array, dtype=float)
    if values.shape != (topology.n_var,):
        raise ValueError(f"genome must have shape ({topology.n_var},), got {values.shape}")

    cables = topology.cables if cable_map is None else cable_map
    layers: list[Layer] = []
    index = 0
    for layer_topology in topology.layers:
        inner_radius_mm = float(values[index])
        _require_finite(inner_radius_mm, "inner_radius_mm")
        index += 1
        cable = cables[layer_topology.cable_id]
        blocks: list[Block] = []
        for _ in range(layer_topology.n_blocks):
            phi_deg = float(values[index])
            _require_finite(phi_deg, "phi_deg")
            raw_turns = values[index + 1]
            _require_finite(float(raw_turns), "n_turns")
            n_turns = int(round(float(raw_turns)))
            n_turns = min(
                layer_topology.n_turns_bounds[1],
                max(layer_topology.n_turns_bounds[0], n_turns),
            )
            blocks.append(
                Block(
                    phi_deg=phi_deg,
                    alpha_deg=0.0,
                    n_turns=n_turns,
                    cable=cable,
                    inner_radius_mm=inner_radius_mm,
                    current_a=1.0,
                )
            )
            index += 2
        layers.append(Layer(inner_radius_mm=inner_radius_mm, blocks=tuple(blocks)))
    return DipoleDesign(aperture_radius_mm=topology.aperture_radius_mm, layers=tuple(layers))


def genome_bounds(topology: Topology) -> tuple[np.ndarray, np.ndarray]:
    """Return lower and upper genome bounds in pymoo's flat-vector format."""

    lower: list[float] = []
    upper: list[float] = []
    for layer in topology.layers:
        lower.append(layer.inner_radius_bounds_mm[0])
        upper.append(layer.inner_radius_bounds_mm[1])
        for _ in range(layer.n_blocks):
            lower.extend((layer.phi_bounds_deg[0], float(layer.n_turns_bounds[0])))
            upper.extend((layer.phi_bounds_deg[1], float(layer.n_turns_bounds[1])))
    return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_finite_positive(value: float, name: str) -> None:
    _require_finite(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _require_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _require_ordered_float_bounds(bounds: tuple[float, float], name: str) -> None:
    lower, upper = bounds
    _require_finite(lower, f"{name} lower")
    _require_finite(upper, f"{name} upper")
    if lower > upper:
        raise ValueError(f"{name} lower must be <= upper")
