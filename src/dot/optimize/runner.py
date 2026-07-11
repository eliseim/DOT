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
                cable_width = self.topology.cables[layer.cable_id].insulated_width_inner_mm
                turn_counts = _sample_turn_counts(sample, layer_index, active_phi_variables)
                phis = _ordered_phi_values(
                    active_phi_variables,
                    turn_counts,
                    radius,
                    cable_width,
                    _repair_target_gap_mm(self.feasibility),
                    rng,
                )
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
            cable_width = self.topology.cables[layer.cable_id].insulated_width_inner_mm
            # genome_bounds() partitions the layer's phi range into per-block
            # windows with block 0 nearest phi_upper (midplane, where its
            # hard-fixed alpha=0 is valid) and increasing block index moving
            # toward phi_lower (the pole). Process from the highest block
            # index (lowest phi) to block 0 (highest phi) to match.
            ordered = sorted(phi_variables, key=lambda item: item.block_index, reverse=True)
            # Turns stack from a block's own phi anchor toward increasing phi
            # (see Block.turns()/_arc_stacked_anchor), so the gap required
            # between block i and block i+1 is governed by block i's own
            # n_turns, not block i+1's.
            gaps = [
                _minimum_phi_gap_deg(
                    radius,
                    cable_width,
                    _repair_target_gap_mm(self.feasibility),
                    n_turns=_sample_n_turns(sample, layer_index, variable.block_index),
                )
                for variable in ordered
            ]
            sorted_phis = sorted(float(sample[variable.name]) for variable in phi_variables)
            previous = -math.inf
            for remaining_index, variable in enumerate(ordered):
                lower, upper = variable.bounds
                required_gap = gaps[remaining_index - 1] if remaining_index > 0 else 0.0
                remaining_gap_sum = sum(gaps[remaining_index : len(ordered) - 1])
                max_phi = upper - remaining_gap_sum
                repaired = max(lower, previous + required_gap, sorted_phis[remaining_index])
                repaired = min(max_phi, repaired)
                sample[variable.name] = float(min(max(repaired, lower), upper))
                previous = float(sample[variable.name])


class TurnBudgetRepair(Repair):
    """Reduce active turn counts to satisfy structural turn budgets after mating."""

    def __init__(self, topology: Topology, targets: OptimizationTargets) -> None:
        super().__init__()
        self.topology = topology
        self.targets = targets
        self._variables = genome_variables(topology)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        for sample in x:
            if not isinstance(sample, dict):
                continue
            self._repair_sample(sample)
        return x

    def _repair_sample(self, sample: dict[str, float | int]) -> None:
        if self.targets.max_total_turns is None and self.targets.max_turns_per_layer is None:
            return

        by_layer = self._active_turn_variables(sample)
        if self.targets.max_turns_per_layer is not None:
            for turn_variables in by_layer.values():
                self._reduce_to_budget(sample, turn_variables, self.targets.max_turns_per_layer)

        if self.targets.max_total_turns is not None:
            all_turn_variables = [
                variable
                for layer_variables in by_layer.values()
                for variable in layer_variables
            ]
            self._reduce_to_budget(sample, all_turn_variables, self.targets.max_total_turns)

    def _active_turn_variables(
        self,
        sample: dict[str, float | int],
    ) -> dict[int, list[tuple[str, int, float]]]:
        by_layer: dict[int, list[tuple[str, int, float]]] = {}
        for variable in self._variables:
            if (
                variable.block_index is None
                or not variable.name.endswith("_n_turns")
                or not _block_is_active(sample, variable.layer_index, variable.block_index)
            ):
                continue
            lower, _upper = variable.bounds
            by_layer.setdefault(variable.layer_index, []).append(
                (variable.name, variable.block_index, lower)
            )
        return by_layer

    @staticmethod
    def _reduce_to_budget(
        sample: dict[str, float | int],
        turn_variables: list[tuple[str, int, float]],
        budget: int,
    ) -> None:
        surplus = sum(int(round(float(sample[name]))) for name, _block_index, _lower in turn_variables) - budget
        while surplus > 0:
            reducible = [
                (int(round(float(sample[name]))), block_index, name, int(round(lower)))
                for name, block_index, lower in turn_variables
                if int(round(float(sample[name]))) > int(round(lower))
            ]
            if not reducible:
                return
            current, _block_index, name, lower = max(reducible)
            reduction = min(surplus, current - lower)
            sample[name] = current - reduction
            surplus -= reduction


