"""Conductor critical-current utilities for DOT."""

from .cadata import (
    CableRecord,
    CadataRecords,
    StrandRecord,
    Type1FitCoefficients,
    UnsupportedFitTypeError,
    parse_cadata_text,
)
from .critical_current import cable_critical_current, strand_critical_current
from .critical_surface import critical_current_density
from .loadline import load_line_margin_percent, solve_short_sample_current

__all__ = [
    "CableRecord",
    "CadataRecords",
    "StrandRecord",
    "Type1FitCoefficients",
    "UnsupportedFitTypeError",
    "cable_critical_current",
    "critical_current_density",
    "load_line_margin_percent",
    "parse_cadata_text",
    "solve_short_sample_current",
    "strand_critical_current",
]
