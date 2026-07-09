"""Optimization utilities for fixed-topology dipole searches."""

from .genome import LayerTopology, Topology, decode, encode, genome_bounds
from .objectives import LayerConductorData, field_quality_objective, load_line_margin_objective
from .operating_point import OperatingPoint, operating_point, scale_design_currents

__all__ = [
    "LayerConductorData",
    "LayerTopology",
    "OperatingPoint",
    "Topology",
    "decode",
    "encode",
    "field_quality_objective",
    "genome_bounds",
    "load_line_margin_objective",
    "operating_point",
    "scale_design_currents",
]
