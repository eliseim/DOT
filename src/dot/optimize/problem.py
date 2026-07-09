"""pymoo problem wiring for fixed-topology dipole optimization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from pymoo.core.problem import Problem

from dot.geometry import CableSpec
from dot.geometry.constraints import check_feasibility

from .genome import Topology, decode, genome_bounds
from .objectives import LayerConductorData, field_quality_objective, load_line_margin_objective
from .operating_point import operating_point

_PENALTY = 1.0e12


@dataclass(frozen=True, slots=True)
class MarginEvaluationExclusion:
    """A layer whose load-line margin was intentionally not evaluated."""

    layer_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class OptimizationTargets:
    """Physics targets and conductor inputs for one campaign."""

    target_bore_field_t: float
    r_ref_mm: float
    max_order: int
    cadata_by_layer: tuple[LayerConductorData | None, ...]
    temperature_k: float
    max_harmonic_units: float | None = None
    min_margin_percent: float | None = None
    max_current_a: float | None = None
    excluded_margin_layers: tuple[MarginEvaluationExclusion, ...] = ()


@dataclass(frozen=True, slots=True)
class FeasibilitySettings:
    """Geometry feasibility settings passed through to task 0003 checks."""

    min_gap_mm: float
    max_angle_deg: float | Sequence[float]
    min_layer_clearance_mm: float = 0.1


class DipoleOptimizationProblem(Problem):
    """Decode genomes, gate geometry feasibility via ``G``, and evaluate objectives."""

    def __init__(
        self,
        topology: Topology,
        targets: OptimizationTargets,
        feasibility: FeasibilitySettings,
        cable_map: Mapping[str, CableSpec] | None = None,
    ) -> None:
        self.topology = topology
        self.targets = targets
        self.feasibility = feasibility
        self.cable_map = topology.cables if cable_map is None else cable_map
        lower, upper = genome_bounds(topology)
        super().__init__(
            n_var=topology.n_var,
            n_obj=2,
            n_ieq_constr=1,
            xl=lower,
            xu=upper,
        )

    def _evaluate(self, x, out, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
        rows = np.atleast_2d(np.asarray(x, dtype=float))
        objectives = np.empty((rows.shape[0], 2), dtype=float)
        constraints = np.empty((rows.shape[0], 1), dtype=float)

        for row_index, row in enumerate(rows):
            try:
                unit_design = decode(row, self.topology, self.cable_map)
                feasibility = check_feasibility(
                    unit_design,
                    aperture_radius_mm=self.topology.aperture_radius_mm,
                    min_gap_mm=self.feasibility.min_gap_mm,
                    max_angle_deg=self.feasibility.max_angle_deg,
                    min_layer_clearance_mm=self.feasibility.min_layer_clearance_mm,
                )
                if not feasibility.is_feasible:
                    objectives[row_index] = (_PENALTY, _PENALTY)
                    constraints[row_index, 0] = float(len(feasibility.violations))
                    continue

                solved = operating_point(unit_design, self.targets.target_bore_field_t)
                if (
                    self.targets.max_current_a is not None
                    and abs(solved.operating_current_a) > self.targets.max_current_a
                ):
                    objectives[row_index] = (_PENALTY, _PENALTY)
                    constraints[row_index, 0] = 1.0
                    continue

                field_quality = field_quality_objective(
                    solved.design,
                    self.targets.r_ref_mm,
                    self.targets.max_order,
                )
                margin_percent = load_line_margin_objective(
                    solved.design,
                    tuple(layer.cable_id for layer in self.topology.layers),
                    self.targets.cadata_by_layer,
                    self.targets.temperature_k,
                )
                objectives[row_index] = (field_quality, -margin_percent)
                constraints[row_index, 0] = 0.0
            except (KeyError, ValueError, ZeroDivisionError):
                objectives[row_index] = (_PENALTY, _PENALTY)
                constraints[row_index, 0] = 1.0

        out["F"] = objectives
        out["G"] = constraints
