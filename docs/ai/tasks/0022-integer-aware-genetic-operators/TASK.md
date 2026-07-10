# TASK: Integer-aware NSGA-II operators + constructive initial sampling

- **ID**: 0022-integer-aware-genetic-operators
- **Status**: draft
- **Model/effort**: High effort. This changes the optimizer's search
  behavior, not its physics — validation is via feasibility-rate and
  convergence comparisons (before/after), not live ROXIE checks. No
  ROXIE dependency for this task.

## Background

DOT's NSGA-II campaign (`src/dot/optimize/runner.py`) currently uses
`pymoo.algorithms.moo.nsga2.NSGA2(pop_size=N)` with every operator left at
pymoo's default: `FloatRandomSampling`, simulated binary crossover (SBX),
and polynomial mutation. The genome
(`src/dot/optimize/genome.py::encode`/`decode`/`genome_bounds`) is a flat
float vector where most slots are genuinely continuous (inner radius, phi,
alpha) but one slot per block — `n_turns` — is fundamentally **discrete**.
`decode()` rounds it to the nearest integer and clips to bounds, but the
GA operators upstream (SBX crossover, polynomial mutation) treat it as
continuous the whole time: this biases exploration (many distinct
float values round to the same integer, wasting search budget) and
produces crossover children whose "turn count gene" is a blended float
with no direct genetic meaning.

A comparative audit of `dipole_designer`'s much larger optimizer
(`C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\`)
found that most of its sophistication (ROXIE circuit breakers, disk
guards, campaign watchdogs, staged topology-refinement, topology-family
survival niching) solves problems specific to *searching over discrete
topology under expensive ROXIE-backed evaluations* — none of which apply
to DOT (topology is fixed per campaign by the caller; evaluations are
~1ms, in-process, no external ROXIE calls). Two techniques from that
codebase were identified as genuinely general, portable, and worth
adapting at DOT's much smaller scale:

1. **Gene-kind-aware crossover/mutation** (`target_synthesis_variation.py`)
   — never apply continuous blend operators to a variable that's really
   discrete; use integer-appropriate operators instead.
2. **Constructive (non-uniform-random) initial sampling**
   (`target_synthesis_initializer.py`, in much reduced form) — build the
   initial population with correct monotonic phi ordering and
   minimum-gap spacing baked in, instead of pure uniform-random sampling
   of the genome's bounding box, which mostly produces infeasible
   individuals for a tightly-packed coil cross-section.

## Goal

1. Give `n_turns` genome slots integer-aware treatment. Use pymoo's
   mixed-variable support (`pymoo.core.variable.Integer`/`Real`, or the
   `MixedVariableGA`/`MixedVariableSampling`/`MixedVariableMating`
   machinery — check what's available in the installed pymoo version, and
   use its idiomatic mixed-variable API rather than hand-rolling a custom
   `Problem` subclass from scratch if pymoo already provides this
   cleanly) so that `n_turns` genes get integer-appropriate crossover
   (e.g. integer SBX/PM variants pymoo provides for `Integer` variables,
   or a swap/random-reset mutation) while radius/phi/alpha genes keep
   real-valued SBX/polynomial operators.
2. Add a constructive initial-population sampler: instead of
   `FloatRandomSampling` (uniform over the full genome bounding box),
   generate initial individuals by placing each layer's blocks with
   correct monotonic phi ordering and a minimum angular gap between
   adjacent blocks (matching the same feasibility notion already checked
   by `dot.geometry.constraints.check_feasibility` — read that module to
   reuse its actual gap/angle definitions, don't reinvent a different
   notion of "gap"), and turn counts drawn from the layer's bounds rather
   than left to chance. This does not need to be a large, defensive
   system with retries/fallback chains like `dipole_designer`'s — DOT's
   evaluation cost is low enough that if a small fraction of constructed
   individuals are still infeasible, they'll simply be penalized and
   selected against normally. Keep it simple.
3. Measure and report the before/after effect: run the same campaign
   configuration (topology, targets, feasibility settings, seed) with the
   old defaults vs. the new operators/sampler, over a fixed generation
   budget, and report the feasible-fraction of the final population and
   the number of generations until the first fully-feasible generation,
   for at least 2-3 different topologies/target configurations (e.g. the
   ones already used in `tests/optimize/test_runner.py` or similar
   existing test fixtures — check what's there first). This task's
   "validation" is this empirical comparison, not a live-ROXIE check.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/genome.py`
- `src/dot/optimize/problem.py`
- `src/dot/optimize/runner.py`
- `tests/optimize/test_genome.py`
- `tests/optimize/test_problem.py`
- `tests/optimize/test_runner.py`

## Explicit non-goals

- No topology search (layer count, block count, cable assignment stay
  fixed by the caller, exactly as today).
- No staged/two-phase refinement, no topology-family survival niching —
  explicitly decided against for DOT (see Background); do not add them.
- No change to `src/dot/optimize/objectives.py` or any physics code.
- No change to the admission/constraint-severity handling — that's task
  0023's scope, not this one. Keep `check_feasibility`'s existing
  violation-count-based `G` output as-is here (0023 will replace it).
- Do not weaken any existing test's tolerance to force a pass.

## Acceptance criteria

- [ ] `n_turns` genes are handled by an integer-appropriate operator, not
      real-valued SBX/polynomial mutation followed by rounding. Show a
      unit test demonstrating the new sampling/crossover/mutation
      actually produces integer-valued (or integer-after-minimal-rounding
      in a way that differs demonstrably from naive float SBX) `n_turns`
      genes, distinct from the old behavior.
- [ ] Constructive initial sampling is implemented and demonstrably
      increases the feasible fraction of the *initial* population
      (generation 0) compared to `FloatRandomSampling`, for at least one
      realistic multi-block topology — report the actual before/after
      percentages.
- [ ] Empirical before/after comparison (per Goal 3) reported for at least
      2-3 configurations: feasible-fraction of final population and
      generations-to-first-fully-feasible-generation, old operators vs.
      new. If the new operators do *not* improve on the old ones for some
      configuration, report that honestly — don't cherry-pick only the
      favorable comparison.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\target_synthesis_variation.py`
  — gene-kind-aware crossover/mutation pattern (read for the *concept*,
  DOT's genome is much simpler — don't port the repair/regeneration
  machinery, that's explicitly out of scope).
- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\target_synthesis_initializer.py`
  — constructive sampling pattern (read for the *concept* only; DOT needs
  a small fraction of this file's complexity — no topology strata, no
  turn-density modes, no retry/fallback chains, no telemetry).
- pymoo's own documentation/source for mixed-variable support
  (`pymoo.core.variable`, `pymoo.core.mixed`) — check what version is
  installed and what's idiomatically available before hand-rolling
  anything.
- `src/dot/geometry/constraints.py` — the actual feasibility/gap
  definitions to match when building the constructive sampler.
