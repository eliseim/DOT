# TASK: Repair turn-count budget violations after mating

- **ID**: 0028-turn-budget-repair
- **Status**: draft
- **Model/effort**: Moderate-high effort. Touches `src/dot/optimize/runner.py`
  (extends/adds a `Repair`, following the exact pattern already established
  by `PhiOrderingRepair` from task 0022) and possibly
  `src/dot/optimize/problem.py` (task 0027's turn-budget constraint
  handling). No live-ROXIE requirement — optimizer search behavior, not
  physics. Validation is empirical (feasibility/convergence).

## Background

Task 0027 added `max_total_turns`/`max_turns_per_layer` as graded, **not
annealed**, constraints — the reasoning at the time was that turn-count
budgets are a discrete structural limit "directly controllable by the
genome's own bounds," unlike current/harmonic/margin (continuous physics
quantities that benefit from gradual relaxation). A real CTH campaign
(6 layers → later 4 layers x 4 blocks, `max_total_turns=100`,
`max_turns_per_layer=30`, using the now-merged tasks 0025/0026/0027)
disproved this: the constructive sampler (a coordinator scratch script,
`ActiveAwareGrowthSampling`) correctly builds an initial population where
every individual respects the turn budget, producing 22 individuals with
real (non-`_PENALTY`) objective values at generation 1 — but by
generation 5, that number collapses to **0** and stays there for the
remaining 75 generations.

Root cause: `max_total_turns`/`max_turns_per_layer` constrain a **sum
across multiple genes** (every active block's `n_turns`, across every
layer). Per-gene bounds (`n_turns_bounds` on each block) cannot enforce a
cross-gene sum constraint — an offspring produced by ordinary integer
crossover/mutation can easily have every individual `n_turns` gene within
its own valid range while the *sum* exceeds the budget. Unlike phi
ordering (which task 0022 already fixed with `PhiOrderingRepair`, restoring
validity after every mating step), there is currently **no repair
mechanism for turn budgets** — `problem.py`'s `_evaluate` just detects the
violation post-hoc and short-circuits to `_PENALTY` objectives (see
current code: `if turn_budget_violation: objectives[row_index] =
(_PENALTY, _PENALTY); continue`). Once mating starts producing
over-budget offspring at a high rate (apparently the common case), the
whole population collapses to `_PENALTY` with no repair to recover from
it and no annealed threshold to fall back on either.

This is the same class of problem as the current-cap stall task 0025 fixed,
but the fix should be different: current/harmonic/margin are continuous
physics quantities where *annealing* (relaxed-then-tightening threshold)
is the natural fix. Turn budgets are a discrete structural constraint
directly computable from the genome, closer in spirit to phi ordering —
so the better-motivated fix, consistent with `PhiOrderingRepair`'s
precedent, is an active **repair** step that restores budget compliance
after mating, not (only) annealing.

## Goal

1. Add a repair mechanism (a new `Repair` class, or extend
   `PhiOrderingRepair` if that's cleaner — your call, but keep the
   responsibilities clear) that, after mating produces an offspring
   genome, checks `max_total_turns`/`max_turns_per_layer` and if
   exceeded, reduces `n_turns` values until back within budget. Design
   the reduction rule deliberately (e.g., reduce from the block(s)
   currently holding the most turns first, or proportionally across all
   active blocks, or some other well-justified rule) — document and
   justify whichever you choose. Respect each block's own
   `n_turns_bounds` lower limit (don't reduce a block below its minimum).
   If a genome can't be brought into budget without violating a lower
   bound (e.g. too many active blocks for the budget), that's fine —
   leave it as still-violating; the existing graded constraint in
   `problem.py` will still penalize it, this repair just needs to handle
   the common/fixable case.
2. Reconsider whether `problem.py`'s current hard `_PENALTY` short-circuit
   for turn-budget violations is still the right behavior once repair
   exists — probably keep it (repair should eliminate most violations
   before they reach evaluation), but confirm and justify your choice.
3. Wire the new repair into `run_campaign`'s `_mixed_variable_nsga2` (or
   equivalent) alongside `PhiOrderingRepair` — check whether pymoo's
   `MixedVariableMating` supports composing multiple repair steps
   cleanly, or whether you need a single combined `Repair` that does both
   phi-ordering and turn-budget repair in sequence.
4. Empirically validate: reproduce the collapse (a small repro case is
   fine, doesn't need to be the full CTH scenario) showing the *current*
   behavior (real-objective count collapsing to ~0 within a handful of
   generations when a turn budget is set), then show the same scenario
   with your repair in place maintains a healthy population of
   real-objective individuals across the full generation budget.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/runner.py`
- `src/dot/optimize/problem.py` (only if you determine the `_PENALTY`
  short-circuit behavior needs to change per Goal 2 — justify any change)
- `tests/optimize/test_runner.py`
- `tests/optimize/test_problem.py` (only if `problem.py` changes)

## Explicit non-goals

- No change to the current/harmonic/margin annealing logic (tasks
  0023/0025, already correct) — this task is specifically about the
  turn-budget constraint's *lack* of a repair mechanism, a different kind
  of fix for a different kind of constraint.
- No change to the active/inactive block genome encoding itself (task
  0027, already correct and merged) — only add a repair step that
  operates on top of it.
- No change to physics/geometry code.
- Do not weaken any existing test's tolerance to force a pass.
- Do not simply anneal the turn budget as an alternative to repair unless
  you've tried repair first and have a specific, documented reason it
  doesn't work — the background section's reasoning for why repair is the
  better-motivated fix here should be taken seriously, not bypassed for
  convenience.

## Acceptance criteria

- [ ] A repair mechanism exists that reduces over-budget `n_turns` values
      while respecting each block's own lower bound, with a documented,
      justified reduction rule.
- [ ] Reproduce the collapse with a small repro case (not necessarily the
      full CTH scenario — a smaller topology with a tight turn budget is
      fine) showing real-objective-individual count dropping toward 0
      within a handful of generations *without* the repair.
- [ ] Show the same repro case *with* the repair maintains a healthy
      (not collapsing to 0) population of real-objective individuals
      across a realistic generation budget (e.g. 20-40 generations).
- [ ] Existing tests (including task 0022's `PhiOrderingRepair` tests and
      task 0027's turn-budget constraint tests) continue to pass
      unmodified.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material

- `src/dot/optimize/runner.py` — `PhiOrderingRepair` (task 0022) is the
  direct precedent and style guide for this task's repair mechanism.
- `src/dot/optimize/problem.py` — the current turn-budget constraint
  implementation (task 0027) and the current-cap annealing implementation
  (task 0025), for contrast — this task is deliberately *not* copying the
  annealing pattern, per the Background section's reasoning.
- The coordinator's own campaign script showing the collapse:
  `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py`
  and `cth_sampler3.py` (read-only, exploratory scratch scripts, not part
  of the DOT package) — `real_F=22` at generation 1 collapsing to
  `real_F=0` by generation 5 and staying there through generation 80 is
  the exact observed failure.
