"""Thin NSGA-II campaign runner."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize

from dot.geometry import DipoleDesign

from .genome import Topology, decode
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


def run_campaign(
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    pop_size: int = 8,
    n_gen: int = 3,
    seed: int | None = None,
) -> ParetoResult:
    """Run a small fixed-topology NSGA-II campaign and return feasible candidates."""

    problem = DipoleOptimizationProblem(topology, targets, feasibility)
    algorithm = NSGA2(pop_size=pop_size)
    result = minimize(
        problem,
        algorithm,
        ("n_gen", n_gen),
        seed=seed,
        verbose=False,
    )

    genomes = np.atleast_2d(result.X) if result.X is not None else np.empty((0, topology.n_var))
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


def _margin_exclusions(targets: OptimizationTargets) -> tuple[MarginEvaluationExclusion, ...]:
    exclusions = {exclusion.layer_index: exclusion for exclusion in targets.excluded_margin_layers}
    for layer_index, layer_data in enumerate(targets.cadata_by_layer):
        if layer_data is None and layer_index not in exclusions:
            exclusions[layer_index] = MarginEvaluationExclusion(
                layer_index=layer_index,
                reason="conductor data unavailable; load-line margin not evaluated",
            )
    return tuple(exclusions[index] for index in sorted(exclusions))
