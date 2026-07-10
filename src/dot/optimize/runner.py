"""Thin NSGA-II campaign runner."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.duplicate import NoDuplicateElimination
from pymoo.core.mixed import MixedVariableMating
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.optimize import minimize

from dot.geometry import DipoleDesign

from .genome import Topology, decode, flatten_mixed_genome, genome_variables
from .operating_point import operating_point
from .problem import (
    DipoleOptimizationProblem,
    FeasibilitySettings,
    MarginEvaluationExclusion,
    OptimizationTargets,
)


@dataclass(frozen=True, slots=True)
class ParetoCandidate:
    """One feasible Pareto candidate returned by ``run_campaign``."""

    genome: np.ndarray
    design: DipoleDesign
    objectives: tuple[float, float]


@dataclass(frozen=True, slots=True)
class ParetoResult:
    """Feasible non-dominated candidates from an optimization run."""

    candidates: tuple[ParetoCandidate, ...]
    excluded_margin_layers: tuple[MarginEvaluationExclusion, ...] = ()


class ConstructiveMixedVariableSampling(Sampling):
    """Construct a mixed-variable initial population with ordered layer phis."""

    def __init__(self, topology: Topology, feasibility: FeasibilitySettings) -> None:
        super().__init__()
        self.topology = topology
        self.feasibility = feasibility
        self._variables = genome_variables(topology)

    def _do(self, problem, n_samples, random_state=None, **kwargs):  # noqa: ANN001, ANN003
        rng = np.random.default_rng() if random_state is None else random_state
        samples: list[dict[str, float | int]] = []
        for _ in range(n_samples):
            sample: dict[str, float | int] = {}
            by_layer: dict[int, list[tuple[str, int, tuple[float, float]]]] = {}
            for variable in self._variables:
                if variable.block_index is not None and variable.name.endswith("_phi_deg"):
                    by_layer.setdefault(variable.layer_index, []).append(
                        (variable.name, variable.block_index, variable.bounds)
                    )
                lower, upper = variable.bounds
                if variable.kind == "binary":
                    sample[variable.name] = bool(rng.integers(0, 2))
                elif variable.kind == "integer":
                    sample[variable.name] = int(rng.integers(int(lower), int(upper) + 1))
                else:
                    sample[variable.name] = float(rng.uniform(lower, upper))

            for layer_index, phi_variables in by_layer.items():
                active_phi_variables = [
                    item for item in phi_variables if _block_is_active(sample, layer_index, item[1])
                ]
                if not active_phi_variables:
                    continue
                layer = self.topology.layers[layer_index]
                radius_name = f"layer_{layer_index}_inner_radius_mm"
                radius = float(sample[radius_name])
                min_gap_deg = _minimum_phi_gap_deg(
                    radius,
                    self.topology.cables[layer.cable_id].insulated_width_inner_mm,
                    self.feasibility.min_gap_mm,
                )
                phis = _ordered_phi_values(active_phi_variables, min_gap_deg, rng)
                for name, phi in phis.items():
                    sample[name] = phi

            samples.append(sample)
        return samples


class PhiOrderingRepair(Repair):
    """Restore per-layer block ordering after mixed-variable variation."""

    def __init__(self, topology: Topology, feasibility: FeasibilitySettings) -> None:
        super().__init__()
        self.topology = topology
        self.feasibility = feasibility
        self._variables = genome_variables(topology)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        for sample in x:
            if not isinstance(sample, dict):
                continue
            self._repair_sample(sample)
        return x

    def _repair_sample(self, sample: dict[str, float | int]) -> None:
        for layer_index, layer in enumerate(self.topology.layers):
            phi_variables = [
                variable
                for variable in self._variables
                if variable.layer_index == layer_index
                and variable.block_index is not None
                and variable.name.endswith("_phi_deg")
                and _block_is_active(sample, layer_index, variable.block_index)
            ]
            if len(phi_variables) < 2:
                continue

            radius = float(sample[f"layer_{layer_index}_inner_radius_mm"])
            min_gap_deg = _minimum_phi_gap_deg(
                radius,
                self.topology.cables[layer.cable_id].insulated_width_inner_mm,
                self.feasibility.min_gap_mm,
            )
            sorted_phis = sorted(float(sample[variable.name]) for variable in phi_variables)
            previous = -math.inf
            for remaining_index, variable in enumerate(sorted(phi_variables, key=lambda item: item.block_index)):
                lower, upper = variable.bounds
                remaining_after = len(phi_variables) - remaining_index - 1
                max_phi = upper - remaining_after * min_gap_deg
                repaired = max(lower, previous + min_gap_deg, sorted_phis[remaining_index])
                repaired = min(max_phi, repaired)
                sample[variable.name] = float(min(max(repaired, lower), upper))
                previous = float(sample[variable.name])


def run_campaign(
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    pop_size: int = 8,
    n_gen: int = 3,
    seed: int | None = None,
) -> ParetoResult:
    """Run a small fixed-topology NSGA-II campaign and return feasible candidates."""

    problem = DipoleOptimizationProblem(topology, targets, feasibility, total_generations=n_gen)
    algorithm = _mixed_variable_nsga2(topology, feasibility, pop_size)
    result = minimize(
        problem,
        algorithm,
        ("n_gen", n_gen),
        seed=seed,
        callback=lambda algorithm: problem.set_generation(algorithm.n_gen),
        verbose=False,
    )

    genomes = _result_genomes(result.X, topology)
    objectives = np.atleast_2d(result.F) if result.F is not None else np.empty((0, 2))
    constraints = np.atleast_2d(result.G) if result.G is not None else np.empty((len(genomes), 1))
    candidates: list[ParetoCandidate] = []
    for genome, objective, constraint in zip(genomes, objectives, constraints, strict=False):
        if np.all(constraint <= 0.0):
            unit_design = decode(genome, topology, topology.cables)
            solved = operating_point(unit_design, targets.target_bore_field_t)
            candidates.append(
                ParetoCandidate(
                    genome=np.asarray(genome, dtype=float),
                    design=solved.design,
                    objectives=(float(objective[0]), float(objective[1])),
                )
            )
    return ParetoResult(
        candidates=tuple(candidates),
        excluded_margin_layers=_margin_exclusions(targets),
    )


def _mixed_variable_nsga2(
    topology: Topology,
    feasibility: FeasibilitySettings,
    pop_size: int,
) -> NSGA2:
    # pymoo's default duplicate elimination converts X to a float array, which
    # crashes for dict-valued mixed-variable genomes. Keep it disabled until DOT
    # has a mixed-genome duplicate comparator.
    duplicate_elimination = NoDuplicateElimination()
    repair = PhiOrderingRepair(topology, feasibility)
    return NSGA2(
        pop_size=pop_size,
        sampling=ConstructiveMixedVariableSampling(topology, feasibility),
        mating=MixedVariableMating(repair=repair, eliminate_duplicates=duplicate_elimination),
        eliminate_duplicates=duplicate_elimination,
    )


def _result_genomes(x, topology: Topology) -> np.ndarray:  # noqa: ANN001
    if x is None:
        return np.empty((0, topology.n_var))
    if isinstance(x, dict):
        return np.atleast_2d(flatten_mixed_genome(x, topology))
    if isinstance(x, np.ndarray) and x.dtype == object and x.size and isinstance(x.flat[0], dict):
        return np.asarray([flatten_mixed_genome(row, topology) for row in x], dtype=float)
    if isinstance(x, list) and x and isinstance(x[0], dict):
        return np.asarray([flatten_mixed_genome(row, topology) for row in x], dtype=float)
    return np.atleast_2d(np.asarray(x, dtype=float))


def _minimum_phi_gap_deg(radius_mm: float, cable_width_mm: float, min_gap_mm: float) -> float:
    radial_floor = max(1.0e-9, radius_mm)
    gap_angle = math.degrees(math.asin(min(1.0, max(0.0, min_gap_mm) / radial_floor)))
    cable_angle = math.degrees(math.asin(min(1.0, max(0.0, cable_width_mm) / radial_floor)))
    return gap_angle + cable_angle


def _ordered_phi_values(
    phi_variables: list[tuple[str, int, tuple[float, float]]],
    min_gap_deg: float,
    rng: np.random.Generator,
) -> dict[str, float]:
    ordered = sorted(phi_variables, key=lambda item: item[1])
    values: dict[str, float] = {}
    previous = -math.inf
    for remaining_index, (name, _block_index, bounds) in enumerate(ordered):
        lower, upper = bounds
        min_phi = max(lower, previous + min_gap_deg)
        remaining_after = len(ordered) - remaining_index - 1
        max_phi = min(upper, upper - remaining_after * min_gap_deg)
        if min_phi <= max_phi:
            phi = float(rng.uniform(min_phi, max_phi))
        else:
            phi = float(min(max(min_phi, lower), upper))
        values[name] = phi
        previous = phi
    return values


def _block_is_active(sample: dict[str, float | int], layer_index: int, block_index: int) -> bool:
    if block_index == 0:
        return True
    return bool(sample.get(f"layer_{layer_index}_block_{block_index}_active", True))


def _margin_exclusions(targets: OptimizationTargets) -> tuple[MarginEvaluationExclusion, ...]:
    exclusions = {exclusion.layer_index: exclusion for exclusion in targets.excluded_margin_layers}
    for layer_index, layer_data in enumerate(targets.cadata_by_layer):
        if layer_data is None and layer_index not in exclusions:
            exclusions[layer_index] = MarginEvaluationExclusion(
                layer_index=layer_index,
                reason="conductor data unavailable; load-line margin not evaluated",
            )
    return tuple(exclusions[index] for index in sorted(exclusions))
