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
class AdmissionStage:
    """One plateau in a staged admission schedule.

    ``end_fraction`` is the generation-progress fraction (0-1) through
    which this stage's thresholds stay in effect. Thresholds are resolved
    as multipliers/relaxations against the campaign's final targets:
    ``harmonic_threshold = harmonic_multiplier * max_harmonic_units``,
    ``margin_threshold = min_margin_percent - margin_relaxation_percent``,
    ``current_threshold = current_multiplier * max_current_a``.
    """

    end_fraction: float
    harmonic_multiplier: float
    margin_relaxation_percent: float
    current_multiplier: float


@dataclass(frozen=True, slots=True)
class AdmissionSchedule:
    """A sequence of :class:`AdmissionStage` plateaus, replacing the default
    single linear anneal (task 0044/dd's multi-stage admission).

    Unlike the linear anneal, thresholds hold **constant** within a stage
    and step discontinuously at each ``end_fraction`` boundary -- this
    gives the population time to consolidate against a given threshold
    before it tightens again, rather than continuously chasing a moving
    target from generation 1.
    """

    stages: tuple[AdmissionStage, ...]

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("AdmissionSchedule requires at least one stage")
        previous_end = 0.0
        for stage in self.stages:
            if stage.end_fraction <= previous_end:
                raise ValueError(
                    "AdmissionSchedule stage end_fraction values must be strictly increasing "
                    f"(got {stage.end_fraction} after {previous_end})"
                )
            previous_end = stage.end_fraction
        if self.stages[-1].end_fraction != 1.0:
            raise ValueError("AdmissionSchedule's last stage must end at end_fraction=1.0")

    def stage_for_progress(self, progress: float) -> AdmissionStage:
        for stage in self.stages:
            if progress <= stage.end_fraction:
                return stage
        return self.stages[-1]


# dd's own suggested defaults (end_fractions/harmonic_multipliers/
# margin_relaxations_pp), extended with a current_multiplier axis DOT
# already anneals but dd doesn't stage the same way.
DEFAULT_ADMISSION_SCHEDULE = AdmissionSchedule(
    stages=(
        AdmissionStage(end_fraction=0.4, harmonic_multiplier=4.0, margin_relaxation_percent=10.0, current_multiplier=1.5),
        AdmissionStage(end_fraction=0.7, harmonic_multiplier=2.0, margin_relaxation_percent=5.0, current_multiplier=1.2),
        AdmissionStage(end_fraction=0.9, harmonic_multiplier=1.0, margin_relaxation_percent=2.0, current_multiplier=1.0),
        AdmissionStage(end_fraction=1.0, harmonic_multiplier=1.0, margin_relaxation_percent=0.0, current_multiplier=1.0),
    )
)


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
    # None (default) preserves the original single linear anneal exactly.
    # When set, admission_thresholds() uses this staged schedule instead
    # (task 0044).
    admission_schedule: AdmissionSchedule | None = None


@dataclass(frozen=True, slots=True)
class FeasibilitySettings:
    """Geometry feasibility settings passed through to task 0003 checks."""

    min_gap_mm: float
    max_angle_deg: float | Sequence[float]
    min_layer_clearance_mm: float = 0.1
    min_pole_gap_mm: float | None = None
    min_inter_block_gap_mm: float | None = None
    enforce_layer_nesting: bool = False
    # Cap, in degrees, on how far LayerNestingRepair (task 0043) may shift an
    # outer layer's blocks toward the midplane to restore C10 nesting. None
    # or <=0 disables the repair (a violation is left for the existing
    # penalty/graded-constraint handling). 15deg mirrors dipole_designer's
    # own max_decode_angle_repair_deg order of magnitude.
    max_nesting_repair_deg: float | None = None


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

        if self.targets.admission_schedule is not None:
            return self._staged_admission_thresholds(progress)

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

    def _staged_admission_thresholds(self, progress: float) -> tuple[float | None, float | None, float | None]:
        assert self.targets.admission_schedule is not None
        stage = self.targets.admission_schedule.stage_for_progress(progress)
        harmonic_threshold = None
        if self.targets.max_harmonic_units is not None:
            harmonic_threshold = stage.harmonic_multiplier * self.targets.max_harmonic_units
        margin_threshold = None
        if self.targets.min_margin_percent is not None:
            margin_threshold = self.targets.min_margin_percent - stage.margin_relaxation_percent
        current_threshold = None
        if self.targets.max_current_a is not None:
            current_threshold = stage.current_multiplier * self.targets.max_current_a
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
                    # field_quality_objective's raw return value is already
                    # in CERN/European relative "units" (parts per 1e4 of
                    # the main dipole term) -- see multipole_coefficients'
                    # own docstring ("multiplied by 1e4... b_1 is 10000 for
                    # a normal dipole"). Dividing harmonic_threshold_units
                    # by 1e4 here compared an already-units-scaled target
                    # against an already-units-scaled objective after an
                    # extra, erroneous 1e4 shrink -- confirmed against the
                    # real CTH-14T design (tests/physics/
                    # test_roxie_parity_live.py's _cth14t_design()), whose
                    # own field_quality_objective is ~2.0 (sensible against
                    # a 5.0-unit target) but would fail the old
                    # 0.0005-unit threshold by a factor of ~4000. No
                    # conversion needed: compare directly.
                    constraints[row_index, target_constraint_index] = max(
                        0.0, field_quality - harmonic_threshold_units
                    )
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
