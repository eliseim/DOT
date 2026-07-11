"""pymoo problem wiring for fixed-topology dipole optimization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from pymoo.core.problem import Problem

from dot.geometry import CableSpec
from dot.geometry.constraints import check_feasibility

from .genome import Topology, decode, flatten_mixed_genome, genome_bounds, mixed_variable_spec
from .objectives import LayerConductorData, field_quality_objective, load_line_margin_objective
from .operating_point import operating_point

_PENALTY = 1.0e12
_START_HARMONIC_RELAXATION_MULTIPLIER = 10.0
_START_MARGIN_RELAXATION_PERCENT = 20.0
_START_CURRENT_RELAXATION_MULTIPLIER = 2.0


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
    max_total_turns: int | None = None
    max_turns_per_layer: int | None = None
    excluded_margin_layers: tuple[MarginEvaluationExclusion, ...] = ()


@dataclass(frozen=True, slots=True)
class FeasibilitySettings:
    """Geometry feasibility settings passed through to task 0003 checks."""

    min_gap_mm: float
    max_angle_deg: float | Sequence[float]
    min_layer_clearance_mm: float = 0.1
    min_pole_gap_mm: float | None = None
    min_inter_block_gap_mm: float | None = None
    enforce_layer_nesting: bool = False


class DipoleOptimizationProblem(Problem):
    """Decode genomes, gate geometry feasibility via ``G``, and evaluate objectives."""

    def __init__(
        self,
        topology: Topology,
        targets: OptimizationTargets,
        feasibility: FeasibilitySettings,
        cable_map: Mapping[str, CableSpec] | None = None,
        total_generations: int = 1,
    ) -> None:
        self.topology = topology
        self.targets = targets
        self.feasibility = feasibility
        self.cable_map = topology.cables if cable_map is None else cable_map
        self.total_generations = max(1, int(total_generations))
        self.current_generation = 1
        lower, upper = genome_bounds(topology)
        super().__init__(
            n_var=topology.n_var,
            n_obj=2,
            n_ieq_constr=1
            + int(targets.max_total_turns is not None)
            + int(targets.max_turns_per_layer is not None)
            + int(targets.max_harmonic_units is not None)
            + int(targets.min_margin_percent is not None)
            + int(targets.max_current_a is not None),
            xl=lower,
            xu=upper,
            vars=mixed_variable_spec(topology),
        )

    def set_generation(self, generation: int) -> None:
        """Set the 1-indexed generation used by annealed target admission."""

        self.current_generation = max(1, int(generation))

    def admission_thresholds(self, generation: int | None = None) -> tuple[float | None, float | None, float | None]:
        """Return active harmonic, margin, and current thresholds."""

        if generation is None:
            generation = self.current_generation
        progress = min(1.0, max(1, int(generation)) / self.total_generations)
        harmonic_threshold = None
        if self.targets.max_harmonic_units is not None:
            start = self.targets.max_harmonic_units * _START_HARMONIC_RELAXATION_MULTIPLIER
            harmonic_threshold = start + progress * (self.targets.max_harmonic_units - start)
        margin_threshold = None
        if self.targets.min_margin_percent is not None:
            start = self.targets.min_margin_percent - _START_MARGIN_RELAXATION_PERCENT
            margin_threshold = start + progress * (self.targets.min_margin_percent - start)
        current_threshold = None
        if self.targets.max_current_a is not None:
            start = self.targets.max_current_a * _START_CURRENT_RELAXATION_MULTIPLIER
            current_threshold = start + progress * (self.targets.max_current_a - start)
        return harmonic_threshold, margin_threshold, current_threshold

    def _evaluate(self, x, out, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
        if isinstance(x, dict):
            rows = np.atleast_2d(flatten_mixed_genome(x, self.topology))
        elif isinstance(x, np.ndarray) and x.dtype == object and x.size and isinstance(x.flat[0], dict):
            rows = np.asarray(
                [flatten_mixed_genome(row, self.topology) for row in x],
                dtype=float,
            )
        elif isinstance(x, list) and x and isinstance(x[0], dict):
            rows = np.asarray(
                [flatten_mixed_genome(row, self.topology) for row in x],
                dtype=float,
            )
        else:
            rows = np.atleast_2d(np.asarray(x, dtype=float))
        objectives = np.empty((rows.shape[0], 2), dtype=float)
        constraints = np.zeros((rows.shape[0], self.n_ieq_constr), dtype=float)
        harmonic_threshold_units, margin_threshold_percent, current_threshold_a = self.admission_thresholds()

        for row_index, row in enumerate(rows):
            try:
                unit_design = decode(row, self.topology, self.cable_map)
                feasibility = check_feasibility(
                    unit_design,
                    aperture_radius_mm=self.topology.aperture_radius_mm,
                    min_gap_mm=self.feasibility.min_gap_mm,
                    max_angle_deg=self.feasibility.max_angle_deg,
                    min_layer_clearance_mm=self.feasibility.min_layer_clearance_mm,
                    min_pole_gap_mm=self.feasibility.min_pole_gap_mm,
                    min_inter_block_gap_mm=self.feasibility.min_inter_block_gap_mm,
                    enforce_layer_nesting=self.feasibility.enforce_layer_nesting,
                )
                if not feasibility.is_feasible:
                    objectives[row_index] = (_PENALTY, _PENALTY)
                    constraints[row_index, 0] = sum(violation.severity for violation in feasibility.violations)
                    continue

                target_constraint_index = 1
                turn_budget_violation = False
                if self.targets.max_total_turns is not None:
                    total_turns = sum(block.n_turns for layer in unit_design.layers for block in layer.blocks)
                    constraints[row_index, target_constraint_index] = max(
                        0.0,
                        float(total_turns - self.targets.max_total_turns),
                    )
                    turn_budget_violation |= constraints[row_index, target_constraint_index] > 0.0
                    target_constraint_index += 1
                if self.targets.max_turns_per_layer is not None:
                    per_layer_violation = sum(
                        max(0, sum(block.n_turns for block in layer.blocks) - self.targets.max_turns_per_layer)
                        for layer in unit_design.layers
                    )
                    constraints[row_index, target_constraint_index] = float(per_layer_violation)
                    turn_budget_violation |= constraints[row_index, target_constraint_index] > 0.0
                    target_constraint_index += 1
                if turn_budget_violation:
                    objectives[row_index] = (_PENALTY, _PENALTY)
                    continue

                solved = operating_point(unit_design, self.targets.target_bore_field_t)
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
                if harmonic_threshold_units is not None:
                    harmonic_threshold = harmonic_threshold_units / 1.0e4
                    constraints[row_index, target_constraint_index] = max(0.0, field_quality - harmonic_threshold)
                    target_constraint_index += 1
                if margin_threshold_percent is not None:
                    constraints[row_index, target_constraint_index] = max(
                        0.0,
                        margin_threshold_percent - margin_percent,
                    )
                    target_constraint_index += 1
                if current_threshold_a is not None:
                    constraints[row_index, target_constraint_index] = max(
                        0.0,
                        abs(solved.operating_current_a) - current_threshold_a,
                    )
            except (KeyError, ValueError, ZeroDivisionError):
                objectives[row_index] = (_PENALTY, _PENALTY)
                constraints[row_index, 0] = 1.0

        out["F"] = objectives
        out["G"] = constraints
