"""Cable geometry primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, init=False)
class CableSpec:
    """Keystoned cable dimensions in millimetres.

    ``width_inner_mm`` and ``width_outer_mm`` are bare cable widths at the
    inner and outer faces.  The legacy ``width_mm`` and
    ``insulation_thickness_mm`` constructor arguments are still accepted for
    rectangular cables.
    """

    width_inner_mm: float
    width_outer_mm: float
    height_mm: float
    insulation_radial_mm: float
    insulation_azimuthal_mm: float

    def __init__(
        self,
        *,
        height_mm: float,
        width_inner_mm: float | None = None,
        width_outer_mm: float | None = None,
        insulation_radial_mm: float | None = None,
        insulation_azimuthal_mm: float | None = None,
        width_mm: float | None = None,
        insulation_thickness_mm: float | None = None,
    ) -> None:
        if width_mm is not None:
            if width_inner_mm is not None or width_outer_mm is not None:
                raise ValueError("width_mm cannot be combined with width_inner_mm or width_outer_mm")
            width_inner_mm = width_mm
            width_outer_mm = width_mm
        if width_inner_mm is None or width_outer_mm is None:
            raise ValueError("width_inner_mm and width_outer_mm are required")

        if insulation_thickness_mm is not None:
            if insulation_radial_mm is None:
                insulation_radial_mm = insulation_thickness_mm
            if insulation_azimuthal_mm is None:
                insulation_azimuthal_mm = insulation_thickness_mm
        if insulation_radial_mm is None:
            insulation_radial_mm = 0.0
        if insulation_azimuthal_mm is None:
            insulation_azimuthal_mm = 0.0

        object.__setattr__(self, "width_inner_mm", width_inner_mm)
        object.__setattr__(self, "width_outer_mm", width_outer_mm)
        object.__setattr__(self, "height_mm", height_mm)
        object.__setattr__(self, "insulation_radial_mm", insulation_radial_mm)
        object.__setattr__(self, "insulation_azimuthal_mm", insulation_azimuthal_mm)
        self.__post_init__()

    def __post_init__(self) -> None:
        for name, value in (
            ("width_inner_mm", self.width_inner_mm),
            ("width_outer_mm", self.width_outer_mm),
            ("height_mm", self.height_mm),
            ("insulation_radial_mm", self.insulation_radial_mm),
            ("insulation_azimuthal_mm", self.insulation_azimuthal_mm),
        ):
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.width_inner_mm <= 0.0:
            raise ValueError("width_inner_mm must be positive")
        if self.width_outer_mm <= 0.0:
            raise ValueError("width_outer_mm must be positive")
        if self.height_mm <= 0.0:
            raise ValueError("height_mm must be positive")
        if self.insulation_radial_mm < 0.0:
            raise ValueError("insulation_radial_mm must be non-negative")
        if self.insulation_azimuthal_mm < 0.0:
            raise ValueError("insulation_azimuthal_mm must be non-negative")

    @property
    def width_mm(self) -> float:
        """Average bare width, kept for legacy rectangular callers."""

        return 0.5 * (self.width_inner_mm + self.width_outer_mm)

    @property
    def insulation_thickness_mm(self) -> float:
        """Average insulation thickness, kept for legacy rectangular callers."""

        return 0.5 * (self.insulation_radial_mm + self.insulation_azimuthal_mm)

    @property
    def insulated_width_mm(self) -> float:
        return 0.5 * (self.insulated_width_inner_mm + self.insulated_width_outer_mm)

    @property
    def insulated_width_inner_mm(self) -> float:
        return self.width_inner_mm + 2.0 * self.insulation_azimuthal_mm

    @property
    def insulated_width_outer_mm(self) -> float:
        return self.width_outer_mm + 2.0 * self.insulation_azimuthal_mm

    @property
    def width_inner_insulated_mm(self) -> float:
        return self.insulated_width_inner_mm

    @property
    def width_outer_insulated_mm(self) -> float:
        return self.insulated_width_outer_mm

    @property
    def insulated_height_mm(self) -> float:
        return self.height_mm + 2.0 * self.insulation_radial_mm
