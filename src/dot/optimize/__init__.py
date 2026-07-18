"""Optimization utilities for fixed-topology dipole searches."""

from .genome import LayerTopology, Topology, decode, encode, genome_bounds
from .objectives import (
    BlockMarginRecord,
    CERTIFICATION_FIDELITY,
    SEARCH_FIDELITY,
    EvaluationFidelity,
    LayerConductorData,
    field_quality_objective,
    harmonic_table,
    load_line_margin_objective,
    load_line_margin_by_block_detail,
)
from .operating_point import OperatingPoint, operating_point, scale_design_currents

__all__ = [
    "CERTIFICATION_FIDELITY",
    "BlockMarginRecord",
    "EvaluationFidelity",
    "LayerConductorData",
    "LayerTopology",
    "OperatingPoint",
    "SEARCH_FIDELITY",
    "Topology",
    "decode",
    "encode",
    "field_quality_objective",
    "harmonic_table",
    "genome_bounds",
    "load_line_margin_objective",
    "load_line_margin_by_block_detail",
    "operating_point",
    "scale_design_currents",
]
