"""Staged refinement ("Phase B" polish) for near-feasible candidates (task 0048).

Ports dipole_designer's own staged-refinement premise: freeze a near-
feasible candidate's topology (turns, active blocks, radii) and locally
perturb only its phi/alpha genes to nudge it across the feasibility line --
closing exactly the kind of small residual violation (one turn's pole-angle
or intersection margin) that a broad NSGA-II search can leave on the table.

Architecture note: dipole_designer's version reuses its own NSGA-II
machinery for this local search. DOT's ``LayerTopology.n_turns_bounds`` is
shared across every block in a layer (not per-block), so per-block turn
freezing isn't directly expressible through the existing
``Topology``/``genome_bounds()`` schema without deeper genome.py changes.
Implemented instead as a small, hand-rolled local search directly over
``DipoleDesign`` objects (``dataclasses.replace`` on ``Block``): this gives
an exact freezing guarantee (turns/active-pattern/radii are copied
byte-for-byte from the seed, never touched) with far less blast radius
than threading a frozen-gene concept through the mixed-variable genome.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from dot.geometry import Block, DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility

from .objectives import field_quality_objective, load_line_margin_objective
from .operating_point import operating_point
from .problem import FeasibilitySettings, OptimizationTargets
from .runner import ParetoCandidate, ParetoResult, _margin_exclusions
from .topology_survival import topology_family


@dataclass(frozen=True, slots=True)
class RefinementConfig:
    """Settings for the staged-refinement local search."""

    enabled: bool = False
    max_seeds: int = 4
    max_seeds_per_topology: int = 1
    population: int = 8
    generations: int = 3
    angular_mutation_probability: float = 0.7
    angular_mutation_sigma_deg: float = 1.0
    # task 0049: dd's "mixed-turn refinement" -- angle-only refinement
    # (task 0048) proved it can drive harmonic content down sharply but
    # cannot move load-line margin at all, since margin is governed by
    # turns/current, both frozen by angle-only perturbation. Unfreezing
    # turns here lets refinement explore that axis too, directly around a
    # seed that already has good field quality.
    mixed_turn_enabled: bool = False
    turn_mutation_probability: float = 0.35
    turn_step: int = 1
    # Probability that a turn mutation TRANSFERS turn_step turns between
    # two blocks in the same layer (preserving that layer's -- and the
    # design's -- total turn count) rather than growing/shrinking one
    # block's turns unilaterally (letting the total drift, bounded by
    # max_total_turns).
    preserve_layer_total_probability: float = 0.8
    max_total_turns: int | None = None


def select_refinement_seeds(
    candidates: tuple[ParetoCandidate, ...],
    config: RefinementConfig,
) -> tuple[ParetoCandidate, ...]:
    """Pick diverse seeds via round-robin across ranking views.

    Round-robins across field-quality (best harmonic content first),
    margin (best load-line margin first), and topology-family novelty
    (spreading picks across distinct decoded phenotypes) so no single
    metric dominates seed choice -- mirrors dipole_designer's own
    rationale for avoiding a single ranking view starving diversity in the
    seed pool.
    """

    if not candidates:
        return ()

    by_field_quality = sorted(candidates, key=lambda c: c.objectives[0])
    by_margin = sorted(candidates, key=lambda c: c.objectives[1])
    by_novelty = sorted(candidates, key=lambda c: topology_family(c.design))
    views = [list(by_field_quality), list(by_margin), list(by_novelty)]

    seeds: list[ParetoCandidate] = []
    family_counts: dict[str, int] = {}
    view_index = 0
    while len(seeds) < config.max_seeds and any(views):
        view = views[view_index % len(views)]
        view_index += 1
        if not view:
            continue
        candidate = view.pop(0)
        family = topology_family(candidate.design)
        if family_counts.get(family, 0) >= config.max_seeds_per_topology:
            continue
        seeds.append(candidate)
        family_counts[family] = family_counts.get(family, 0) + 1
        # ParetoCandidate carries a numpy-array genome field, so `in`/
        # `.remove()` (which use `==`) raise "truth value of an array is
        # ambiguous" -- compare by identity instead.
        for other_view in views:
            for index, item in enumerate(other_view):
                if item is candidate:
                    del other_view[index]
                    break

    return tuple(seeds)


def run_refinement(
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    seeds: tuple[ParetoCandidate, ...],
    config: RefinementConfig,
    random_state: np.random.Generator | None = None,
) -> ParetoResult:
    """Locally polish each seed's phi/alpha genes, verified against real feasibility."""

    rng = np.random.default_rng() if random_state is None else random_state
    candidates: list[ParetoCandidate] = []
    for seed in seeds:
        candidates.extend(_refine_one_seed(seed, targets, feasibility, config, rng))
    return ParetoResult(candidates=tuple(candidates), excluded_margin_layers=_margin_exclusions(targets))


