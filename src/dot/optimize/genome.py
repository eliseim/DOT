"""Genome encoding for fixed-maximum-topology coil optimization.

The topology is fixed by the caller: layer count, maximum block count per layer,
and the cable assigned to each layer are not search variables.  The genome
stores one continuous inner radius per layer and, per block slot, one continuous
azimuthal angle plus one integer turn count.  The first block in each layer is
always active, has ``alpha_deg`` fixed to zero, and has no active or alpha genome
slot; later block slots store an active/inactive gene and one continuous
``alpha_deg`` value.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from pymoo.core.variable import Binary, Integer, Real

from dot.geometry import Block, CableSpec, DipoleDesign, Layer

DEFAULT_ALPHA_BOUNDS_DEG = (-10.0, 70.0)


@dataclass(frozen=True, slots=True)
class GenomeVariable:
    """Metadata for one flat genome slot."""

    name: str
    index: int
    kind: str
    bounds: tuple[float, float]
    layer_index: int
    block_index: int | None = None


@dataclass(frozen=True, slots=True)
class LayerTopology:
    """Maximum topology and variable bounds for one coil layer."""

    cable_id: str
    n_blocks: int
    inner_radius_bounds_mm: tuple[float, float]
    phi_bounds_deg: tuple[float, float]
    n_turns_bounds: tuple[int, int]
    alpha_bounds_deg: tuple[float, float] = DEFAULT_ALPHA_BOUNDS_DEG

    def __post_init__(self) -> None:
        if not self.cable_id:
            raise ValueError("cable_id must be non-empty")
        _require_positive_int(self.n_blocks, "n_blocks")
        _require_ordered_float_bounds(self.inner_radius_bounds_mm, "inner_radius_bounds_mm")
        _require_ordered_float_bounds(self.phi_bounds_deg, "phi_bounds_deg")
        _require_ordered_float_bounds(self.alpha_bounds_deg, "alpha_bounds_deg")
        lower, upper = self.n_turns_bounds
        _require_positive_int(lower, "n_turns_bounds lower")
        _require_positive_int(upper, "n_turns_bounds upper")
        if lower > upper:
            raise ValueError("n_turns_bounds lower must be <= upper")


@dataclass(frozen=True, slots=True)
class Topology:
    """Fixed layer/cable topology, maximum block counts, and design constants."""

    aperture_radius_mm: float
    layers: tuple[LayerTopology, ...]
    cables: Mapping[str, CableSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_finite_positive(self.aperture_radius_mm, "aperture_radius_mm")
        if not self.layers:
            raise ValueError("topology must contain at least one layer")

    @property
    def n_var(self) -> int:
        return sum(1 + 2 + 4 * (layer.n_blocks - 1) for layer in self.layers)


def encode(design: DipoleDesign, topology: Topology | None = None) -> np.ndarray:
    """Encode a ``DipoleDesign`` into a flat genome array.

    Without an explicit topology, every block present in the design is encoded
    as active, preserving the pre-optional-block calling convention.  With a
    topology, missing block slots are padded as inactive using that slot's lower
    bounds for the ignored phi/turn/alpha genes.
    """

    values: list[float] = []
    if topology is not None and len(design.layers) != len(topology.layers):
        raise ValueError("design layer count must match topology layer count")

    for layer_index, layer in enumerate(design.layers):
        layer_topology = None if topology is None else topology.layers[layer_index]
        if layer_topology is not None and len(layer.blocks) > layer_topology.n_blocks:
            raise ValueError("design has more blocks than topology maximum")
        values.append(layer.inner_radius_mm)
        max_blocks = len(layer.blocks) if layer_topology is None else layer_topology.n_blocks
        for block_index in range(max_blocks):
            if block_index < len(layer.blocks):
                block = layer.blocks[block_index]
                values.append(block.phi_deg)
                values.append(float(block.n_turns))
                if block_index > 0:
                    values.append(1.0)
                    values.append(block.alpha_deg)
                continue
            if layer_topology is None:
                break
            phi_lower, phi_upper = layer_topology.phi_bounds_deg
            window_width = (phi_upper - phi_lower) / layer_topology.n_blocks
            values.append(phi_lower + block_index * window_width)
            values.append(float(layer_topology.n_turns_bounds[0]))
            if block_index > 0:
                values.append(0.0)
                values.append(layer_topology.alpha_bounds_deg[0])
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
        for block_index in range(layer_topology.n_blocks):
            phi_deg = float(values[index])
            _require_finite(phi_deg, "phi_deg")
            raw_turns = values[index + 1]
            _require_finite(float(raw_turns), "n_turns")
            n_turns = int(round(float(raw_turns)))
            n_turns = min(
                layer_topology.n_turns_bounds[1],
                max(layer_topology.n_turns_bounds[0], n_turns),
            )
            index += 2
            if block_index == 0:
                is_active = True
                alpha_deg = 0.0
            else:
                raw_active = values[index]
                _require_finite(float(raw_active), "active")
                is_active = bool(int(round(float(raw_active))))
                index += 1
                alpha_deg = float(values[index])
                _require_finite(alpha_deg, "alpha_deg")
                index += 1
            if not is_active:
                continue
            blocks.append(
                Block(
                    phi_deg=phi_deg,
                    alpha_deg=alpha_deg,
                    n_turns=n_turns,
                    cable=cable,
                    inner_radius_mm=inner_radius_mm,
                    current_a=1.0,
                )
            )
        layers.append(Layer(inner_radius_mm=inner_radius_mm, blocks=tuple(blocks)))
    return DipoleDesign(aperture_radius_mm=topology.aperture_radius_mm, layers=tuple(layers))


def genome_bounds(topology: Topology) -> tuple[np.ndarray, np.ndarray]:
    """Return lower and upper genome bounds in pymoo's flat-vector format."""

    lower: list[float] = []
    upper: list[float] = []
    for layer in topology.layers:
        phi_lower, phi_upper = layer.phi_bounds_deg
        window_width = (phi_upper - phi_lower) / layer.n_blocks
        lower.append(layer.inner_radius_bounds_mm[0])
        upper.append(layer.inner_radius_bounds_mm[1])
        for block_index in range(layer.n_blocks):
            # Block index 0 has alpha_deg hard-fixed to 0 (see decode()),
            # which is only geometrically valid near the midplane
            # (phi_deg=90, per primitives.py's phi convention). So block 0
            # must get the window closest to phi_upper (the midplane side)
            # and increasing block index must move toward phi_lower (the
            # pole side), where the free alpha gene on blocks 1..n-1 can
            # compensate. This matches the verified reference convention
            # in dipole_designer (blocks stored ascending pole-ward from
            # the midplane block, which is always alpha=0).
            block_phi_lower = phi_upper - (block_index + 1) * window_width
            block_phi_upper = phi_upper - block_index * window_width
            lower.extend((block_phi_lower, float(layer.n_turns_bounds[0])))
            upper.extend((block_phi_upper, float(layer.n_turns_bounds[1])))
            if block_index > 0:
                lower.append(0.0)
                upper.append(1.0)
                lower.append(layer.alpha_bounds_deg[0])
                upper.append(layer.alpha_bounds_deg[1])
    return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)