class AlphaAlignmentRepair(Repair):
    """Clamp each free-alpha block's alpha_deg into a window around its own phi.

    Block index 0 has alpha_deg hard-fixed to 0 (see genome.py), valid
    because genome_bounds() places it nearest the midplane (phi=90deg).
    Blocks 1..n-1 have a free alpha gene, but ordinary crossover/mutation
    treats it as independent of phi -- after mating, a block's phi can be
    repaired to a very different (more pole-ward) value than the alpha
    gene was tuned for, leaving alpha badly mismatched and producing
    self-overlapping turns that no other repair catches (phi-ordering and
    turn-budget repair don't touch alpha_deg at all).

    A turn's axes rotate with alpha only (see primitives.py's
    absolute-global-frame alpha convention); they align with the block's
    true local radial direction (sin(phi), cos(phi)) when
    alpha = phi - 90. Confirmed empirically (coordinator) against
    check_turn_non_intersection that alpha at or modestly above that
    target stays valid across realistic turn counts, while alpha far
    below it (or too far above, for high turn counts) does not. Clamping
    into [target, target + 15] (intersected with the block's own
    alpha_bounds) keeps blocks close to structurally valid without
    collapsing the alpha gene to a single deterministic value.
    """

    _WINDOW_ABOVE_TARGET_DEG = 15.0

    def __init__(self, topology: Topology) -> None:
        super().__init__()
        self.topology = topology
        self._variables = genome_variables(topology)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        for sample in x:
            if not isinstance(sample, dict):
                continue
            self._repair_sample(sample)
        return x

    def _repair_sample(self, sample: dict[str, float | int]) -> None:
        for variable in self._variables:
            if (
                variable.block_index is None
                or variable.block_index == 0
                or not variable.name.endswith("_alpha_deg")
            ):
                continue
            phi_name = f"layer_{variable.layer_index}_block_{variable.block_index}_phi_deg"
            phi = float(sample.get(phi_name, 90.0))
            target = phi - 90.0
            lower, upper = variable.bounds
            window_lower = max(lower, target)
            window_upper = min(upper, target + self._WINDOW_ABOVE_TARGET_DEG)
            current = float(sample[variable.name])
            if window_lower <= window_upper:
                sample[variable.name] = float(min(max(current, window_lower), window_upper))
            else:
                sample[variable.name] = float(min(max(current, lower), upper))


class CampaignRepair(Repair):
    """Apply all mixed-variable structural repairs in a fixed sequence.

    Turn-budget repair runs first so that phi-ordering repair computes its
    turn-count-aware gaps from each block's final, budget-compliant
    ``n_turns`` rather than a pre-reduction value. Reversing the order is
    still geometrically safe (phi gaps computed from an inflated n_turns
    are only overly conservative, never insufficient, since
    TurnBudgetRepair only ever reduces n_turns), but running turn-budget
    repair first avoids that unnecessary conservatism. Alpha-alignment
    repair runs last since it depends on each block's final phi.
    """

    def __init__(self, topology: Topology, feasibility: FeasibilitySettings, targets: OptimizationTargets) -> None:
        super().__init__()
        self._phi_ordering = PhiOrderingRepair(topology, feasibility)
        self._turn_budget = TurnBudgetRepair(topology, targets)
        self._alpha_alignment = AlphaAlignmentRepair(topology)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        x = self._turn_budget._do(problem, x, **kwargs)
        x = self._phi_ordering._do(problem, x, **kwargs)
        return self._alpha_alignment._do(problem, x, **kwargs)


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
    algorithm = _mixed_variable_nsga2(topology, feasibility, pop_size, targets)
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
    targets: OptimizationTargets | None = None,
) -> NSGA2:
    # pymoo's default duplicate elimination converts X to a float array, which
    # crashes for dict-valued mixed-variable genomes. Keep it disabled until DOT
    # has a mixed-genome duplicate comparator.
    duplicate_elimination = NoDuplicateElimination()
    if targets is None:
        targets = OptimizationTargets(
            target_bore_field_t=0.0,
            r_ref_mm=0.0,
            max_order=1,
            cadata_by_layer=(),
            temperature_k=0.0,
        )
    repair = CampaignRepair(topology, feasibility, targets)
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


