"""pymoo problem wiring for fixed-topology dipole optimization."""

from __future__ import annotations

import math
import os
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

import numpy as np
from pymoo.core.problem import Problem

from dot.geometry import CableSpec, DipoleDesign
from dot.geometry.constraints import check_feasibility

from . import objectives as _objectives_module
from .genome import Topology, decode, flatten_mixed_genome, genome_bounds, mixed_variable_spec
from .objectives import (
    CERTIFICATION_FIDELITY,
    SEARCH_FIDELITY,
    EvaluationFidelity,
    LayerConductorData,
    field_quality_objective,
    load_line_margin_objective,
)
from .operating_point import OperatingPoint, operating_point, operating_point_at_current
from .topology_survival import topology_family

_PENALTY = 1.0e12
FIXED_CURRENT_FIELD_RELATIVE_TOLERANCE = 1.0e-4
FIXED_CURRENT_FIELD_ABSOLUTE_TOLERANCE_T = 1.0e-7
_EVALUATION_CACHE_MAXSIZE = 32768
_RowEvaluation = tuple[tuple[float, float], tuple[float, ...], str]
_EvaluationCacheKey = bytes


@dataclass(frozen=True, slots=True)
class OptimizationTargets:
    """Physics targets and conductor inputs for one campaign."""

    target_bore_field_t: float
    r_ref_mm: float
    max_order: int
    cadata_by_layer: tuple[LayerConductorData, ...]
    temperature_k: float
    harmonic_orders: tuple[int, ...] = ()
    harmonic_targets: tuple[tuple[int, float], ...] = ()
    search_fidelity: EvaluationFidelity = SEARCH_FIDELITY
    certification_fidelity: EvaluationFidelity = CERTIFICATION_FIDELITY
    max_harmonic_units: float | None = None
    min_margin_percent: float | None = None
    min_current_a: float | None = None
    max_current_a: float | None = None
    max_total_turns: int | None = None
    max_turns_per_layer: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.target_bore_field_t) or self.target_bore_field_t <= 0.0:
            raise ValueError("target_bore_field_t must be finite and positive")
        if not math.isfinite(self.r_ref_mm) or self.r_ref_mm <= 0.0:
            raise ValueError("r_ref_mm must be finite and positive")
        if isinstance(self.max_order, bool) or not isinstance(self.max_order, int):
            raise ValueError("max_order must be an integer")
        if self.max_order < 3:
            raise ValueError("max_order must be at least 3")
        if not math.isfinite(self.temperature_k) or self.temperature_k <= 0.0:
            raise ValueError("temperature_k must be finite and positive")
        if any(layer_data is None for layer_data in self.cadata_by_layer):
            raise ValueError("cadata_by_layer requires supported conductor data for every layer")

        if len(set(self.harmonic_orders)) != len(self.harmonic_orders):
            raise ValueError("harmonic_orders must be unique")
        if any(
            isinstance(order, bool)
            or not isinstance(order, int)
            or order < 3
            or order > self.max_order
            or order % 2 == 0
            for order in self.harmonic_orders
        ):
            raise ValueError(
                "harmonic_orders must contain odd normal dipole orders from 3 through max_order"
            )
        orders = [order for order, _target in self.harmonic_targets]
        if len(set(orders)) != len(orders):
            raise ValueError("harmonic target orders must be unique")
        for order, target in self.harmonic_targets:
            if (
                isinstance(order, bool)
                or not isinstance(order, int)
                or order < 3
                or order > self.max_order
                or order % 2 == 0
                or not math.isfinite(target)
            ):
                raise ValueError("harmonic targets must use valid orders and finite values")
            if self.harmonic_orders and order not in self.harmonic_orders:
                raise ValueError("harmonic target orders must belong to harmonic_orders")
        if self.max_harmonic_units is not None and (
            not math.isfinite(self.max_harmonic_units)
            or self.max_harmonic_units <= 0.0
        ):
            raise ValueError("max_harmonic_units must be finite and positive")
        if self.min_margin_percent is not None and (
            not math.isfinite(self.min_margin_percent)
            or self.min_margin_percent < 0.0
            or self.min_margin_percent >= 100.0
        ):
            raise ValueError("min_margin_percent must be finite and in [0, 100)")
        if self.min_current_a is not None and (
            not math.isfinite(self.min_current_a) or self.min_current_a < 0.0
        ):
            raise ValueError("min_current_a must be finite and non-negative")
        if self.max_current_a is not None and (
            not math.isfinite(self.max_current_a) or self.max_current_a <= 0.0
        ):
            raise ValueError("max_current_a must be finite and positive")
        if (
            self.min_current_a is not None
            and self.max_current_a is not None
            and self.min_current_a > self.max_current_a
        ):
            raise ValueError("min_current_a must not exceed max_current_a")
        for field_name, value in (
            ("max_total_turns", self.max_total_turns),
            ("max_turns_per_layer", self.max_turns_per_layer),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{field_name} must be a positive integer")
    @property
    def fixed_current_a(self) -> float | None:
        """Return the exact requested current when both bounds are equal."""

        if (
            self.min_current_a is not None
            and self.max_current_a is not None
            and self.min_current_a == self.max_current_a
        ):
            return self.min_current_a
        return None


def solve_operating_point(
    unit_current_design: DipoleDesign,
    targets: OptimizationTargets,
) -> OperatingPoint:
    """Solve by field scaling, or apply the exact current requested by equal bounds."""

    fixed_current_a = targets.fixed_current_a
    if fixed_current_a is not None:
        return operating_point_at_current(
            unit_current_design,
            fixed_current_a,
            target_bore_field_t=targets.target_bore_field_t,
        )
    return operating_point(unit_current_design, targets.target_bore_field_t)


def fixed_current_field_violation(solved: OperatingPoint, targets: OptimizationTargets) -> float:
    """Normalized target-field violation for an exact-current operating point."""

    if targets.fixed_current_a is None:
        return 0.0
    actual_field_t = solved.unit_bore_field_t * solved.scale_factor
    tolerance_t = max(
        FIXED_CURRENT_FIELD_ABSOLUTE_TOLERANCE_T,
        FIXED_CURRENT_FIELD_RELATIVE_TOLERANCE * abs(targets.target_bore_field_t),
    )
    excess_t = max(0.0, abs(actual_field_t - targets.target_bore_field_t) - tolerance_t)
    return excess_t / max(abs(targets.target_bore_field_t), tolerance_t)


def current_range_violation(
    current_a: float,
    min_current_a: float | None,
    max_current_a: float | None,
) -> float:
    """Return one normalized violation for optional lower and upper current bounds."""

    scale_a = max(
        1.0,
        abs(current_a),
        abs(min_current_a) if min_current_a is not None else 0.0,
        abs(max_current_a) if max_current_a is not None else 0.0,
    )
    tolerance_a = max(1.0e-6, 1.0e-10 * scale_a)
    lower = (
        max(0.0, min_current_a - current_a - tolerance_a) / max(1.0, min_current_a)
        if min_current_a is not None
        else 0.0
    )
    upper = (
        max(0.0, current_a - max_current_a - tolerance_a) / max(1.0, max_current_a)
        if max_current_a is not None
        else 0.0
    )
    return max(lower, upper)


def _require_finite_nonnegative(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _require_optional_finite_nonnegative(value: float | None, name: str) -> None:
    if value is not None:
        _require_finite_nonnegative(value, name)


def _require_optional_layerwise_nonnegative(
    value: float | Sequence[float] | None,
    name: str,
) -> None:
    if value is None:
        return
    if isinstance(value, Real) and not isinstance(value, bool):
        _require_finite_nonnegative(float(value), name)
        return
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a number or a sequence of numbers") from exc
    if not values:
        raise ValueError(f"{name} sequence must not be empty")
    for index, item in enumerate(values):
        _require_finite_nonnegative(item, f"{name}[{index}]")


@dataclass(frozen=True, slots=True)
class FeasibilitySettings:
    """Geometry feasibility settings applied to every candidate."""

    min_gap_mm: float
    # Legacy angle limit retained only for loading older campaigns.
    max_angle_deg: float | Sequence[float] | None = None
    min_layer_clearance_mm: float = 0.1
    min_pole_gap_mm: float | None = None
    min_pole_turn_radius_mm: float | None = None
    # A scalar applies to every layer; a sequence sets the physical
    # closest-point clearance independently for each layer.
    min_inter_block_gap_mm: float | Sequence[float] | None = None
    enforce_layer_nesting: bool = False
    geometry_tolerance_mm: float = 0.005
    # Cap, in degrees, on how far LayerNestingRepair may shift an
    # outer layer's blocks toward the midplane to restore C10 nesting. None
    # or <=0 disables the repair (a violation is left for the existing
    # penalty/graded-constraint handling). 15deg mirrors dipole_designer's
    # own max_decode_angle_repair_deg order of magnitude.
    max_nesting_repair_deg: float | None = None

    def __post_init__(self) -> None:
        _require_finite_nonnegative(self.min_gap_mm, "min_gap_mm")
        _require_finite_nonnegative(
            self.min_layer_clearance_mm,
            "min_layer_clearance_mm",
        )
        _require_optional_finite_nonnegative(self.min_pole_gap_mm, "min_pole_gap_mm")
        _require_optional_finite_nonnegative(
            self.min_pole_turn_radius_mm,
            "min_pole_turn_radius_mm",
        )
        _require_optional_layerwise_nonnegative(
            self.min_inter_block_gap_mm,
            "min_inter_block_gap_mm",
        )
        _require_optional_layerwise_nonnegative(self.max_angle_deg, "max_angle_deg")
        _require_finite_nonnegative(
            self.geometry_tolerance_mm,
            "geometry_tolerance_mm",
        )
        if not isinstance(self.enforce_layer_nesting, bool):
            raise ValueError("enforce_layer_nesting must be a boolean")
        if self.max_nesting_repair_deg is not None and not math.isfinite(
            self.max_nesting_repair_deg
        ):
            raise ValueError("max_nesting_repair_deg must be finite when provided")


class DipoleOptimizationProblem(Problem):
    """Decode genomes, gate geometry feasibility via ``G``, and evaluate objectives."""

    def __init__(
        self,
        topology: Topology,
        targets: OptimizationTargets,
        feasibility: FeasibilitySettings,
        cable_map: Mapping[str, CableSpec] | None = None,
        n_workers: int | None = None,
    ) -> None:
        if targets.r_ref_mm >= topology.aperture_radius_mm:
            raise ValueError("r_ref_mm must be smaller than the aperture radius")
        if len(targets.cadata_by_layer) != len(topology.layers):
            raise ValueError(
                "cadata_by_layer must contain exactly one entry per topology layer"
            )
        self.topology = topology
        self.targets = targets
        self.feasibility = feasibility
        self.cable_map = topology.cables if cable_map is None else cable_map
        constraint_names = ["geometry"]
        if targets.max_total_turns is not None:
            constraint_names.append("total_turns")
        if targets.max_turns_per_layer is not None:
            constraint_names.append("turns_per_layer")
        # Operating current is a hard powering/circuit constraint.
        if targets.fixed_current_a is not None:
            constraint_names.append("fixed_current_field")
        elif targets.min_current_a is not None or targets.max_current_a is not None:
            constraint_names.append("current")
        self.constraint_names = tuple(constraint_names)
        lower, upper = genome_bounds(topology)
        super().__init__(
            n_var=topology.n_var,
            n_obj=2,
            n_ieq_constr=len(self.constraint_names),
            xl=lower,
            xu=upper,
            vars=mixed_variable_spec(topology),
        )
        # Load-line evaluation can dominate runtime at high
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
        self._worker_count = 1
        # Repaired mixed-variable offspring can be byte-identical even when
        # they came from different parents. Preserve every individual in
        # NSGA-II, but reuse its exact raw evaluation.
        self._evaluation_cache: OrderedDict[_EvaluationCacheKey, _RowEvaluation] = (
            OrderedDict()
        )
        self.evaluation_cache_hits = 0
        self.evaluation_cache_misses = 0
        if n_workers is not None and n_workers > 1:
            import concurrent.futures
            import multiprocessing

            hardware_limit = max(1, os.cpu_count() or 1)
            platform_limit = 61 if os.name == "nt" else hardware_limit
            worker_count = min(int(n_workers), hardware_limit, platform_limit)
            if worker_count > 1:
                self._worker_count = worker_count

                self._executor = concurrent.futures.ProcessPoolExecutor(
                    max_workers=worker_count,
                    # Explicit spawn is safe when the GUI starts a campaign from
                    # its background thread and is consistent across platforms.
                    mp_context=multiprocessing.get_context("spawn"),
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

    def repair_population(self, samples: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        """Repair independent offspring in the persistent process pool.

        The method is intentionally an exact ordered map. It is used only
        when process evaluation was explicitly enabled by the caller; serial
        campaigns retain the normal in-process repair path.
        """

        if self._executor is None or len(samples) < 8:
            raise RuntimeError("parallel repair requires an active pool and at least eight samples")
        chunksize = max(1, len(samples) // (self._worker_count * 4))
        return list(
            self._executor.map(
                _repair_sample_worker,
                samples,
                chunksize=chunksize,
            )
        )

    def __del__(self) -> None:
        # Best-effort cleanup if close() was never called explicitly --
        # ProcessPoolExecutor does not reliably self-terminate on GC.
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    def _evaluate(self, x, out, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
        if isinstance(x, dict):
            rows = np.atleast_2d(flatten_mixed_genome(x, self.topology))
        elif (
            isinstance(x, np.ndarray)
            and x.dtype == object
            and x.size
            and isinstance(x.flat[0], dict)
        ):
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
        # Topology families let survival retain geometrically distinct layouts.
        families = np.full(rows.shape[0], "invalid", dtype=object)

        row_keys = [self._evaluation_cache_key(row) for row in rows]
        resolved: dict[_EvaluationCacheKey, _RowEvaluation] = {}
        missing: OrderedDict[_EvaluationCacheKey, np.ndarray] = OrderedDict()
        for key, row in zip(row_keys, rows, strict=True):
            cached = self._evaluation_cache.get(key)
            if cached is not None:
                self._evaluation_cache.move_to_end(key)
                resolved[key] = cached
                self.evaluation_cache_hits += 1
            elif key in missing:
                # A duplicate within this batch is one avoided evaluation too.
                self.evaluation_cache_hits += 1
            else:
                missing[key] = row
                self.evaluation_cache_misses += 1

        missing_rows = tuple(missing.values())
        if self._executor is not None and missing_rows:
            evaluated = list(self._executor.map(_evaluate_row_worker, missing_rows))
        else:
            evaluated = [
                _evaluate_row(
                    row,
                    self.topology,
                    self.cable_map,
                    self.feasibility,
                    self.targets,
                    self.n_ieq_constr,
                )
                for row in missing_rows
            ]

        for key, result in zip(missing, evaluated, strict=True):
            immutable = (
                result[0],
                tuple(float(value) for value in result[1]),
                result[2],
            )
            resolved[key] = immutable
            self._evaluation_cache[key] = immutable
            self._evaluation_cache.move_to_end(key)
            if len(self._evaluation_cache) > _EVALUATION_CACHE_MAXSIZE:
                self._evaluation_cache.popitem(last=False)

        results = [resolved[key] for key in row_keys]

        for row_index, (objective_row, constraint_row, family) in enumerate(results):
            objectives[row_index] = objective_row
            constraints[row_index] = constraint_row
            families[row_index] = family

        out["F"] = objectives
        out["G"] = constraints
        out["topology_family"] = families

    @staticmethod
    def _evaluation_cache_key(row: np.ndarray) -> _EvaluationCacheKey:
        contiguous = np.ascontiguousarray(row, dtype=np.float64)
        return contiguous.tobytes()


def _evaluate_row(
    row: np.ndarray,
    topology: Topology,
    cable_map: Mapping[str, CableSpec],
    feasibility: FeasibilitySettings,
    targets: OptimizationTargets,
    n_ieq_constr: int,
) -> tuple[tuple[float, float], np.ndarray, str]:
    """Evaluate one genome row in-process or in a worker process."""

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
            min_pole_turn_radius_mm=feasibility.min_pole_turn_radius_mm,
            min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
            enforce_layer_nesting=feasibility.enforce_layer_nesting,
            geometry_tolerance_mm=feasibility.geometry_tolerance_mm,
        )
        if not result.is_feasible:
            constraint[0] = max(
                _normalized_geometry_violation(
                    violation.constraint_name,
                    violation.severity,
                    feasibility,
                    layer_index=violation.layer_index,
                )
                for violation in result.violations
            )
            return objective, constraint, family

        target_constraint_index = 1
        turn_budget_violation = False
        if targets.max_total_turns is not None:
            total_turns = sum(
                block.n_turns for layer in unit_design.layers for block in layer.blocks
            )
            constraint[target_constraint_index] = max(
                0.0,
                float(total_turns - targets.max_total_turns) / max(1.0, targets.max_total_turns),
            )
            turn_budget_violation |= constraint[target_constraint_index] > 0.0
            target_constraint_index += 1
        if targets.max_turns_per_layer is not None:
            per_layer_violation = sum(
                max(0, sum(block.n_turns for block in layer.blocks) - targets.max_turns_per_layer)
                for layer in unit_design.layers
            )
            constraint[target_constraint_index] = float(per_layer_violation) / max(
                1.0, targets.max_turns_per_layer
            )
            turn_budget_violation |= constraint[target_constraint_index] > 0.0
            target_constraint_index += 1
        if turn_budget_violation:
            return objective, constraint, family

        solved = solve_operating_point(unit_design, targets)
        field_quality = field_quality_objective(
            solved.design,
            targets.r_ref_mm,
            targets.max_order,
            normal_orders=targets.harmonic_orders or None,
            normal_targets=dict(targets.harmonic_targets),
            include_skew=not bool(targets.harmonic_orders),
            fidelity=targets.search_fidelity,
        )
        objective = (field_quality, _PENALTY)
        if targets.fixed_current_a is not None:
            constraint[target_constraint_index] = fixed_current_field_violation(solved, targets)
        elif targets.min_current_a is not None or targets.max_current_a is not None:
            constraint[target_constraint_index] = current_range_violation(
                abs(solved.operating_current_a),
                targets.min_current_a,
                targets.max_current_a,
            )
        # NSGA-II needs both objective values for every geometrically valid
        # design.  Short-circuiting margin when harmonics/current failed made
        # the entire infeasible population share a 1e12 margin objective and
        # falsely left the margin constraint at zero.  That destroys the
        # trade-off gradient needed to evolve more conductor while improving
        # field quality, and makes near-feasible diagnostics misleading.
        margin_percent = load_line_margin_objective(
            solved.design,
            tuple(layer.cable_id for layer in topology.layers),
            targets.cadata_by_layer,
            targets.temperature_k,
            fidelity=targets.search_fidelity,
        )
        objective = (field_quality, -margin_percent)
        return objective, constraint, family
    except (KeyError, ValueError, ZeroDivisionError):
        # An evaluation failure is not evidence that any secondary hard
        # constraint passed.  Mark the whole row invalid so it cannot outrank
        # a physically evaluated near-feasible design merely because its
        # unevaluated constraint slots were left at zero.
        constraint[:] = 1.0
        return (_PENALTY, _PENALTY), constraint, family


def _normalized_geometry_violation(
    constraint_name: str,
    severity: float,
    feasibility: FeasibilitySettings,
    *,
    layer_index: int | None = None,
) -> float:
    """Convert heterogeneous geometry violations to dimensionless utilization.

    Taking the maximum makes the value independent of the number of turn pairs
    that happen to report the same collision.
    """

    if constraint_name == "midplane_clearance":
        scale = max(0.1, feasibility.min_gap_mm)
    elif constraint_name == "pole_clearance":
        scale = max(0.1, feasibility.min_pole_gap_mm or 0.0)
    elif constraint_name == "first_layer_pole_turn_radius":
        scale = max(0.1, feasibility.min_pole_turn_radius_mm or 0.0)
    elif constraint_name == "inter_layer_spacing":
        scale = max(0.1, feasibility.min_layer_clearance_mm)
    elif constraint_name in {"inter_block_gap", "electrical_gap", "wedge_gap"}:
        scale = max(
            0.1,
            _layerwise_setting(
                feasibility.min_inter_block_gap_mm,
                layer_index,
            ),
        )
    elif constraint_name == "pole_angle_limit":
        scale = 5.0
    else:
        scale = 0.1
    return max(0.0, float(severity)) / scale


def _layerwise_setting(
    value: float | Sequence[float] | None,
    layer_index: int | None,
) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Real):
        return float(value)
    values = tuple(float(item) for item in value)
    if not values:
        return 0.0
    if layer_index is None:
        return max(values)
    if layer_index < 0 or layer_index >= len(values):
        raise ValueError("layerwise feasibility setting does not match the design layers")
    return values[layer_index]


# Process-pool worker state: set once per worker process via
# _init_worker, then reused across every row that process evaluates. Kept
# as module globals rather than passed per-call so the (relatively large,
# static-for-the-whole-run) topology/cable_map/feasibility/targets objects
# are pickled only once at pool startup, not once per row.
_worker_topology: Topology
_worker_cable_map: Mapping[str, CableSpec]
_worker_feasibility: FeasibilitySettings
_worker_targets: OptimizationTargets
_worker_n_ieq_constr: int
_worker_repair: object


def _init_worker(
    topology: Topology,
    cable_map: Mapping[str, CableSpec],
    feasibility: FeasibilitySettings,
    targets: OptimizationTargets,
    n_ieq_constr: int,
    peak_field_filaments_per_axis: int,
) -> None:
    global \
        _worker_topology, \
        _worker_cable_map, \
        _worker_feasibility, \
        _worker_targets, \
        _worker_n_ieq_constr, \
        _worker_repair
    _worker_topology = topology
    _worker_cable_map = cable_map
    _worker_feasibility = feasibility
    _worker_targets = targets
    _worker_n_ieq_constr = n_ieq_constr
    # Imported lazily after module initialization to avoid a module-level
    # problem.py <-> runner.py cycle.
    from .runner import CampaignRepair

    _worker_repair = CampaignRepair(topology, feasibility, targets)
    # Windows uses "spawn" for new processes, so each worker re-imports
    # dot.optimize.objectives fresh -- it does NOT inherit the parent
    # process's runtime mutation of this module-level global (campaign
    # scripts set it to a cheaper SEARCH_DISCRETIZATION value). Without
    # this, workers would silently fall back to the expensive default,
    # defeating the whole point of the multi-fidelity search/verify split.
    _objectives_module.PEAK_FIELD_FILAMENTS_PER_AXIS = peak_field_filaments_per_axis


def _evaluate_row_worker(row: np.ndarray) -> tuple[tuple[float, float], np.ndarray, str]:
    return _evaluate_row(
        row,
        _worker_topology,
        _worker_cable_map,
        _worker_feasibility,
        _worker_targets,
        _worker_n_ieq_constr,
    )


def _repair_sample_worker(sample: dict[str, object]) -> dict[str, object]:
    return _worker_repair.repair_sample(sample)  # type: ignore[attr-defined,no-any-return]