def genome_variables(topology: Topology) -> tuple[GenomeVariable, ...]:
    """Return ordered metadata for every flat genome slot."""

    lower, upper = genome_bounds(topology)
    variables: list[GenomeVariable] = []
    index = 0
    for layer_index, layer in enumerate(topology.layers):
        variables.append(
            GenomeVariable(
                name=f"layer_{layer_index}_inner_radius_mm",
                index=index,
                kind="real",
                bounds=(float(lower[index]), float(upper[index])),
                layer_index=layer_index,
            )
        )
        index += 1
        for block_index in range(layer.n_blocks):
            variables.append(
                GenomeVariable(
                    name=f"layer_{layer_index}_block_{block_index}_phi_deg",
                    index=index,
                    kind="real",
                    bounds=(float(lower[index]), float(upper[index])),
                    layer_index=layer_index,
                    block_index=block_index,
                )
            )
            index += 1
            variables.append(
                GenomeVariable(
                    name=f"layer_{layer_index}_block_{block_index}_n_turns",
                    index=index,
                    kind="integer",
                    bounds=(float(lower[index]), float(upper[index])),
                    layer_index=layer_index,
                    block_index=block_index,
                )
            )
            index += 1
            if block_index > 0:
                variables.append(
                    GenomeVariable(
                        name=f"layer_{layer_index}_block_{block_index}_active",
                        index=index,
                        kind="binary",
                        bounds=(float(lower[index]), float(upper[index])),
                        layer_index=layer_index,
                        block_index=block_index,
                    )
                )
                index += 1
                variables.append(
                    GenomeVariable(
                        name=f"layer_{layer_index}_block_{block_index}_alpha_deg",
                        index=index,
                        kind="real",
                        bounds=(float(lower[index]), float(upper[index])),
                        layer_index=layer_index,
                        block_index=block_index,
                    )
                )
                index += 1
    return tuple(variables)


def mixed_variable_spec(topology: Topology) -> dict[str, Real | Integer | Binary]:
    """Return pymoo mixed-variable declarations for this topology."""

    variables: dict[str, Real | Integer | Binary] = {}
    for variable in genome_variables(topology):
        if variable.kind == "binary":
            variables[variable.name] = Binary()
        elif variable.kind == "integer":
            variables[variable.name] = Integer(
                bounds=(int(variable.bounds[0]), int(variable.bounds[1]))
            )
        else:
            variables[variable.name] = Real(bounds=variable.bounds)
    return variables


def flatten_mixed_genome(genome: Mapping[str, float] | Sequence[float], topology: Topology) -> np.ndarray:
    """Convert a pymoo mixed-variable dict or flat sequence to DOT's flat genome."""

    if not isinstance(genome, Mapping):
        return np.asarray(genome, dtype=float)

    values = np.empty(topology.n_var, dtype=float)
    for variable in genome_variables(topology):
        values[variable.index] = float(genome[variable.name])
    return values


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
