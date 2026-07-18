"""Thin NSGA-II campaign runner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real as RealNumber
from typing import Callable

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.duplicate import NoDuplicateElimination
from pymoo.core.infill import InfillCriterion
from pymoo.core.mixed import MixedVariableMating
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.core.variable import Binary, Choice, Integer, Real
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.crossover.ux import UX
from pymoo.operators.mutation.bitflip import BFM
from pymoo.operators.mutation.pm import PM
from pymoo.operators.mutation.rm import ChoiceRandomMutation
from pymoo.operators.repair.rounding import RoundingRepair
from pymoo.optimize import minimize

from dot.geometry import DipoleDesign
from dot.geometry.constraints import (
    check_extended_lower_edge_nesting,
    check_feasibility,
    check_layer_nesting,
)

from .genome import GenomeVariable, Topology, decode, flatten_mixed_genome, genome_variables
from .objectives import (
    BlockMarginRecord,
    LayerMarginRecord,
    harmonic_table,
    load_line_margin_by_block_detail,
    load_line_margin_detail,
)
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
    harmonics: tuple[tuple[int, float, float], ...] = ()
    margin_by_layer: tuple[LayerMarginRecord, ...] = ()
    margin_by_block: tuple[BlockMarginRecord, ...] = ()
    operating_current_a: float | None = None
    certified: bool = False
    harmonic_targets: tuple[tuple[int, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ParetoResult:
    """Feasible non-dominated candidates from an optimization run."""

    candidates: tuple[ParetoCandidate, ...]
    excluded_margin_layers: tuple[MarginEvaluationExclusion, ...] = ()
    near_feasible: tuple["NearFeasibleCandidate", ...] = ()
    # Rank-zero archive at search fidelity, before immutable acceptance
    # certification.  Keeping this full front is essential when no point is
    # inside the target box: the ten-item near-feasible diagnostic list is
    # intentionally too small to represent the engineering trade-off.
    search_front: tuple[ParetoCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class NearFeasibleCandidate:
    """A final-population design retained for diagnostics, never as a pass."""

    genome: np.ndarray
    design: DipoleDesign
    search_objectives: tuple[float, float]
    normalized_violations: tuple[tuple[str, float], ...]
    harmonic_targets: tuple[tuple[int, float], ...] = ()

    @property
    def max_violation(self) -> float:
        return max((value for _, value in self.normalized_violations), default=0.0)


class CampaignCancelled(RuntimeError):
    """Raised after a generation when a cooperative stop is requested."""


def merge_pareto_results(
    results: list[ParetoResult],
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
) -> ParetoResult:
    """Merge independent seeds into one re-certified nondominated archive."""

    candidates = [candidate for result in results for candidate in result.candidates]
    exclusions = tuple(
        dict.fromkeys(
            exclusion for result in results for exclusion in result.excluded_margin_layers
        )
    )
    near_feasible = sorted(
        (item for result in results for item in result.near_feasible),
        key=lambda item: (
            item.max_violation,
            sum(value for _, value in item.normalized_violations),
        ),
    )[:10]
    search_front = _search_nondominated(
        [candidate for result in results for candidate in result.search_front]
    )
    return ParetoResult(
        candidates=_certified_nondominated(candidates, topology, targets, feasibility),
        excluded_margin_layers=exclusions,
        near_feasible=tuple(near_feasible),
        search_front=search_front,
    )


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
        physics_seed_count = max(1, int(math.ceil(0.6 * n_samples)))
        for sample_index in range(n_samples):
            physics_seed = sample_index < physics_seed_count
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

            # Optional block slots represent an ordered winding, so activate
            # a contiguous prefix.  For most initial samples, also seed the
            # free cable-frame angle near the local radial direction used by
            # classical cos-theta/sector constructions.  This is generic
            # physics knowledge, not a reference-magnet block layout; the
            # remaining population stays fully random for diversity.
            for layer_index, layer in enumerate(self.topology.layers):
                active_count = int(rng.integers(layer.min_blocks, layer.n_blocks + 1))
                for block_index in range(1, layer.n_blocks):
                    sample[f"layer_{layer_index}_block_{block_index}_active"] = (
                        block_index < active_count
                    )

            for layer_index, phi_variables in by_layer.items():
                active_phi_variables = [
                    item for item in phi_variables if _block_is_active(sample, layer_index, item[1])
                ]
                if not active_phi_variables:
                    continue
                layer = self.topology.layers[layer_index]
                radius_name = f"layer_{layer_index}_inner_radius_mm"
                radius = float(sample[radius_name])
                cable = self.topology.cables[layer.cable_id]
                cable_width = cable.insulated_width_inner_mm
                if physics_seed:
                    active_count = len(active_phi_variables)
                    pitch_deg = max(
                        1.0e-9,
                        math.degrees(math.asin(min(1.0, cable_width / max(radius, cable_width)))),
                    )
                    # A uniform 60-degree sector is the classical analytic
                    # starting point for cancelling the first allowed dipole
                    # harmonic. Sample a neighborhood, then distribute its
                    # conductor monotonically across the requested number of
                    # blocks; no reference-magnet angles or turns are used.
                    sector_span_deg = float(rng.uniform(48.0, 62.0))
                    target_total_turns = max(
                        active_count,
                        int(round(sector_span_deg / pitch_deg)),
                    )
                    _assign_sector_turns(
                        sample,
                        layer_index,
                        active_phi_variables,
                        layer.n_turns_bounds,
                        target_total_turns,
                    )
                turn_counts = _sample_turn_counts(sample, layer_index, active_phi_variables)
                if physics_seed:
                    phis = _sector_seed_phi_values(
                        active_phi_variables,
                        turn_counts,
                        radius,
                        cable_width,
                        _repair_target_gap_mm(self.feasibility, layer_index),
                        self.feasibility.min_gap_mm,
                        _midplane_anchor_offset_mm(cable),
                        rng,
                    )
                else:
                    phis = _ordered_phi_values(
                        active_phi_variables,
                        turn_counts,
                        radius,
                        cable_width,
                        _repair_target_gap_mm(self.feasibility, layer_index),
                        self.feasibility.min_gap_mm,
                        _midplane_anchor_offset_mm(cable),
                        rng,
                    )
                for name, phi in phis.items():
                    sample[name] = phi
                if physics_seed:
                    for name, block_index, _bounds in active_phi_variables:
                        if block_index == 0:
                            continue
                        alpha_name = name.replace("_phi_deg", "_alpha_deg")
                        alpha_variable = next(
                            variable for variable in self._variables if variable.name == alpha_name
                        )
                        aligned = phis[name] + float(rng.normal(0.0, 5.0))
                        sample[alpha_name] = float(
                            min(max(aligned, alpha_variable.bounds[0]), alpha_variable.bounds[1])
                        )

            samples.append(sample)
        values = np.asarray(samples, dtype=object)
        if isinstance(problem, DipoleOptimizationProblem):
            # Initial genomes must pass through exactly the same structural
            # projection as offspring.  Applying only GroundTruthRepair here
            # left random layer radii and too-few active blocks untouched.
            return CampaignRepair(
                self.topology,
                self.feasibility,
                problem.targets,
            )._do(problem, values)

        # Direct unit use has no target object, so apply every target-free
        # stage and retain the historical sampling API.
        values = ContiguousActiveBlocksRepair(self.topology)._do(problem, values)
        values = MinActiveBlocksRepair(self.topology)._do(problem, values)
        values = RadialCompactionRepair(self.topology, self.feasibility)._do(problem, values)
        values = PhiOrderingRepair(self.topology, self.feasibility)._do(problem, values)
        values = LayerNestingRepair(self.topology, self.feasibility)._do(problem, values)
        return GroundTruthRepair(self.topology, self.feasibility)._do(problem, values)


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
            if not phi_variables:
                continue
            if len(phi_variables) == 1:
                # Only the midplane block (block 0) is active in this layer.
                # Pin its anchor to the requested physical clearance rather
                # than phi=0deg, which puts the anchored cable corner on the
                # symmetry plane.
                variable = phi_variables[0]
                radius = float(sample[f"layer_{layer_index}_inner_radius_mm"])
                cable = self.topology.cables[layer.cable_id]
                target = _midplane_anchor_phi_deg(
                    radius,
                    self.feasibility.min_gap_mm,
                    _midplane_anchor_offset_mm(cable),
                )
                sample[variable.name] = float(
                    min(max(target, variable.bounds[0]), variable.bounds[1])
                )
                continue

            radius = float(sample[f"layer_{layer_index}_inner_radius_mm"])
            cable_width = self.topology.cables[layer.cable_id].insulated_width_inner_mm
            # Block 0 is the fixed midplane block at the smallest phi;
            # increasing block index moves poleward toward larger phi.
            ordered = sorted(phi_variables, key=lambda item: item.block_index)
            # Turns stack from a block's anchor toward increasing phi (the
            # pole).  Consequently the transition to a poleward block is
            # governed by the footprint of the *midward* block.  Keep one
            # footprint per block and select the correct one below.
            footprints = [
                _minimum_phi_gap_deg(
                    radius,
                    cable_width,
                    _repair_target_gap_mm(self.feasibility, layer_index),
                    n_turns=_sample_n_turns(sample, layer_index, variable.block_index),
                )
                for variable in ordered
            ]
            # Anchor block 0 at its midplane-clearance limit, then make the
            # smallest poleward projection needed to restore clearance.
            # Retaining already-feasible proposed phi values preserves a
            # useful optimization degree of freedom; rebuilding an evenly
            # packed layer here previously collapsed that diversity.
            midplane_target = _midplane_anchor_phi_deg(
                radius,
                self.feasibility.min_gap_mm,
                _midplane_anchor_offset_mm(self.topology.cables[layer.cable_id]),
            )
            position = float(min(max(midplane_target, ordered[0].bounds[0]), ordered[0].bounds[1]))
            sample[ordered[0].name] = position
            for index in range(1, len(ordered)):
                lower, upper = ordered[index].bounds
                min_allowed = position + footprints[index - 1]
                proposed = float(sample[ordered[index].name])
                position = float(min(upper, max(proposed, lower, min_allowed)))
                sample[ordered[index].name] = position


class ContiguousActiveBlocksRepair(Repair):
    """Represent each layer topology by a contiguous active block prefix."""

    def __init__(self, topology: Topology) -> None:
        super().__init__()
        self.topology = topology

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        for sample in x:
            if not isinstance(sample, dict):
                continue
            for layer_index, layer in enumerate(self.topology.layers):
                active_count = max(
                    layer.min_blocks,
                    sum(
                        1
                        for block_index in range(layer.n_blocks)
                        if _block_is_active(sample, layer_index, block_index)
                    ),
                )
                active_count = min(active_count, layer.n_blocks)
                for block_index in range(1, layer.n_blocks):
                    sample[f"layer_{layer_index}_block_{block_index}_active"] = (
                        block_index < active_count
                    )
        return x


class LayerNestingRepair(Repair):
    """Shift an outer layer's blocks toward the midplane to restore nesting.

    Task 0037/0043: :func:`check_layer_nesting` (C10) was implemented but
    left gated off (``enforce_layer_nesting=False``) because nothing
    repaired a violation -- enabling it collapsed the whole population.
    Mirrors dipole_designer's own C10 repair: bisection-search a single
    scalar phi shift, applied to every active non-midplane block in the
    violating outer layer, that eliminates the violation. The midplane
    block remains fixed at its physical symmetry-plane clearance.
    A uniform shift of the remaining blocks preserves their mutual ordering
    ``PhiOrderingRepair`` already established -- this is why it must run
    strictly after that repair. Applying the shift moves blocks toward the
    midplane (decreasing phi, away from the pole) because that is the
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

        movable = [variable for variable in phi_variables if variable.block_index != 0]
        if not movable:
            return
        radius = float(sample[f"layer_{layer_index}_inner_radius_mm"])
        block_0 = next(
            (variable for variable in phi_variables if variable.block_index == 0),
            None,
        )
        block_1 = min(movable, key=lambda variable: variable.block_index)
        cable_width = self.topology.cables[
            self.topology.layers[layer_index].cable_id
        ].insulated_width_inner_mm
        turns_name = f"layer_{layer_index}_block_0_n_turns"
        turns_variable = next(
            (variable for variable in self._variables if variable.name == turns_name),
            None,
        )

        while True:
            max_shifts = [float(sample[variable.name]) - variable.bounds[0] for variable in movable]
            if block_0 is not None:
                required = _minimum_phi_gap_deg(
                    radius,
                    cable_width,
                    _repair_target_gap_mm(self.feasibility, layer_index),
                    n_turns=_sample_n_turns(sample, layer_index, 0),
                )
                max_shifts.append(
                    float(sample[block_1.name]) - required - float(sample[block_0.name])
                )
            max_shift = min(cap, *max_shifts)
            if max_shift > 0.0 and not self._layer_has_nesting_violation(
                sample, layer_index, shift=max_shift
            ):
                self._apply_shift(
                    sample,
                    movable,
                    self._bisect_minimum_shift(sample, layer_index, movable, max_shift),
                )
                return

            # A large midplane block can consume all angular room available
            # to move poleward blocks into a nestable position. Reduce it one
            # turn at a time only when angular room (not the configured cap)
            # is the limiting factor, then retry the exact nesting check.
            if max_shift >= cap - 1.0e-12 or turns_variable is None:
                return
            current_turns = int(round(float(sample[turns_name])))
            lower_turns = int(round(turns_variable.bounds[0]))
            if current_turns <= lower_turns:
                return
            sample[turns_name] = current_turns - 1

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
                    and variable.block_index != 0
                    and _block_is_active(sample, layer_index, variable.block_index)
                ):
                    probe[variable.name] = float(sample[variable.name]) - shift
        genome = flatten_mixed_genome(probe, self.topology)
        design = decode(genome, self.topology, self.topology.cables)
        return any(
            violation.layer_index == layer_index
            for violation in (
                *check_layer_nesting(design),
                *check_extended_lower_edge_nesting(design),
            )
        )

    @staticmethod
    def _apply_shift(
        sample: dict[str, float | int], phi_variables: list[GenomeVariable], shift: float
    ) -> None:
        if shift <= 0.0:
            return
        for variable in phi_variables:
            sample[variable.name] = float(sample[variable.name]) - shift


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
                variable for layer_variables in by_layer.values() for variable in layer_variables
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
        surplus = (
            sum(int(round(float(sample[name]))) for name, _block_index, _lower in turn_variables)
            - budget
        )
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
    because genome_bounds() places it nearest the midplane (phi=0deg).
    Blocks 1..n-1 have a free alpha gene, but ordinary crossover/mutation
    treats it as independent of phi -- after mating, a block's phi can be
    repaired to a very different (more pole-ward) value than the alpha
    gene was tuned for, leaving alpha badly mismatched and producing
    self-overlapping turns that no other repair catches (phi-ordering and
    turn-budget repair don't touch alpha_deg at all).

    A turn's axes rotate with alpha only (see primitives.py's
    absolute-global-frame alpha convention); they align with the block's
    true local radial direction (cos(phi), sin(phi)) when alpha = phi.
    Clamping into [target - 15, target] (intersected with the block's own
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
            phi = float(sample.get(phi_name, 0.0))
            target = phi
            lower, upper = variable.bounds
            window_lower = max(lower, target - self._WINDOW_ABOVE_TARGET_DEG)
            window_upper = min(upper, target)
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
            result = self._feasibility_result(sample)
            if result.is_feasible:
                return
            if self._repair_pole_boundary(sample, result):
                continue
            if self._repair_aperture_boundary(sample, result):
                continue
            if not self._shrink_worst_block(sample, result):
                return

    def _feasibility_result(self, sample: dict[str, float | int]):
        genome = flatten_mixed_genome(sample, self.topology)
        unit_design = decode(genome, self.topology, self.topology.cables)
        return check_feasibility(
            unit_design,
            aperture_radius_mm=self.topology.aperture_radius_mm,
            min_gap_mm=self.feasibility.min_gap_mm,
            max_angle_deg=self.feasibility.max_angle_deg,
            min_layer_clearance_mm=self.feasibility.min_layer_clearance_mm,
            min_pole_gap_mm=self.feasibility.min_pole_gap_mm,
            min_pole_turn_radius_mm=self.feasibility.min_pole_turn_radius_mm,
            min_inter_block_gap_mm=self.feasibility.min_inter_block_gap_mm,
            enforce_layer_nesting=self.feasibility.enforce_layer_nesting,
            geometry_tolerance_mm=self.feasibility.geometry_tolerance_mm,
        )

    def _repair_pole_boundary(self, sample: dict[str, float | int], result) -> bool:  # noqa: ANN001
        """Move a pole-boundary offender toward the midplane before deleting turns."""

        offenders = [
            violation
            for violation in result.violations
            if violation.constraint_name in {"pole_angle_limit", "first_layer_pole_turn_radius"}
            and violation.layer_index is not None
            and violation.block_index is not None
        ]
        offenders.sort(key=lambda violation: violation.severity, reverse=True)
        for violation in offenders:
            genome_block = self._genome_block_index(
                sample, violation.layer_index, violation.block_index
            )
            if genome_block is None:
                continue
            phi_name = f"layer_{violation.layer_index}_block_{genome_block}_phi_deg"
            variable = next((item for item in self._variables if item.name == phi_name), None)
            if variable is None:
                continue
            current = float(sample[phi_name])
            lower = variable.bounds[0]
            if genome_block == 0:
                radius = float(sample[f"layer_{violation.layer_index}_inner_radius_mm"])
                lower = max(
                    lower,
                    _midplane_anchor_phi_deg(
                        radius,
                        self.feasibility.min_gap_mm,
                        _midplane_anchor_offset_mm(
                            self.topology.cables[
                                self.topology.layers[violation.layer_index].cable_id
                            ]
                        ),
                    ),
                )
            else:
                midward_blocks = [
                    block_index
                    for block_index in range(genome_block - 1, -1, -1)
                    if _block_is_active(sample, violation.layer_index, block_index)
                ]
                if midward_blocks:
                    midward = midward_blocks[0]
                    layer = self.topology.layers[violation.layer_index]
                    radius = float(sample[f"layer_{violation.layer_index}_inner_radius_mm"])
                    cable_width = self.topology.cables[layer.cable_id].insulated_width_inner_mm
                    required = _minimum_phi_gap_deg(
                        radius,
                        cable_width,
                        _repair_target_gap_mm(
                            self.feasibility,
                            violation.layer_index,
                        ),
                        n_turns=_sample_n_turns(sample, violation.layer_index, midward),
                    )
                    lower = max(
                        lower,
                        float(sample[f"layer_{violation.layer_index}_block_{midward}_phi_deg"])
                        + required,
                    )
            repaired = max(lower, current - violation.severity - 0.1)
            if repaired < current - 1.0e-12:
                sample[phi_name] = repaired
                return True
        return False

    def _repair_aperture_boundary(self, sample: dict[str, float | int], result) -> bool:  # noqa: ANN001
        """Rotate a free block out of a small aperture intrusion before removing cable.

        A tilted block can put one inner corner just inside the circular
        aperture even though its mandrel radius is correct. Deleting turns is
        a particularly harmful repair here: it systematically removes the
        conductor needed for load-line margin. Probe both alpha directions
        and retain a bounded step only when the complete geometry improves.
        The user-fixed midplane block has no free alpha gene and is therefore
        deliberately left to the existing conservative fallback.
        """

        offenders = [
            violation
            for violation in result.violations
            if violation.constraint_name == "aperture_clearance"
            and violation.layer_index is not None
            and violation.block_index is not None
        ]
        if not offenders:
            return False

        baseline_score = self._geometry_repair_score(result)
        best: tuple[tuple[int, float, float], str, float] | None = None
        for violation in offenders:
            block_index = self._genome_block_index(
                sample,
                violation.layer_index,
                violation.block_index,
            )
            if block_index <= 0:
                continue
            alpha_name = f"layer_{violation.layer_index}_block_{block_index}_alpha_deg"
            variable = next(
                (item for item in self._variables if item.name == alpha_name),
                None,
            )
            if variable is None:
                continue
            current = float(sample[alpha_name])
            for direction in (-1.0, 1.0):
                proposed = min(
                    max(current + 0.5 * direction, variable.bounds[0]),
                    variable.bounds[1],
                )
                if math.isclose(proposed, current, abs_tol=1.0e-12):
                    continue
                probe = dict(sample)
                probe[alpha_name] = proposed
                score = self._geometry_repair_score(self._feasibility_result(probe))
                if score >= baseline_score:
                    continue
                candidate = (score, alpha_name, proposed)
                if best is None or candidate[0] < best[0]:
                    best = candidate

        if best is None:
            return False
        _, alpha_name, proposed = best
        sample[alpha_name] = proposed
        return True

    @staticmethod
    def _geometry_repair_score(result) -> tuple[int, float, float]:  # noqa: ANN001
        if result.is_feasible:
            return (0, 0.0, 0.0)
        severities = tuple(float(violation.severity) for violation in result.violations)
        return (len(severities), max(severities), sum(severities))

    def _shrink_worst_block(self, sample: dict[str, float | int], result) -> bool:  # noqa: ANN001
        turn_limits: dict[tuple[int, int], int] = {}
        for violation in result.violations:
            indexed_sides = (
                (violation.layer_index, violation.block_index, violation.turn_index),
                (
                    violation.other_layer_index,
                    violation.other_block_index,
                    violation.other_turn_index,
                ),
            )
            for layer_index, decode_block_index, turn_index in indexed_sides:
                if layer_index is None or decode_block_index is None or turn_index is None:
                    continue
                genome_block_index = self._genome_block_index(
                    sample, layer_index, decode_block_index
                )
                key = (layer_index, genome_block_index)
                turn_limits[key] = min(turn_limits.get(key, turn_index), turn_index)

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
        non_midplane_candidates = [
            (layer_index, block_index)
            for layer_index, block_index in violated
            if block_index is not None and block_index != 0
        ]
        midplane_candidates = [
            (layer_index, block_index) for layer_index, block_index in violated if block_index == 0
        ]
        candidates = non_midplane_candidates + midplane_candidates
        if not candidates:
            return False

        # Rank candidates by turn count (most turn-heavy first), same
        # priority as before, but now try each in turn instead of
        # committing to a single "worst" one -- deactivating the worst
        # offender can be blocked by its layer's min_blocks floor
        # (task 0054), in which case the next-worst candidate should still
        # get a chance rather than leaving the sample unrepaired outright.
        ranked: list[tuple[int, int, str, int, int]] = []
        for layer_index, block_index in candidates:
            turns_name = f"layer_{layer_index}_block_{block_index}_n_turns"
            if turns_name not in sample:
                continue
            current = int(round(float(sample[turns_name])))
            variable = next(v for v in self._variables if v.name == turns_name)
            lower = int(round(variable.bounds[0]))
            limit = turn_limits.get((layer_index, block_index), current - 1)
            ranked.append((current, lower, turns_name, block_index, limit))
        ranked.sort(key=lambda item: (item[3] == 0, -item[0]))

        for current, lower, turns_name, block_index, turn_limit in ranked:
            if current > lower:
                # If the exact polygon check identifies offending turn t,
                # removing turn t and all later turns is equivalent to
                # setting n_turns=t. Jump there directly instead of repeating
                # the full O(N²) collision suite once per deleted turn.
                sample[turns_name] = max(lower, min(current - 1, turn_limit))
                return True
            if block_index == 0:
                continue
            active_name = turns_name.replace("_n_turns", "_active")
            # A missing key means "active" (see _block_is_active's own
            # default) -- deactivation must still be possible by *setting*
            # the key, not skipped just because it doesn't exist yet.
            if not bool(sample.get(active_name, True)):
                continue
            layer_index = int(turns_name.split("_")[1])
            if self._would_violate_min_blocks(sample, layer_index):
                continue
            sample[active_name] = False
            return True
        return False

    def _would_violate_min_blocks(self, sample: dict[str, float | int], layer_index: int) -> bool:
        layer = self.topology.layers[layer_index]
        if layer.min_blocks <= 1:
            return False
        active_count = sum(
            1
            for block_index in range(layer.n_blocks)
            if _block_is_active(sample, layer_index, block_index)
        )
        return active_count - 1 < layer.min_blocks

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


class RadialCompactionRepair(Repair):
    """Pull every layer's inner radius down to the tightest value the
    PREVIOUS layer's actual (post-repair) outer edge allows.

    ``inner_radius_mm`` is a free continuous gene, sampled/mutated anywhere
    within ``inner_radius_bounds_mm`` -- and nothing else in the repair
    chain or objective rewards sitting near the bottom of that range. A
    campaign's own admission/feasibility checks only enforce
    ``check_inter_layer_spacing``/``check_midplane_clearance`` as MINIMUMS
    (``gap >= min_layer_clearance_mm`` / ``gap >= min_gap_mm``), so a
    candidate with a 13mm radial gap is exactly as "feasible" as one with
    0.51mm: the search has no pressure to pack tightly like the real
    reference design does, and was confirmed (by hand-inspecting a
    converged campaign's best candidate) to leave large, non-representative
    slack. This repair makes tight packing structural instead of aspirational
    -- applied to every sample, every generation, not a one-off polish on a
    single saved candidate. Must run before ``PhiOrderingRepair`` in
    ``CampaignRepair``'s chain: that repair reads each layer's
    ``inner_radius_mm`` straight from the sample to size its phi gaps, and
    needs to see the tightened radius, not the pre-repair one.
    """

    def __init__(self, topology: Topology, feasibility: FeasibilitySettings) -> None:
        super().__init__()
        self.topology = topology
        self.feasibility = feasibility

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        for sample in x:
            if not isinstance(sample, dict):
                continue
            self._repair_sample(sample)
        return x

    def _repair_sample(self, sample: dict[str, float | int]) -> None:
        previous_outer_edge: float | None = None
        for layer_index, layer in enumerate(self.topology.layers):
            key = f"layer_{layer_index}_inner_radius_mm"
            lower, upper = layer.inner_radius_bounds_mm
            target = (
                lower
                if previous_outer_edge is None
                else previous_outer_edge + self.feasibility.min_layer_clearance_mm
            )
            radius = min(max(target, lower), upper)
            sample[key] = radius
            cable = self.topology.cables[layer.cable_id]
            previous_outer_edge = radius + cable.insulated_height_mm


class MinActiveBlocksRepair(Repair):
    """Reactivate blocks so every layer meets its ``min_blocks`` floor.

    ``ActiveAwareGrowthSampling``-style constructive sampling only sets
    this floor at generation 0; without repairing it too, mutation's
    Binary ``active`` gene (bit-flip, can turn a block off) erodes it over
    generations, and a campaign converges toward whatever sparse topology
    is easiest to make feasible -- dd's own topology-collapse review found
    exactly this failure mode and recommends a per-layer minimum active
    block count (">=2 in L1/L2 so wedge angles exist to cancel
    harmonics"). This repair is the mechanism that makes ``min_blocks``
    hold for the whole search, not just the initial population.
    """

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
        for layer_index, layer in enumerate(self.topology.layers):
            if layer.min_blocks <= 1:
                continue
            active = [b for b in range(layer.n_blocks) if _block_is_active(sample, layer_index, b)]
            if len(active) >= layer.min_blocks:
                continue
            inactive = [b for b in range(layer.n_blocks) if b not in active]
            for block_index in inactive:
                if len(active) >= layer.min_blocks:
                    break
                sample[f"layer_{layer_index}_block_{block_index}_active"] = True
                turns_name = f"layer_{layer_index}_block_{block_index}_n_turns"
                if int(round(float(sample.get(turns_name, 0)))) < layer.n_turns_bounds[0]:
                    sample[turns_name] = layer.n_turns_bounds[0]
                active.append(block_index)


class CampaignRepair(Repair):
    """Apply all mixed-variable structural repairs in a fixed sequence.

    Min-active-blocks repair runs first: it can activate blocks, and every
    later repair (turn-budget, phi-ordering, ...) must see the final
    active-block set, not one that gains members after they already ran.
    Radial-compaction repair runs next, before anything phi-related: it
    tightens every layer's ``inner_radius_mm`` toward the previous layer's
    actual outer edge, and ``PhiOrderingRepair`` reads that same
    ``inner_radius_mm`` straight from the sample to size its turn-aware
    phi gaps, so it must see the tightened value, not the pre-repair one.
    Turn-budget repair runs next so that phi-ordering repair computes its
    turn-count-aware gaps from each block's final, budget-compliant
    ``n_turns`` rather than a pre-reduction value. Reversing that pair is
    still geometrically safe (phi gaps computed from an inflated n_turns
    are only overly conservative, never insufficient, since
    TurnBudgetRepair only ever reduces n_turns), but running turn-budget
    repair first avoids that unnecessary conservatism. Layer-nesting
    repair runs next: it applies a pure scalar-shift translation to an
    outer layer's blocks, which preserves the ordering/gaps phi-ordering
    repair just established, so it must run after that repair, not before
    it (translating unordered blocks could still leave them unordered).
    Alpha is deliberately not clamped to a phi-derived heuristic: published
    ROXIE layouts contain valid blocks outside a narrow alignment window.
    GroundTruthRepair runs last: it verifies against
    real check_feasibility and greedily shrinks anything the formula-based
    repairs above still leave infeasible.
    """

    def __init__(
        self, topology: Topology, feasibility: FeasibilitySettings, targets: OptimizationTargets
    ) -> None:
        super().__init__()
        self._contiguous_blocks = ContiguousActiveBlocksRepair(topology)
        self._min_active_blocks = MinActiveBlocksRepair(topology)
        self._radial_compaction = RadialCompactionRepair(topology, feasibility)
        self._phi_ordering = PhiOrderingRepair(topology, feasibility)
        self._layer_nesting = LayerNestingRepair(topology, feasibility)
        self._turn_budget = TurnBudgetRepair(topology, targets)
        self._ground_truth = GroundTruthRepair(topology, feasibility)

    def _do(self, problem, x, **kwargs):  # noqa: ANN001, ANN003
        x = self._contiguous_blocks._do(problem, x, **kwargs)
        x = self._min_active_blocks._do(problem, x, **kwargs)
        x = self._radial_compaction._do(problem, x, **kwargs)
        x = self._turn_budget._do(problem, x, **kwargs)
        x = self._phi_ordering._do(problem, x, **kwargs)
        # Ground-truth shrinking can change the inner layer's pole-side edge
        # and thereby create a new nesting violation after nesting was first
        # projected.  Iterate the two coupled repairs to a small fixed point.
        for _ in range(3):
            x = self._layer_nesting._do(problem, x, **kwargs)
            x = self._ground_truth._do(problem, x, **kwargs)
        return x


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


def best_generation_candidate(
    topology: Topology,
    pop,
    targets: OptimizationTargets | None = None,
) -> tuple[DipoleDesign, tuple[float, float], float] | None:  # noqa: ANN001
    """Decode the population's best-so-far individual for live GUI reporting.

    Among geometrically/admission-feasible individuals, prefer one that is
    closest to the declared harmonic/margin target box and then balance low
    harmonic against high margin.  This prevents the live GUI from calling a
    zero-margin, low-harmonic extreme the generation's "best" design.  If no
    individual is feasible yet, fall back to the smallest max constraint
    violation so the user still sees progress from generation 1 onward.
    """

    x = pop.get("X")
    f = pop.get("F")
    g = pop.get("G")
    if x is None or f is None or len(x) == 0:
        return None
    feasible_mask = np.all(g <= 0.0, axis=1) if g is not None else np.zeros(len(x), dtype=bool)
    if np.any(feasible_mask):
        candidate_indices = np.flatnonzero(feasible_mask)
        if targets is None:
            best_index = candidate_indices[np.argmin(f[candidate_indices, 0])]
        else:
            best_index = min(
                candidate_indices,
                key=lambda index: _generation_candidate_score(f[index], targets),
            )
    else:
        violation = np.max(g, axis=1) if g is not None else np.zeros(len(x))
        best_index = int(np.argmin(violation))
    genome = x[best_index]
    if isinstance(genome, dict):
        genome = flatten_mixed_genome(genome, topology)
    genome = np.asarray(genome, dtype=float)
    unit_design = decode(genome, topology, topology.cables)
    harmonic_units, neg_margin = float(f[best_index, 0]), float(f[best_index, 1])
    return unit_design, (harmonic_units, neg_margin), -neg_margin


def _generation_candidate_score(
    objectives: np.ndarray,
    targets: OptimizationTargets,
) -> tuple[float, float]:
    harmonic = float(objectives[0])
    margin = -float(objectives[1])
    harmonic_scale = targets.max_harmonic_units or max(abs(harmonic), 1.0)
    margin_scale = targets.min_margin_percent or max(abs(margin), 1.0)
    harmonic_ratio = harmonic / harmonic_scale
    margin_ratio = margin / margin_scale
    target_box_violation = max(0.0, harmonic_ratio - 1.0) + max(0.0, 1.0 - margin_ratio)
    balanced_tradeoff = harmonic_ratio + 1.0 / max(margin_ratio, 1.0e-12)
    return target_box_violation, balanced_tradeoff


def run_campaign(
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    pop_size: int = 8,
    n_gen: int = 3,
    seed: int | None = None,
    topology_survival: TopologySurvivalConfig | None = None,
    adaptive_offspring: bool = False,
    n_workers: int | None = None,
    on_generation: Callable[
        [int, int, DipoleDesign | None, float | None, float | None, int | None],
        None,
    ]
    | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ParetoResult:
    """Run a small fixed-topology NSGA-II campaign and return feasible candidates.

    ``on_generation``, if given, is called once per generation with
    ``(generation, total_generations, best_design_or_None, best_margin_percent_or_None,
    best_harmonic_units_or_None, topology_family_count_or_None)`` -- the live
    per-generation best-candidate view dd's GUI has and DOT's lacked (task
    0052), extended (task 0056) with the harmonic/diversity signal a live
    convergence chart needs.
    """

    problem = DipoleOptimizationProblem(
        topology, targets, feasibility, total_generations=n_gen, n_workers=n_workers
    )
    algorithm = _mixed_variable_nsga2(
        topology, feasibility, pop_size, targets, topology_survival, adaptive_offspring
    )

    def _advance_generation(algorithm) -> None:  # noqa: ANN001
        problem.set_generation(algorithm.n_gen)
        # Pareto-search harmonic/margin thresholds are absent from G, while
        # the current cap is a static hard constraint. Survivors' cached
        # physics therefore remain valid; re-evaluating the full population
        # here doubled the dominant load-line work for no numerical change.
        if not targets.pareto_search:
            refresh_population_admission(problem, algorithm.pop)
        if on_generation is not None:
            best = None
            margin_percent = None
            harmonic_units = None
            try:
                found = best_generation_candidate(topology, algorithm.pop, targets)
                if found is not None:
                    design, (raw_harmonic_units, _neg_margin), margin_percent = found
                    harmonic_units = (
                        raw_harmonic_units
                        if math.isfinite(raw_harmonic_units) and raw_harmonic_units < 1.0e11
                        else None
                    )
                    scaled = operating_point(design, targets.target_bore_field_t)
                    best = scaled.design
            except (KeyError, ValueError, ZeroDivisionError):
                best = None
                margin_percent = None
                harmonic_units = None
            families = algorithm.pop.get("topology_family")
            family_count = (
                len({f for f in families if f is not None}) if families is not None else None
            )
            on_generation(
                algorithm.n_gen, n_gen, best, margin_percent, harmonic_units, family_count
            )
        if should_stop is not None and should_stop():
            raise CampaignCancelled(f"campaign stopped after generation {algorithm.n_gen}")

    try:
        result = minimize(
            problem,
            algorithm,
            ("n_gen", n_gen),
            seed=seed,
            callback=_advance_generation,
            verbose=False,
        )
    finally:
        problem.close()

    # Do not trust result.X/result.G as final engineering truth: individuals
    # can have been born under an earlier admission plateau. Reconsider the
    # whole final population and certify it below against immutable targets.
    final_algorithm = getattr(result, "algorithm", None)
    final_population = getattr(final_algorithm, "pop", None)
    pop_x = final_population.get("X") if final_population is not None else None
    genomes = _result_genomes(pop_x, topology)
    pop_f = (
        np.atleast_2d(final_population.get("F"))
        if final_population is not None and final_population.get("F") is not None
        else np.full((len(genomes), 2), math.inf)
    )
    pop_g = (
        np.atleast_2d(final_population.get("G"))
        if final_population is not None and final_population.get("G") is not None
        else np.full((len(genomes), len(problem.constraint_names)), math.inf)
    )
    candidates: list[ParetoCandidate] = []
    near_feasible: list[NearFeasibleCandidate] = []
    for genome, objective, constraint in zip(genomes, pop_f, pop_g, strict=False):
        try:
            unit_design = decode(genome, topology, topology.cables)
            solved = operating_point(unit_design, targets.target_bore_field_t)
            normalized_violations = [
                (name, max(0.0, float(value)))
                for name, value in zip(problem.constraint_names, constraint, strict=True)
            ]
            if targets.pareto_search:
                if targets.max_harmonic_units is not None:
                    normalized_violations.append(
                        (
                            "harmonics",
                            max(
                                0.0,
                                (float(objective[0]) - targets.max_harmonic_units)
                                / max(1.0, abs(targets.max_harmonic_units)),
                            ),
                        )
                    )
                if targets.min_margin_percent is not None:
                    margin_percent = -float(objective[1])
                    normalized_violations.append(
                        (
                            "margin",
                            max(
                                0.0,
                                (targets.min_margin_percent - margin_percent)
                                / max(1.0, abs(targets.min_margin_percent)),
                            ),
                        )
                    )
            search_candidate = ParetoCandidate(
                genome=np.asarray(genome, dtype=float),
                design=solved.design,
                objectives=(float(objective[0]), float(objective[1])),
                harmonic_targets=targets.harmonic_targets,
            )
            # Harmonic and margin thresholds are performance objectives for
            # the final frontier, not prerequisites for appearing on it.
            # Geometry, current, and turn budgets remain hard constraints.
            hard_feasible = all(
                float(value) <= 0.0
                for name, value in zip(problem.constraint_names, constraint, strict=True)
                if name not in {"harmonics", "margin"}
            )
            if hard_feasible:
                candidates.append(search_candidate)
            near_feasible.append(
                NearFeasibleCandidate(
                    genome=np.asarray(genome, dtype=float),
                    design=solved.design,
                    search_objectives=(float(objective[0]), float(objective[1])),
                    normalized_violations=tuple(normalized_violations),
                    harmonic_targets=targets.harmonic_targets,
                )
            )
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    search_candidates = list(candidates)
    search_front = list(_search_nondominated(search_candidates))
    candidates = list(_certified_nondominated(search_candidates, topology, targets, feasibility))
    near_feasible.sort(
        key=lambda item: (
            item.max_violation,
            sum(value for _, value in item.normalized_violations),
        )
    )

    return ParetoResult(
        candidates=tuple(candidates),
        excluded_margin_layers=_margin_exclusions(targets),
        near_feasible=tuple(near_feasible[:10]),
        search_front=tuple(search_front),
    )


def _certified_nondominated(
    candidates: list[ParetoCandidate],
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
) -> tuple[ParetoCandidate, ...]:
    """Re-evaluate, deduplicate, and return feasible rank-zero candidates."""

    certified: list[ParetoCandidate] = []
    seen: set[tuple[object, ...]] = set()
    for candidate in candidates:
        checked = _certify_candidate(candidate, topology, targets, feasibility)
        if checked is None:
            continue
        key = _design_key(checked.design)
        if key in seen:
            continue
        seen.add(key)
        certified.append(checked)

    rank_zero: list[ParetoCandidate] = []
    for index, candidate in enumerate(certified):
        if any(
            _dominates(other.objectives, candidate.objectives)
            for other_index, other in enumerate(certified)
            if other_index != index
        ):
            continue
        rank_zero.append(candidate)
    rank_zero = _prefer_simpler_equivalents(rank_zero)
    rank_zero.sort(key=lambda item: (*item.objectives, *_design_complexity(item.design)))
    return tuple(rank_zero)


def _certify_candidate(
    candidate: ParetoCandidate,
    topology: Topology,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
) -> ParetoCandidate | None:
    design = candidate.design
    geometry = check_feasibility(
        design,
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
    if not geometry.is_feasible:
        return None
    total_turns = sum(block.n_turns for layer in design.layers for block in layer.blocks)
    if targets.max_total_turns is not None and total_turns > targets.max_total_turns:
        return None
    if targets.max_turns_per_layer is not None and any(
        sum(block.n_turns for block in layer.blocks) > targets.max_turns_per_layer
        for layer in design.layers
    ):
        return None
    try:
        solved = operating_point(design, targets.target_bore_field_t)
        harmonics = harmonic_table(
            solved.design,
            targets.r_ref_mm,
            targets.max_order,
            targets.certification_fidelity,
        )
        if targets.harmonic_orders:
            wanted = set(targets.harmonic_orders)
            target_by_order = dict(targets.harmonic_targets)
            field_quality = max(
                abs(b_n - target_by_order.get(order, 0.0))
                for order, b_n, _ in harmonics
                if order in wanted
            )
        else:
            field_quality = max(
                max(abs(b_n), abs(a_n)) for order, b_n, a_n in harmonics if order >= 2
            )
        operating_current_a = abs(solved.operating_current_a)
        if targets.max_harmonic_units is not None and field_quality > targets.max_harmonic_units:
            return None
        if targets.max_current_a is not None and operating_current_a > targets.max_current_a:
            return None
        margins = load_line_margin_detail(
            solved.design,
            targets.cadata_by_layer,
            targets.temperature_k,
            fidelity=targets.certification_fidelity,
        )
        margin_percent = min(item.margin_percent for item in margins)
        if targets.min_margin_percent is not None and margin_percent < targets.min_margin_percent:
            return None
        block_margins = load_line_margin_by_block_detail(
            solved.design,
            targets.cadata_by_layer,
            targets.temperature_k,
            fidelity=targets.certification_fidelity,
        )
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    return ParetoCandidate(
        genome=candidate.genome,
        design=solved.design,
        objectives=(field_quality, -margin_percent),
        harmonics=harmonics,
        margin_by_layer=margins,
        margin_by_block=block_margins,
        operating_current_a=operating_current_a,
        certified=True,
        harmonic_targets=targets.harmonic_targets,
    )


def _design_key(design: DipoleDesign) -> tuple[object, ...]:
    return tuple(
        value
        for layer in design.layers
        for value in (
            round(layer.inner_radius_mm, 8),
            *(
                item
                for block in layer.blocks
                for item in (
                    round(block.phi_deg, 8),
                    round(block.alpha_deg, 8),
                    block.n_turns,
                )
            ),
        )
    )


def _design_complexity(design: DipoleDesign) -> tuple[int, int]:
    """Secondary preference: fewer turns first, then fewer active blocks."""

    return (
        sum(block.n_turns for layer in design.layers for block in layer.blocks),
        sum(len(layer.blocks) for layer in design.layers),
    )


def _objectives_equivalent(
    left: tuple[float, float],
    right: tuple[float, float],
) -> bool:
    """Treat only numerical-noise-level electromagnetic differences as identical."""

    return all(
        math.isclose(a, b, rel_tol=1.0e-12, abs_tol=1.0e-9)
        for a, b in zip(left, right, strict=True)
    )


def _prefer_simpler_equivalents(
    candidates: list[ParetoCandidate],
) -> list[ParetoCandidate]:
    """Keep the least-complex representative of each EM-equivalent group."""

    preferred: list[ParetoCandidate] = []
    for candidate in sorted(candidates, key=lambda item: _design_complexity(item.design)):
        if any(
            _objectives_equivalent(candidate.objectives, existing.objectives)
            for existing in preferred
        ):
            continue
        preferred.append(candidate)
    return preferred


def _dominates(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return all(a <= b for a, b in zip(left, right, strict=True)) and any(
        a < b for a, b in zip(left, right, strict=True)
    )


def _search_nondominated(
    candidates: list[ParetoCandidate],
) -> tuple[ParetoCandidate, ...]:
    """Deduplicate and retain the finite rank-zero search-fidelity archive."""

    unique: list[ParetoCandidate] = []
    seen: set[tuple[object, ...]] = set()
    for candidate in candidates:
        if not all(math.isfinite(value) and abs(value) < 1.0e11 for value in candidate.objectives):
            continue
        key = _design_key(candidate.design)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    rank_zero = [
        candidate
        for index, candidate in enumerate(unique)
        if not any(
            _dominates(other.objectives, candidate.objectives)
            for other_index, other in enumerate(unique)
            if other_index != index
        )
    ]
    rank_zero = _prefer_simpler_equivalents(rank_zero)
    rank_zero.sort(key=lambda item: (*item.objectives, *_design_complexity(item.design)))
    return tuple(rank_zero)


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
                min_pole_turn_radius_mm=self.feasibility.min_pole_turn_radius_mm,
                min_inter_block_gap_mm=self.feasibility.min_inter_block_gap_mm,
                enforce_layer_nesting=self.feasibility.enforce_layer_nesting,
                geometry_tolerance_mm=self.feasibility.geometry_tolerance_mm,
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
    # dd's own topology-collapse review (REVIEW_blind_optimizer_topology_collapse.md,
    # section 5.8/T5) found that pymoo-style SBX crossover blending discrete
    # genes (then rounding) "is semantically weak and tends to push [them]
    # toward whichever parent dominates the front" -- accelerating premature
    # convergence to the incumbent topology. pymoo's MixedVariableMating
    # already avoids this for Binary (``active``) genes via UX (uniform
    # gene swap, no interpolation), but its own default for Integer
    # (``n_turns``) is still ``SBX(vtype=float, repair=RoundingRepair())``,
    # the exact blend-then-round pattern dd's review flagged. Override it
    # with the same UX swap used for Binary -- an integer-exact swap, never
    # a blend -- matching dd's actual fix.
    crossover = {
        Binary: UX(),
        Real: SBX(),
        Integer: UX(),
        Choice: UX(),
    }
    # With crossover no longer blending Integer (n_turns) genes, mutation is
    # the ONLY source of new turn values -- and pymoo's default per-gene
    # mutation rate (``prob_var = min(0.5, 1/n_var)``) is far too low for
    # DOT's genomes (~1.7% per gene at n_var=60), confirmed empirically:
    # only 11/30 random seeds produced any novel turn value across 12
    # offspring under the default rate. dd's own turn mutation rate is an
    # explicit, deliberately-tuned constant (``turn_mutation_prob=0.20``,
    # not the generic 1/n_var default) -- matched here for the same reason.
    mutation = {
        Binary: BFM(),
        Real: PM(),
        Integer: PM(vtype=float, repair=RoundingRepair(), prob_var=0.2),
        Choice: ChoiceRandomMutation(),
    }
    mating: InfillCriterion = MixedVariableMating(
        crossover=crossover,
        mutation=mutation,
        repair=repair,
        eliminate_duplicates=duplicate_elimination,
    )
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
    further from the block's own ``phi_deg`` anchor toward increasing
    ``phi`` (the pole) -- see ``_arc_stacked_anchor`` in
    ``dot.geometry.primitives``. So a
    block with ``n_turns`` turns spans roughly ``n_turns`` cable widths of
    angle poleward of its anchor, not just one. Its poleward neighbor's
    anchor must clear that whole span plus the explicit clearance, or
    ``check_turn_non_intersection`` will find real overlap even though the
    anchors themselves look adequately spaced.
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
    min_inter_block_gap_mm: float,
    midplane_gap_mm: float,
    midplane_anchor_offset_mm: float,
    rng: np.random.Generator,
) -> dict[str, float]:
    # Block 0 sits at the smallest phi (midplane); increasing block index
    # moves toward larger phi (pole).
    ordered = sorted(phi_variables, key=lambda item: item[1])
    footprints = [
        _minimum_phi_gap_deg(
            radius_mm,
            cable_width_mm,
            min_inter_block_gap_mm,
            n_turns=turn_counts.get(block_index, 1),
        )
        for _, block_index, _bounds in ordered
    ]
    proposals = {
        name: float(rng.uniform(bounds[0], bounds[1])) for name, _block_index, bounds in ordered
    }
    values: dict[str, float] = {}
    midward_name, _midward_index, midward_bounds = ordered[0]
    position = float(
        min(
            max(
                _midplane_anchor_phi_deg(
                    radius_mm,
                    midplane_gap_mm,
                    midplane_anchor_offset_mm,
                ),
                midward_bounds[0],
            ),
            midward_bounds[1],
        )
    )
    values[midward_name] = position
    for index in range(1, len(ordered)):
        name, _block_index, (lower, upper) = ordered[index]
        min_allowed = position + footprints[index - 1]
        position = float(min(upper, max(proposals[name], lower, min_allowed)))
        values[name] = position
    return values


def _midplane_anchor_phi_deg(
    radius_mm: float,
    one_sided_gap_mm: float,
    anchor_offset_mm: float = 0.0,
) -> float:
    """Anchor angle giving an alpha=0 midplane block its requested gap."""

    radius = max(1.0e-12, float(radius_mm))
    ratio = min(
        1.0,
        max(0.0, (float(one_sided_gap_mm) + float(anchor_offset_mm)) / radius),
    )
    return math.degrees(math.asin(ratio))


def _midplane_anchor_offset_mm(cable) -> float:  # noqa: ANN001
    """Distance from an alpha=0 anchor to the cable's lower y edge."""

    if math.isclose(
        cable.insulated_width_inner_mm,
        cable.insulated_width_outer_mm,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        return 0.5 * cable.insulated_width_inner_mm
    return 0.0


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


def _assign_sector_turns(
    sample: dict[str, float | int],
    layer_index: int,
    phi_variables: list[tuple[str, int, tuple[float, float]]],
    turn_bounds: tuple[int, int],
    target_total: int,
) -> None:
    """Distribute a generic sector-coil turn total across active blocks."""

    block_indices = sorted(block_index for _name, block_index, _bounds in phi_variables)
    lower, upper = turn_bounds
    remaining = max(len(block_indices) * lower, target_total)
    assignments = {block_index: lower for block_index in block_indices}
    remaining -= len(block_indices) * lower
    # Bias conductor gently toward the midplane, consistent with a cos-theta
    # current sheet, while respecting the user's per-block limits.
    while remaining > 0:
        progressed = False
        for block_index in block_indices:
            if assignments[block_index] >= upper:
                continue
            assignments[block_index] += 1
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break
    for block_index, turns in assignments.items():
        sample[f"layer_{layer_index}_block_{block_index}_n_turns"] = turns


def _sector_seed_phi_values(
    phi_variables: list[tuple[str, int, tuple[float, float]]],
    turn_counts: dict[int, int],
    radius_mm: float,
    cable_width_mm: float,
    min_inter_block_gap_mm: float,
    midplane_gap_mm: float,
    midplane_anchor_offset_mm: float,
    rng: np.random.Generator,
) -> dict[str, float]:
    """Build a packed, wedge-separated generic sector-coil seed."""

    ordered = sorted(phi_variables, key=lambda item: item[1])
    values: dict[str, float] = {}
    first_name, first_index, first_bounds = ordered[0]
    position = min(
        max(
            _midplane_anchor_phi_deg(
                radius_mm,
                midplane_gap_mm,
                midplane_anchor_offset_mm,
            ),
            first_bounds[0],
        ),
        first_bounds[1],
    )
    values[first_name] = float(position)
    previous_index = first_index
    for name, block_index, (lower, upper) in ordered[1:]:
        footprint = _minimum_phi_gap_deg(
            radius_mm,
            cable_width_mm,
            min_inter_block_gap_mm,
            n_turns=turn_counts.get(previous_index, 1),
        )
        wedge_deg = float(rng.uniform(0.5, 4.0))
        position = float(min(upper, max(lower, position + footprint + wedge_deg)))
        values[name] = position
        previous_index = block_index
    return values


def _repair_target_gap_mm(
    feasibility: FeasibilitySettings,
    layer_index: int,
) -> float:
    """Minimum inter-block gap the phi repair/sampler should target.

    ``feasibility.min_gap_mm`` is the midplane-clearance value (dd's C4),
    which is unrelated to and typically much smaller than the inter-block
    gap requirement (dd's C7a/C7b, ``min_inter_block_gap_mm``). Repairing
    only to ``min_gap_mm`` left offspring with real (but unrepaired)
    ``inter_block_gap`` violations whenever a campaign configured a
    stricter wedge-gap minimum -- use whichever is larger.
    """

    configured = feasibility.min_inter_block_gap_mm
    if configured is None:
        inter_block_gap = 0.0
    elif isinstance(configured, RealNumber):
        inter_block_gap = float(configured)
    else:
        values = tuple(float(value) for value in configured)
        if layer_index < 0 or layer_index >= len(values):
            raise ValueError(
                "min_inter_block_gap_mm sequence length must match the topology layers"
            )
        inter_block_gap = values[layer_index]
    return max(feasibility.min_gap_mm, inter_block_gap)


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