def _refine_one_seed(
    seed: ParetoCandidate,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    config: RefinementConfig,
    rng: np.random.Generator,
) -> list[ParetoCandidate]:
    found: list[ParetoCandidate] = []
    current = seed.design
    for _generation in range(config.generations):
        offspring = [_perturb_design(current, rng, config) for _ in range(config.population)]
        generation_results: list[ParetoCandidate] = []
        for design in offspring:
            candidate = _evaluate_if_feasible(design, targets, feasibility)
            if candidate is not None:
                generation_results.append(candidate)
        if not generation_results:
            continue
        found.extend(generation_results)
        current = min(generation_results, key=lambda c: c.objectives[0]).design
    return found


def _evaluate_if_feasible(
    design: DipoleDesign,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
) -> ParetoCandidate | None:
    result = check_feasibility(
        design,
        aperture_radius_mm=design.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        max_angle_deg=feasibility.max_angle_deg,
        min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
        min_pole_gap_mm=feasibility.min_pole_gap_mm,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        enforce_layer_nesting=feasibility.enforce_layer_nesting,
    )
    if not result.is_feasible:
        return None
    try:
        solved = operating_point(design, targets.target_bore_field_t)
        field_quality = field_quality_objective(solved.design, targets.r_ref_mm, targets.max_order)
        margin_percent = load_line_margin_objective(
            solved.design,
            tuple(),
            targets.cadata_by_layer,
            targets.temperature_k,
        )
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    return ParetoCandidate(
        genome=np.empty(0, dtype=float),
        design=solved.design,
        objectives=(field_quality, -margin_percent),
    )


def _perturb_design(
    design: DipoleDesign,
    rng: np.random.Generator,
    config: RefinementConfig,
) -> DipoleDesign:
    """Perturb phi/alpha (always) and, if enabled, turn counts (task 0049).

    Active-block pattern, cable, and radius stay frozen either way -- only
    the number of new perturbation KINDS grows (turns joins phi/alpha),
    never the set of frozen structural parameters.
    """

    layers = []
    for layer in design.layers:
        blocks = _perturb_turns(list(layer.blocks), rng, config) if config.mixed_turn_enabled else list(layer.blocks)
        blocks = [_perturb_block_angles(block_index, block, rng, config) for block_index, block in enumerate(blocks)]
        layers.append(Layer(inner_radius_mm=layer.inner_radius_mm, blocks=tuple(blocks)))
    perturbed = DipoleDesign(aperture_radius_mm=design.aperture_radius_mm, layers=tuple(layers))

    if config.max_total_turns is not None:
        total_turns = sum(block.n_turns for layer in perturbed.layers for block in layer.blocks)
        if total_turns > config.max_total_turns:
            # Turn mutation pushed past the budget -- revert turns (keep
            # the angle perturbation, which is always budget-safe since it
            # never touches turn counts).
            return _perturb_design(design, rng, replace(config, mixed_turn_enabled=False))

    return perturbed


def _perturb_block_angles(
    block_index: int,
    block: Block,
    rng: np.random.Generator,
    config: RefinementConfig,
) -> Block:
    if rng.random() >= config.angular_mutation_probability:
        return block
    phi_delta = float(rng.normal(0.0, config.angular_mutation_sigma_deg))
    # Block 0 of every layer keeps alpha_deg=0.0 -- DOT's own invariant
    # (only valid near the midplane, structurally hard-fixed everywhere
    # else in the genome).
    if block_index == 0:
        return replace(block, phi_deg=block.phi_deg + phi_delta)
    alpha_delta = float(rng.normal(0.0, config.angular_mutation_sigma_deg))
    return replace(block, phi_deg=block.phi_deg + phi_delta, alpha_deg=block.alpha_deg + alpha_delta)


def _perturb_turns(
    blocks: list[Block],
    rng: np.random.Generator,
    config: RefinementConfig,
) -> list[Block]:
    if rng.random() >= config.turn_mutation_probability:
        return blocks

    if len(blocks) >= 2 and rng.random() < config.preserve_layer_total_probability:
        donor_index, recipient_index = rng.choice(len(blocks), size=2, replace=False)
        donor = blocks[donor_index]
        if donor.n_turns - config.turn_step >= 1:
            blocks = list(blocks)
            blocks[donor_index] = replace(donor, n_turns=donor.n_turns - config.turn_step)
            recipient = blocks[recipient_index]
            blocks[recipient_index] = replace(recipient, n_turns=recipient.n_turns + config.turn_step)
        return blocks

    # Grow or shrink a single block's turns -- the design's total turn
    # count is allowed to drift, bounded by max_total_turns in the caller.
    index = int(rng.integers(0, len(blocks)))
    block = blocks[index]
    direction = 1 if rng.random() < 0.5 else -1
    new_turns = block.n_turns + direction * config.turn_step
    if new_turns < 1:
        return blocks
    blocks = list(blocks)
    blocks[index] = replace(block, n_turns=new_turns)
    return blocks
