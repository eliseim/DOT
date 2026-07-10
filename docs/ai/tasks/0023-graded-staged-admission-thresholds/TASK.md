# TASK: Graded constraint severity + staged admission thresholds

- **ID**: 0023-graded-staged-admission-thresholds
- **Status**: draft
- **Model/effort**: High effort. Touches `src/dot/geometry/constraints.py`,
  a previously validated file (feasibility logic, not the ROXIE-parity
  geometry itself) — extend it additively, do not change existing
  pass/fail behavior. Validation is via empirical convergence/feasibility
  comparison, not live ROXIE (this task doesn't touch physics).

## Background

DOT's optimizer (`src/dot/optimize/problem.py::DipoleOptimizationProblem._evaluate`)
currently gates infeasible genomes with a flat, ungraded penalty: if
`check_feasibility(...)` reports any violation, both objectives are set to
a huge fixed constant (`_PENALTY = 1e12`) and the pymoo inequality
constraint `G` is set to `float(len(feasibility.violations))` — the
**count** of violations, not their severity. A genome that's infeasible by
a hair (e.g. one turn overlapping its neighbor by 0.01mm) is scored
identically to one that's wildly infeasible (turns overlapping by 10mm) —
both just get "1e12, 1e12" and a `G` value with no gradient for selection
pressure to climb. Similarly, DOT has no equivalent of `dipole_designer`'s
`admission.py`, which relaxes harmonic-quality/margin *targets* early in a
campaign and tightens them toward the user's true target over the run
(constraint annealing) — DOT's `max_harmonic_units`/`min_margin_percent`
targets, if set, are presumably applied as hard cutoffs from generation 0
(check `src/dot/optimize/problem.py` and `objectives.py` for how these are
currently used, if at all — read before assuming).

A comparative audit of `dipole_designer`'s optimizer found this pattern
(`admission.py`, 190 lines) to be a genuinely general, ROXIE-independent
NSGA-II technique — nothing about it depends on external solver calls —
and likely DOT's highest-value, lowest-cost algorithmic improvement, since
DOT can afford far more generations to anneal a relaxation schedule over
than `dipole_designer` ever could against expensive ROXIE evaluations.

## Goal

1. **Graded geometric constraint severity.** Extend
   `src/dot/geometry/constraints.py`'s `Violation` dataclass with a
   numeric severity field (e.g. `severity_mm` or similar — pick a
   consistent unit/sign convention and document it: recommend "how far
   past the limit," so `0` is exactly at the boundary and positive values
   are how infeasible it is; a satisfied constraint doesn't produce a
   `Violation` at all today, which is fine, keep that). Populate it in
   each `check_*` function using the actual clearance/angle value already
   being computed there (do not reverse-engineer it from the message
   string). **This must be additive and backward compatible**: existing
   callers/tests that only look at `is_feasible`/`violations` length must
   keep working unchanged; do not remove or rename any existing field.
2. Use this severity in `DipoleOptimizationProblem._evaluate`: replace
   `constraints[row_index, 0] = float(len(feasibility.violations))` with
   a continuous aggregate severity (e.g. sum or max of the violations'
   `severity_mm`, your call, justify the choice) so pymoo's constraint
   handling has an actual gradient to climb rather than a step function.
3. **Staged/annealed admission for target-based objectives.** If
   `OptimizationTargets.max_harmonic_units`/`min_margin_percent` are set,
   apply them as **relaxed-then-tightening** constraints over the
   campaign's generation budget (e.g. linear or another schedule from a
   generous starting threshold toward the user's true target by the final
   generation) rather than a hard cutoff from generation 0. This needs the
   current generation index available inside `_evaluate` — check how
   pymoo exposes this to a `Problem` (e.g. via `algorithm.n_gen` in a
   callback, or restructure so `run_campaign` threads it through) and use
   whatever's idiomatic for the installed pymoo version.
4. Report an honest empirical before/after: feasible-fraction of the final
   population and (if targets are set) how many campaigns reach at least
   one target-satisfying candidate, old flat-penalty/hard-cutoff approach
   vs. new graded/staged approach, for 2-3 configurations.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/constraints.py`
- `src/dot/optimize/problem.py`
- `src/dot/optimize/runner.py`
- `tests/geometry/test_constraints.py`
- `tests/optimize/test_problem.py`
- `tests/optimize/test_runner.py`

## Explicit non-goals

- No change to what counts as feasible/infeasible — `is_feasible`'s
  boolean semantics must not change for any existing test case. This task
  adds *severity* information, it does not change the feasibility
  boundary itself.
- No change to the geometry math that produces clearances/angles
  (`_distance_origin_to_polygon` etc.) — only expose the already-computed
  numeric value via `Violation`, don't recompute it differently.
- No topology search, no staged refinement, no operator changes — that's
  task 0022's scope, not this one.
- No change to physics/ROXIE-parity code.
- Do not weaken any existing test's tolerance to force a pass.

## Acceptance criteria

- [ ] `Violation` carries a numeric severity field, populated correctly by
      every `check_*` function, backward compatible with all existing
      tests (they must pass unmodified unless they specifically assert on
      the new field).
- [ ] `DipoleOptimizationProblem`'s `G` output uses graded severity, not a
      violation count. Unit test demonstrating two different infeasible
      genomes (barely infeasible vs. wildly infeasible) get distinguishable
      `G` values, not both collapsing to the same count.
- [ ] Staged/annealed admission implemented for target-based objectives
      when set; unit test demonstrating the effective threshold at an
      early generation is looser than at a late generation, converging to
      the user's true target by the end.
- [ ] Empirical before/after comparison reported honestly for 2-3
      configurations (per Goal 4) — including a configuration where the
      new approach does *not* help, if that's what's found.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\admission.py`
  — the relaxation/annealing pattern (read for the *concept*; DOT's
  target set is simpler — harmonic units and margin percent, not
  dipole_designer's full target-box system).
- `src/dot/geometry/constraints.py` — read fully before modifying; this
  file has existing test coverage that must not regress.
