"""Cable geometry primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CableSpec:
    """Rectangular cable dimensions in millimetres."""

    width_mm: float
    height_mm: float
    insulation_thickness_mm: float

    def __post_init__(self) -> None:
        for name, value in (
            ("width_mm", self.width_mm),
            ("height_mm", self.height_mm),
            ("insulation_thickness_mm", self.insulation_thickness_mm),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.width_mm <= 0.0:
            raise ValueError("width_mm must be positive")
        if self.height_mm <= 0.0:
            raise ValueError("height_mm must be positive")
        if self.insulation_thickness_mm < 0.0:
            raise ValueError("insulation_thickness_mm must be non-negative")

    @property
    def insulated_width_mm(self) -> float:
        return self.width_mm + 2.0 * self.insulation_thickness_mm

    @property
    def insulated_height_mm(self) -> float:
        return self.height_mm + 2.0 * self.insulation_thickness_mm
