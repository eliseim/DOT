"""Thin NSGA-II campaign runner."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.duplicate import NoDuplicateElimination
from pymoo.core.infill import InfillCriterion
from pymoo.core.mixed import MixedVariableMating
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.optimize import minimize

from dot.geometry import DipoleDesign
from dot.geometry.constraints import check_feasibility, check_layer_nesting

from .genome import GenomeVariable, Topology, decode, flatten_mixed_genome, genome_variables
from .operating_point import operating_point
from .problem import (
    DipoleOptimizationProblem,
    FeasibilitySettings,
    MarginEvaluationExclusion,
    OptimizationTargets,
)
from .topology_survival import TopologyAwareRankAndCrowding, TopologySurvivalConfig


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
            # Slack-packing construction (task 0046, replaces a prior
            # greedy floor-clamp): a greedy clamp assigns each block the
            # smallest value that satisfies ordering/gaps against the
            # previous block, so any block whose proposed value doesn't
            # already clear that floor snaps to EXACTLY its own window's
            # lower bound -- using none of that window's interior, no
            # matter how wide it is (confirmed empirically: a fully
            # collapsed sample repairs to every block sitting at its
            # window's lower edge). Only the last-processed block (block 0)
            # could ever use its own window's interior, so any slack in the
            # layer's phi range concentrated there instead of spreading
            # across all blocks -- a quiet, systematic bias in exactly the
            # gene that gates C2/C4/C5/C10/C19. Instead, distribute the
            # layer's total slack (available span minus required gaps)
            # evenly across every block's position, ignoring each block's
            # individually-proposed value entirely: this is a
            # reconstruction, consistent with how DOT's other repairs
            # (TurnBudgetRepair, GroundTruthRepair) already rebuild rather
            # than minimally nudge.
            total_required_gap = sum(gaps[:-1])
            available_span = ordered[-1].bounds[1] - ordered[0].bounds[0]
            slack = max(0.0, available_span - total_required_gap)
            slack_share = slack / len(ordered)
            position = ordered[0].bounds[0]
            for index, variable in enumerate(ordered):
                position += slack_share if index == 0 else gaps[index - 1] + slack_share
                lower, upper = variable.bounds
                position = float(min(max(position, lower), upper))
                sample[variable.name] = position


class LayerNestingRepair(Repair):
    """Shift an outer layer's blocks toward the midplane to restore nesting.

    Task 0037/0043: :func:`check_layer_nesting` (C10) was implemented but
    left gated off (``enforce_layer_nesting=False``) because nothing
    repaired a violation -- enabling it collapsed the whole population.
    Mirrors dipole_designer's own C10 repair: bisection-search a single
    scalar phi shift, applied to every active block in the violating outer
    layer, that eliminates the violation. A uniform shift is a pure
    translation, so it cannot disturb the ordering/gaps
    ``PhiOrderingRepair`` already established -- this is why it must run
    strictly after that repair. Applying the shift moves blocks toward the
    midplane (increasing phi, away from the pole) because that is the
    direction that pulls conductor vertices back onto the accepted side of
    the inner layer's pole-side nesting edge (see
    :func:`check_layer_nesting`'s docstring). The shift is capped by
    ``FeasibilitySettings.max_nesting_repair_deg`` and by each block's own
    genome-space upper phi bound; if the cap is reached before the
    violation clears, the sample is left untouched -- like
    ``GroundTruthRepair``, this repair never raises, it just leaves
    residual infeasibility for the existing penalty/graded-constraint
    handling in ``DipoleOptimizationProblem`` to deal with.
    """

    _MAX_BISECTION_ITERATIONS = 40

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
        cap = self.feasibility.max_nesting_repair_deg
        if cap is None or cap <= 0.0:
            return
        for layer_index in range(1, len(self.topology.layers)):
            self._repair_layer(sample, layer_index, cap)

    def _repair_layer(self, sample: dict[str, float | int], layer_index: int, cap: float) -> None:
        phi_variables = [
            variable
            for variable in self._variables
            if variable.layer_index == layer_index
            and variable.block_index is not None
            and variable.name.endswith("_phi_deg")
            and _block_is_active(sample, layer_index, variable.block_index)
        ]
        if not phi_variables:
            return
        if not self._layer_has_nesting_violation(sample, layer_index):
            return

        max_shift = min(
            cap,
            *(variable.bounds[1] - float(sample[variable.name]) for variable in phi_variables),
        )
        if max_shift <= 0.0:
            return
        if not self._layer_has_nesting_violation(sample, layer_index, shift=max_shift):
            self._apply_shift(sample, phi_variables, self._bisect_minimum_shift(sample, layer_index, phi_variables, max_shift))
        # else: even the maximum permitted shift cannot clear the
        # violation -- leave the sample untouched, per this class's
        # docstring.

    def _bisect_minimum_shift(
        self,
        sample: dict[str, float | int],
        layer_index: int,
        phi_variables: list[GenomeVariable],
        max_shift: float,
    ) -> float:
        lower, upper = 0.0, max_shift
        for _ in range(self._MAX_BISECTION_ITERATIONS):
            midpoint = (lower + upper) / 2.0
            if self._layer_has_nesting_violation(sample, layer_index, shift=midpoint):
                lower = midpoint
            else:
                upper = midpoint
        return upper

    def _layer_has_nesting_violation(
        self,
        sample: dict[str, float | int],
        layer_index: int,
        *,
        shift: float = 0.0,
    ) -> bool:
        probe = dict(sample) if shift else sample
        if shift:
            for variable in self._variables:
                if (
                    variable.layer_index == layer_index
                    and variable.block_index is not None
                    and variable.name.endswith("_phi_deg")
                    and _block_is_active(sample, layer_index, variable.block_index)
                ):
                    probe[variable.name] = float(sample[variable.name]) + shift
        genome = flatten_mixed_genome(probe, self.topology)
        design = decode(genome, self.topology, self.topology.cables)
        return any(violation.layer_index == layer_index for violation in check_layer_nesting(design))

    @staticmethod
    def _apply_shift(sample: dict[str, float | int], phi_variables: list[GenomeVariable], shift: float) -> None:
        if shift <= 0.0:
            return
        for variable in phi_variables:
            sample[variable.name] = float(sample[variable.name]) + shift


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


class GroundTruthRepair(Repair):
    """Final safety-net repair: verify against real check_feasibility, shrink if not.

    PhiOrderingRepair, TurnBudgetRepair, and AlphaAlignmentRepair are all
    formula-based -- they restore structural invariants (ordering,
    budgets, an approximate alpha target) without ever calling
    :func:`check_feasibility` themselves. Confirmed empirically
    (coordinator) that this is not sufficient: even a single turn built
    from AlphaAlignmentRepair's "aligned" alpha target can land well
    outside a real constraint (e.g. ``check_pole_angle_limit``'s
    minimum-angle-from-pole requirement) for blocks positioned close to a
    layer's pole-ward bound, because a finite cable width subtends a much
    larger angle at small angle-from-pole than the formulas account for.

    This mirrors the campaign's own initial-population sampler
    (``ActiveAwareGrowthSampling``), which uses real ``check_feasibility``
    as ground truth while growing turns and reliably produces a healthy
    population -- but nothing did the equivalent after mating. This repair
    closes that gap: verify the fully-repaired sample against real
    feasibility, and if still infeasible, greedily shrink it (reduce the
    most-turn-heavy active non-block-0 block by one turn, or deactivate it
    once at its lower bound; fall back to block 0 only once no other
    active block remains) until feasible or a bounded number of attempts
    is exhausted. A sample that still can't be repaired within that budget
    is left as-is -- the existing graded/``_PENALTY`` handling in
    ``DipoleOptimizationProblem`` still applies to it.
    """

    _MAX_ATTEMPTS = 40

    def __init__(
        self,
        topology: Topology,
        feasibility: FeasibilitySettings,
    ) -> None:
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
        for _attempt in range(self._MAX_ATTEMPTS):
            genome = flatten_mixed_genome(sample, self.topology)
            unit_design = decode(genome, self.topology, self.topology.cables)
            result = check_feasibility(
                unit_design,
                aperture_radius_mm=self.topology.aperture_radius_mm,
                min_gap_mm=self.feasibility.min_gap_mm,
                max_angle_deg=self.feasibility.max_angle_deg,
                min_layer_clearance_mm=self.feasibility.min_layer_clearance_mm,
                min_pole_gap_mm=self.feasibility.min_pole_gap_mm,
                min_inter_block_gap_mm=self.feasibility.min_inter_block_gap_mm,
                enforce_layer_nesting=self.feasibility.enforce_layer_nesting,
            )
            if result.is_feasible:
                return
            if not self._shrink_worst_block(sample, result):
                return

    def _shrink_worst_block(self, sample: dict[str, float | int], result) -> bool:  # noqa: ANN001
        violated_decode_space = {
            (v.layer_index, v.block_index) for v in result.violations if v.block_index is not None
        }
        violated_decode_space |= {
            (v.other_layer_index, v.other_block_index)
            for v in result.violations
            if v.other_block_index is not None
        }
        # Violation.block_index is the block's position in the *decoded*
        # design (decode() skips inactive genome slots and re-indexes the
        # survivors from 0), not its genome-space index (the one used in
        # sample dict keys like "layer_L_block_G_n_turns"). Translate before
        # touching the sample, or this can end up "fixing" an unrelated
        # (possibly already-inactive) genome slot while the real offender
        # is left untouched.
        violated = {
            (layer_index, self._genome_block_index(sample, layer_index, decode_block_index))
            for layer_index, decode_block_index in violated_decode_space
        }
        candidates = [
            (layer_index, block_index)
            for layer_index, block_index in violated
            if block_index is not None and block_index != 0
        ]
        if not candidates:
            candidates = [(li, bi) for li, bi in violated if bi is not None]
        if not candidates:
            return False

        best: tuple[int, int, str, int] | None = None
        for layer_index, block_index in candidates:
            turns_name = f"layer_{layer_index}_block_{block_index}_n_turns"
            if turns_name not in sample:
                continue
            current = int(round(float(sample[turns_name])))
            variable = next(v for v in self._variables if v.name == turns_name)
            lower = int(round(variable.bounds[0]))
            if best is None or current > best[0]:
                best = (current, lower, turns_name, block_index)

        if best is None:
            return False
        current, lower, turns_name, block_index = best
        if current > lower:
            sample[turns_name] = current - 1
            return True
        if block_index != 0:
            active_name = turns_name.replace("_n_turns", "_active")
            # A missing key means "active" (see _block_is_active's own
            # default) -- deactivation must still be possible by *setting*
            # the key, not skipped just because it doesn't exist yet.
            if bool(sample.get(active_name, True)):
                sample[active_name] = False
                return True
        return False

    def _genome_block_index(
        self,
        sample: dict[str, float | int],
        layer_index: int,
        decode_block_index: int,
    ) -> int:
        """Map a decode-space block index (position among active blocks) to genome-space."""

        seen = -1
        n_blocks = self.topology.layers[layer_index].n_blocks
        for genome_block_index in range(n_blocks):
            if not _block_is_active(sample, layer_index, genome_block_index):
                continue
            seen += 1
            if seen == decode_block_index:
                return genome_block_index
        # decode_block_index should always resolve given a Violation was
        # produced from this same sample's decoded design; fall back to a
        # value with no matching genome key rather than raise, so the
        # caller's "turns_name not in sample" skip handles it gracefully.
        return -1


class CampaignRepair(Repair):
    """Apply all mixed-variable structural repairs in a fixed sequence.

    Turn-budget repair runs first so that phi-ordering repair computes its
    turn-count-aware gaps from each block's final, budget-compliant
    ``n_turns`` rather than a pre-reduction value. Reversing the order is
    still geometrically safe (phi gaps computed from an inflated n_turns
    are only overly conservative, never insufficient, since
    TurnBudgetRepair only ever reduces n_turns), but running turn-budget
    repair first avoids that unnecessary conservatism. Layer-nesting
    repair runs next: it applies a pure scalar-shift translation to an
    outer layer's blocks, which preserves the ordering/gaps phi-ordering
    repair just established, so it must run after that repair, not before
    it (translating unordered blocks could still leave them unordered).
    Alpha-alignment repair runs after both, since it depends on each
    block's final phi. GroundTruthRepair runs last: it verifies against
    real check_feasibility and greedily shrinks anything the formula-based
    repairs above still leave infeasible.
    """

    def __init__(self, topology: Topology, feasibility: FeasibilitySettings, targets: OptimizationTargets) -> None:
        super().__init__()
        self._phi_ordering = PhiOrderingRepair(topology, feasibility)
        self._layer_nesting = LayerNestingRepair(topology, feasibility)
        self._turn_budget = TurnBudgetRepair(topology, targets)
        self._alpha_alignment = AlphaAlignmentRepair(topology)
        self._ground_truth = GroundTruthRepair(topology, feasibility)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        x = self._turn_budget._do(problem, x, **kwargs)
        x = self._phi_ordering._do(problem, x, **kwargs)
        x = self._layer_nesting._do(problem, x, **kwargs)
        x = self._alpha_alignment._do(problem, x, **kwargs)
        return self._ground_truth._do(problem, x, **kwargs)


def refresh_population_admission(problem: DipoleOptimizationProblem, pop) -> None:  # noqa: ANN001
    """Re-score a pymoo population's cached F/G against the problem's current
    admission thresholds.

    ``DipoleOptimizationProblem.admission_thresholds()`` anneals the
    harmonic/margin/current thresholds by generation (task 0023), but pymoo's
    NSGA2 never re-evaluates a surviving individual's cached F/G once it is
    born -- only new offspring are scored under the current generation's
    threshold. Elitist survival then retains individuals whose G reflects a
    much looser threshold from whenever they were born, never re-validated
    against the tightening target: confirmed empirically (task 0042) via a
    campaign whose final "feasible" individuals had G<=0 (so counted as
    feasible) while their actual harmonic/margin values were 5-6x off the
    final target. Calling this once per generation, right after
    ``problem.set_generation()``, keeps every individual entering the next
    generation's mating/survival scored under the threshold that is
    currently active, both for honest reporting and for correct
    constraint-domination-based selection pressure.
    """

    x = pop.get("X")
    if x is None or len(x) == 0:
        return
    objectives, constraints = problem.evaluate(x, return_values_of=["F", "G"])
    pop.set("F", objectives)
    pop.set("G", constraints)


def run_campaign(
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    pop_size: int = 8,
    n_gen: int = 3,
    seed: int | None = None,
    topology_survival: TopologySurvivalConfig | None = None,
    adaptive_offspring: bool = False,
) -> ParetoResult:
    """Run a small fixed-topology NSGA-II campaign and return feasible candidates."""

    problem = DipoleOptimizationProblem(topology, targets, feasibility, total_generations=n_gen)
    algorithm = _mixed_variable_nsga2(topology, feasibility, pop_size, targets, topology_survival, adaptive_offspring)

    def _advance_generation(algorithm) -> None:  # noqa: ANN001
        problem.set_generation(algorithm.n_gen)
        refresh_population_admission(problem, algorithm.pop)

    result = minimize(
        problem,
        algorithm,
        ("n_gen", n_gen),
        seed=seed,
        callback=_advance_generation,
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


class AdaptiveOffspringMating(InfillCriterion):
    """Wrap ``MixedVariableMating`` with a cheap post-hoc validity retry (task 0047).

    Narrower than dipole_designer's own offspring-regeneration mechanism,
    whose main goal is reducing live-ROXIE call cost -- not DOT's
    bottleneck, since DOT's search never calls live ROXIE per-candidate.
    What's worth porting is the cheap pre-validity retry loop: after the
    wrapped mating (which already runs ``CampaignRepair``) produces
    offspring, check each one against real ``check_feasibility``; for any
    still infeasible, retry in bounded priority order -- first a fresh
    mating draw from the same parent pool (giving ``CampaignRepair``
    another attempt at a different random genome), then fall back to a
    feasibility-aware individual from the existing constructive sampler
    (reusing existing code rather than inventing a new retry taxonomy).
    Tracks the per-generation valid-offspring fraction for diagnostics;
    true mutation-strength modulation (dipole_designer's adaptive 0.2-1.0
    scale) is deferred to a follow-up task rather than forcing a fragile
    hook into pymoo's per-variable-kind operator internals.
    """

    def __init__(
        self,
        topology: Topology,
        feasibility: FeasibilitySettings,
        mating: MixedVariableMating,
        sampling: Sampling,
        max_regeneration_attempts: int = 3,
    ) -> None:
        super().__init__()
        self.topology = topology
        self.feasibility = feasibility
        self.mating = mating
        self.sampling = sampling
        self.max_regeneration_attempts = max_regeneration_attempts
        self.valid_fraction_history: list[float] = []

    def do(self, problem, pop, n_offsprings, random_state=None, **kwargs):  # noqa: ANN001, ANN003
        off = self.mating.do(problem, pop, n_offsprings, random_state=random_state, **kwargs)
        total = len(off)
        if total == 0:
            return off

        valid_flags = [self._is_valid(individual.get("X")) for individual in off]
        for index, is_valid in enumerate(valid_flags):
            if is_valid:
                continue
            replacement = self._regenerate(problem, pop, random_state, **kwargs)
            if replacement is not None:
                off[index].set("X", replacement)
                # Re-check rather than assume: the fallback constructive
                # sampler is feasibility-aware in practice, but nothing
                # guarantees it here -- an unconditional True would report
                # a false "fully valid" generation even if regeneration
                # produced something still infeasible.
                valid_flags[index] = self._is_valid(replacement)

        self.valid_fraction_history.append(sum(valid_flags) / total)
        return off

    def _do(self, problem, pop, n_offsprings, random_state=None, **kwargs):  # noqa: ANN001, ANN003
        # Required by InfillCriterion's abstract interface, but this class
        # overrides do() directly rather than relying on the base
        # do()->_do() flow (it needs to inspect and retry the WHOLE batch
        # produced by the wrapped mating, not build offspring one call at
        # a time), so this is never actually invoked.
        return self.mating._do(problem, pop, n_offsprings, random_state=random_state, **kwargs)

    def _is_valid(self, sample) -> bool:  # noqa: ANN001
        if not isinstance(sample, dict):
            return True
        try:
            genome = flatten_mixed_genome(sample, self.topology)
            design = decode(genome, self.topology, self.topology.cables)
            result = check_feasibility(
                design,
                aperture_radius_mm=self.topology.aperture_radius_mm,
                min_gap_mm=self.feasibility.min_gap_mm,
                max_angle_deg=self.feasibility.max_angle_deg,
                min_layer_clearance_mm=self.feasibility.min_layer_clearance_mm,
                min_pole_gap_mm=self.feasibility.min_pole_gap_mm,
                min_inter_block_gap_mm=self.feasibility.min_inter_block_gap_mm,
                enforce_layer_nesting=self.feasibility.enforce_layer_nesting,
            )
            return result.is_feasible
        except (KeyError, ValueError, ZeroDivisionError):
            return False

    def _regenerate(self, problem, pop, random_state, **kwargs):  # noqa: ANN001, ANN003
        for _ in range(self.max_regeneration_attempts):
            retry = self.mating.do(problem, pop, 1, random_state=random_state, **kwargs)
            if len(retry) and self._is_valid(retry[0].get("X")):
                return retry[0].get("X")
        fallback = self.sampling.do(problem, 1, random_state=random_state)
        if len(fallback):
            return fallback[0].get("X")
        return None


def _mixed_variable_nsga2(
    topology: Topology,
    feasibility: FeasibilitySettings,
    pop_size: int,
    targets: OptimizationTargets | None = None,
    topology_survival: TopologySurvivalConfig | None = None,
    adaptive_offspring: bool = False,
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
    survival = TopologyAwareRankAndCrowding(topology_survival or TopologySurvivalConfig())
    sampling = ConstructiveMixedVariableSampling(topology, feasibility)
    mating: InfillCriterion = MixedVariableMating(repair=repair, eliminate_duplicates=duplicate_elimination)
    if adaptive_offspring:
        mating = AdaptiveOffspringMating(topology, feasibility, mating, sampling)
    return NSGA2(
        pop_size=pop_size,
        sampling=sampling,
        mating=mating,
        eliminate_duplicates=duplicate_elimination,
        survival=survival,
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