def _minimum_phi_gap_deg(
    radius_mm: float,
    cable_width_mm: float,
    min_gap_mm: float,
    *,
    n_turns: int = 1,
) -> float:
    """Minimum anchor-to-anchor gap so a block's real turn footprint clears its neighbor.

    ``Block.turns()`` stacks each successive turn one insulated cable width
    further from the block's own ``phi_deg`` anchor (toward increasing
    phi) -- see ``_arc_stacked_anchor`` in ``dot.geometry.primitives``. So a
    block with ``n_turns`` turns spans roughly ``n_turns`` cable widths of
    angle starting at its anchor, not just one. The gap to the next block
    (at higher phi) must clear that whole span plus the explicit
    clearance, or ``check_turn_non_intersection`` will find real overlap
    even though the anchors themselves look adequately spaced.
    """

    radial_floor = max(1.0e-9, radius_mm)
    gap_angle = math.degrees(math.asin(min(1.0, max(0.0, min_gap_mm) / radial_floor)))
    cable_angle = math.degrees(math.asin(min(1.0, max(0.0, cable_width_mm) / radial_floor)))
    return gap_angle + cable_angle * max(1, int(n_turns))


def _ordered_phi_values(
    phi_variables: list[tuple[str, int, tuple[float, float]]],
    turn_counts: dict[int, int],
    radius_mm: float,
    cable_width_mm: float,
    min_gap_mm: float,
    rng: np.random.Generator,
) -> dict[str, float]:
    # See PhiOrderingRepair._repair_sample: block 0 sits nearest phi_upper
    # (midplane) and increasing block index moves toward phi_lower (pole).
    ordered = sorted(phi_variables, key=lambda item: item[1], reverse=True)
    # gaps[i] is the gap required after block i (i.e. the transition from
    # block i to block i+1), sized from block i's own n_turns.
    gaps = [
        _minimum_phi_gap_deg(radius_mm, cable_width_mm, min_gap_mm, n_turns=turn_counts.get(block_index, 1))
        for _, block_index, _bounds in ordered
    ]
    values: dict[str, float] = {}
    previous = -math.inf
    for remaining_index, (name, _block_index, bounds) in enumerate(ordered):
        lower, upper = bounds
        required_gap = gaps[remaining_index - 1] if remaining_index > 0 else 0.0
        min_phi = max(lower, previous + required_gap)
        remaining_gap_sum = sum(gaps[remaining_index : len(ordered) - 1])
        max_phi = min(upper, upper - remaining_gap_sum)
        if min_phi <= max_phi:
            phi = float(rng.uniform(min_phi, max_phi))
        else:
            phi = float(min(max(min_phi, lower), upper))
        values[name] = phi
        previous = phi
    return values


def _sample_n_turns(sample: dict[str, float | int], layer_index: int, block_index: int) -> int:
    return int(round(float(sample.get(f"layer_{layer_index}_block_{block_index}_n_turns", 1))))


def _sample_turn_counts(
    sample: dict[str, float | int],
    layer_index: int,
    phi_variables: list[tuple[str, int, tuple[float, float]]],
) -> dict[int, int]:
    return {
        block_index: _sample_n_turns(sample, layer_index, block_index)
        for _name, block_index, _bounds in phi_variables
    }


def _repair_target_gap_mm(feasibility: FeasibilitySettings) -> float:
    """Minimum inter-block gap the phi repair/sampler should target.

    ``feasibility.min_gap_mm`` is the midplane-clearance value (dd's C4),
    which is unrelated to and typically much smaller than the inter-block
    gap requirement (dd's C7a/C7b, ``min_inter_block_gap_mm``). Repairing
    only to ``min_gap_mm`` left offspring with real (but unrepaired)
    ``inter_block_gap`` violations whenever a campaign configured a
    stricter wedge-gap minimum -- use whichever is larger.
    """

    return max(feasibility.min_gap_mm, feasibility.min_inter_block_gap_mm or 0.0)


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
