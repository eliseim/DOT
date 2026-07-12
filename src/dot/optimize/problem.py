"""pymoo problem wiring for fixed-topology dipole optimization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from pymoo.core.problem import Problem

from dot.geometry import CableSpec
from dot.geometry.constraints import check_feasibility

from . import objectives as _objectives_module
from .genome import Topology, decode, flatten_mixed_genome, genome_bounds, mixed_variable_spec
from .objectives import LayerConductorData, field_quality_objective, load_line_margin_objective
from .operating_point import operating_point
from .topology_survival import topology_family

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
        n_workers: int | None = None,
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
        # task 0050: load_line_margin_objective costs up to ~3s/eval at high
        # turn counts (near-field cost grows with total conductor count),
        # making deep campaigns at the turn counts needed for realistic
        # margins impractically slow. Population evaluation is
        # embarrassingly parallel (each row is independent), so distribute
        # it across a persistent process pool when requested -- same
        # computation, just distributed, zero numerical risk. The pool is
        # created once here and reused across every generation's
        # _evaluate() call (creating a fresh pool per generation would
        # waste most of the win on process-spawn overhead).
        self._executor = None
        if n_workers is not None and n_workers > 1:
            import concurrent.futures

            self._executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=n_workers,
                initializer=_init_worker,
                initargs=(
                    topology,
                    self.cable_map,
                    feasibility,
                    targets,
                    self.n_ieq_constr,
                    _objectives_module.PEAK_FIELD_FILAMENTS_PER_AXIS,
                ),
            )

    def close(self) -> None:
        """Shut down the worker pool, if one was created."""

        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def __del__(self) -> None:
        # Best-effort cleanup if close() was never called explicitly --
        # ProcessPoolExecutor does not reliably self-terminate on GC.
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

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
        # task 0045: attached for TopologyAwareRankAndCrowding's family-quota
        # survival. "invalid" is the fallback for rows whose genome fails to
        # decode at all -- those never get a real fingerprint.
        families = np.full(rows.shape[0], "invalid", dtype=object)
        harmonic_threshold_units, margin_threshold_percent, current_threshold_a = self.admission_thresholds()

        if self._executor is not None:
            tasks = [
                (row, harmonic_threshold_units, margin_threshold_percent, current_threshold_a) for row in rows
            ]
            results = list(self._executor.map(_evaluate_row_worker, tasks))
        else:
            results = [
                _evaluate_row(
                    row,
                    self.topology,
                    self.cable_map,
                    self.feasibility,
                    self.targets,
                    self.n_ieq_constr,
                    harmonic_threshold_units,
                    margin_threshold_percent,
                    current_threshold_a,
                )
                for row in rows
            ]

        for row_index, (objective_row, constraint_row, family) in enumerate(results):
            objectives[row_index] = objective_row
            constraints[row_index] = constraint_row
            families[row_index] = family

        out["F"] = objectives
        out["G"] = constraints
        out["topology_family"] = families


def _evaluate_row(
    row: np.ndarray,
    topology: Topology,
    cable_map: Mapping[str, CableSpec],
    feasibility: FeasibilitySettings,
    targets: OptimizationTargets,
    n_ieq_constr: int,
    harmonic_threshold_units: float | None,
    margin_threshold_percent: float | None,
    current_threshold_a: float | None,
) -> tuple[tuple[float, float], np.ndarray, str]:
    """Evaluate one genome row. Module-level (not a method) so it is picklable
    and can run in a worker process (task 0050)."""

    objective = (_PENALTY, _PENALTY)
    constraint = np.zeros(n_ieq_constr, dtype=float)
    family = "invalid"
    try:
        unit_design = decode(row, topology, cable_map)
        family = topology_family(unit_design)
        result = check_feasibility(
            unit_design,
            aperture_radius_mm=topology.aperture_radius_mm,
            min_gap_mm=feasibility.min_gap_mm,
            max_angle_deg=feasibility.max_angle_deg,
            min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
            min_pole_gap_mm=feasibility.min_pole_gap_mm,
            min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
            enforce_layer_nesting=feasibility.enforce_layer_nesting,
        )
        if not result.is_feasible:
            constraint[0] = sum(violation.severity for violation in result.violations)
            return objective, constraint, family

        target_constraint_index = 1
        turn_budget_violation = False
        if targets.max_total_turns is not None:
            total_turns = sum(block.n_turns for layer in unit_design.layers for block in layer.blocks)
            constraint[target_constraint_index] = max(0.0, float(total_turns - targets.max_total_turns))
            turn_budget_violation |= constraint[target_constraint_index] > 0.0
            target_constraint_index += 1
        if targets.max_turns_per_layer is not None:
            per_layer_violation = sum(
                max(0, sum(block.n_turns for block in layer.blocks) - targets.max_turns_per_layer)
                for layer in unit_design.layers
            )
            constraint[target_constraint_index] = float(per_layer_violation)
            turn_budget_violation |= constraint[target_constraint_index] > 0.0
            target_constraint_index += 1
        if turn_budget_violation:
            return objective, constraint, family

        solved = operating_point(unit_design, targets.target_bore_field_t)
        field_quality = field_quality_objective(solved.design, targets.r_ref_mm, targets.max_order)
        margin_percent = load_line_margin_objective(
            solved.design,
            tuple(layer.cable_id for layer in topology.layers),
            targets.cadata_by_layer,
            targets.temperature_k,
        )
        objective = (field_quality, -margin_percent)
        if harmonic_threshold_units is not None:
            # field_quality_objective's raw return value is already in
            # CERN/European relative "units" (parts per 1e4 of the main
            # dipole term) -- see multipole_coefficients' own docstring
            # ("multiplied by 1e4... b_1 is 10000 for a normal dipole").
            # No conversion needed: compare directly (task 0041).
            constraint[target_constraint_index] = max(0.0, field_quality - harmonic_threshold_units)
            target_constraint_index += 1
        if margin_threshold_percent is not None:
            constraint[target_constraint_index] = max(0.0, margin_threshold_percent - margin_percent)
            target_constraint_index += 1
        if current_threshold_a is not None:
            constraint[target_constraint_index] = max(0.0, abs(solved.operating_current_a) - current_threshold_a)
        return objective, constraint, family
    except (KeyError, ValueError, ZeroDivisionError):
        constraint[:] = 0.0
        constraint[0] = 1.0
        return (_PENALTY, _PENALTY), constraint, family


# Process-pool worker state (task 0050): set once per worker process via
# _init_worker, then reused across every row that process evaluates. Kept
# as module globals rather than passed per-call so the (relatively large,
# static-for-the-whole-run) topology/cable_map/feasibility/targets objects
# are pickled only once at pool startup, not once per row.
_worker_topology: Topology
_worker_cable_map: Mapping[str, CableSpec]
_worker_feasibility: FeasibilitySettings
_worker_targets: OptimizationTargets
_worker_n_ieq_constr: int


def _init_worker(
    topology: Topology,
    cable_map: Mapping[str, CableSpec],
    feasibility: FeasibilitySettings,
    targets: OptimizationTargets,
    n_ieq_constr: int,
    peak_field_filaments_per_axis: int,
) -> None:
    global _worker_topology, _worker_cable_map, _worker_feasibility, _worker_targets, _worker_n_ieq_constr
    _worker_topology = topology
    _worker_cable_map = cable_map
    _worker_feasibility = feasibility
    _worker_targets = targets
    _worker_n_ieq_constr = n_ieq_constr
    # Windows uses "spawn" for new processes, so each worker re-imports
    # dot.optimize.objectives fresh -- it does NOT inherit the parent
    # process's runtime mutation of this module-level global (campaign
    # scripts set it to a cheaper SEARCH_DISCRETIZATION value). Without
    # this, workers would silently fall back to the expensive default,
    # defeating the whole point of the multi-fidelity search/verify split.
    _objectives_module.PEAK_FIELD_FILAMENTS_PER_AXIS = peak_field_filaments_per_axis


def _evaluate_row_worker(
    task: tuple[np.ndarray, float | None, float | None, float | None],
) -> tuple[tuple[float, float], np.ndarray, str]:
    row, harmonic_threshold_units, margin_threshold_percent, current_threshold_a = task
    return _evaluate_row(
        row,
        _worker_topology,
        _worker_cable_map,
        _worker_feasibility,
        _worker_targets,
        _worker_n_ieq_constr,
        harmonic_threshold_units,
        margin_threshold_percent,
        current_threshold_a,
    )
