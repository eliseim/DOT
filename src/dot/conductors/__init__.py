"""Conductor critical-current utilities for DOT."""

from .cadata import (
    CableRecord,
    CadataRecords,
    ConductorRecord,
    ConductorResolution,
    FilamentRecord,
    InsulationRecord,
    StrandRecord,
    Type1FitCoefficients,
    Type11FitCoefficients,
    UnsupportedRemfitRecord,
    UnsupportedFitTypeError,
    parse_cadata_text,
    resolve_conductor,
)
from .critical_current import (
    cable_critical_current,
    strand_critical_current,
    strand_non_copper_area_m2,
)
from .critical_surface import critical_current_density
from .loadline import (
    ConservativeCurrentAdvice,
    conservative_maximum_current_advice,
    load_line_margin_percent,
    solve_short_sample_current,
)

__all__ = [
    "CableRecord",
    "CadataRecords",
    "ConductorRecord",
    "ConductorResolution",
    "ConservativeCurrentAdvice",
    "FilamentRecord",
    "InsulationRecord",
    "StrandRecord",
    "Type1FitCoefficients",
    "Type11FitCoefficients",
    "UnsupportedRemfitRecord",
    "UnsupportedFitTypeError",
    "cable_critical_current",
    "critical_current_density",
    "conservative_maximum_current_advice",
    "load_line_margin_percent",
    "parse_cadata_text",
    "resolve_conductor",
    "solve_short_sample_current",
    "strand_critical_current",
    "strand_non_copper_area_m2",
]
