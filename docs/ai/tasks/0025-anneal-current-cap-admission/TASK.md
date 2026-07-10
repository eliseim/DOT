# TASK: Anneal the current-cap constraint like harmonic/margin admission

- **ID**: 0025-anneal-current-cap-admission
- **Status**: draft
- **Model/effort**: Moderate effort. Small, well-scoped change to
  `src/dot/optimize/problem.py`, following an already-established pattern
  (task 0023's harmonic/margin annealing) rather than inventing a new
  mechanism. No live-ROXIE requirement — validation is empirical
  (feasibility/convergence), same as tasks 0022/0023.

## Background

A real CTH campaign (12.4T target, 25% min margin, 5 units max harmonics,
13000A current cap, full geometric constraints) stalled completely: every
candidate in the final population of 120 individuals was penalized, with
zero exceptions. Root cause, confirmed by direct inspection of the final
population's constraint values:
`DipoleOptimizationProblem._evaluate` (`src/dot/optimize/problem.py`,
current lines ~137-144) checks the current cap with a **flat, ungraded**
penalty:

```python
solved = operating_point(unit_design, self.targets.target_bore_field_t)
if (
    self.targets.max_current_a is not None
    and abs(solved.operating_current_a) > self.targets.max_current_a
):
    objectives[row_index] = (_PENALTY, _PENALTY)
    constraints[row_index, 0] = 1.0
    continue
```

This is fundamentally different from how task 0023 already handles the
harmonic and margin admission targets a few lines later in the same
function — those use a graded, continuous constraint value
(`constraints[row_index, target_constraint_index] = max(0.0, field_quality
- harmonic_threshold)`, similarly for margin) **and** an annealed
threshold via `admission_thresholds()` that starts relaxed and tightens to
the true target over the campaign's generation budget.

When a campaign's geometrically-feasible seed population is current-
infeasible from generation 0 (as happened here — realistic turn
placements needed ~18-19kA against a 13000A cap), the flat penalty gives
NSGA-II **zero gradient** to distinguish "1% over the cap" from "50% over
the cap." Every individual collapses to the same `_PENALTY` value and
selection has nothing to climb. This is the same problem task 0023 already
solved for harmonic/margin — it just never got applied to the current cap.

The user's own diagnosis, which this task should implement: margin is
already a continuous objective (`-margin_percent`) that degrades
monotonically as current rises, so the gradient needed to steer the search
toward lower current already exists via margin quality — *if* the current
cap doesn't cut candidates off before that gradient can be used. The fix
is not to loosen the cap permanently (13000A is presumably a genuine
power-supply/engineering limit, not a soft preference) but to **anneal
it** exactly like harmonic/margin: start relaxed (e.g. ~2x the target) in
early generations, tighten to the true `max_current_a` by the final
generation. Early on, over-current candidates survive on margin/harmonic
quality alone (giving the search room to discover efficient turn
placements); by the end, the real hard limit is enforced.

## Goal

1. Extend `DipoleOptimizationProblem.admission_thresholds()` to also
   return an annealed current-cap threshold, following the exact same
   linear relaxation-to-target pattern already used for
   `max_harmonic_units`/`min_margin_percent` (see
   `_START_HARMONIC_RELAXATION_MULTIPLIER`/`_START_MARGIN_RELAXATION_PERCENT`
   — add an analogous `_START_CURRENT_RELAXATION_MULTIPLIER`, default
   value your call, but justify it — the background section suggests ~2x
   as a starting point given the observed 18-19kA vs 13000A gap, but
   check empirically what works).
2. Replace the flat current-cap check in `_evaluate` with a graded
   constraint in its own `G` column, matching the harmonic/margin pattern:
   `constraints[row_index, current_constraint_index] = max(0.0,
   abs(operating_current_a) - current_threshold)`. This should **not**
   short-circuit with `continue` before computing objectives — a design
   that's over the *annealed* (relaxed) threshold but still geometrically
   valid should still get real `field_quality`/`margin_percent` objective
   values computed, so the search has real information to act on. Only
   truly pathological cases (the existing `except (KeyError, ValueError,
   ZeroDivisionError)` block) should still skip objective computation.
3. Update `n_ieq_constr` in `__init__` to account for the new current
   constraint column when `targets.max_current_a is not None` (currently
   it's `1 + int(max_harmonic_units is not None) +
   int(min_margin_percent is not None)` — add
   `+ int(max_current_a is not None)`).
4. Re-run the exact CTH campaign scenario from the background (or an
   equivalent smaller repro) before and after this change, and report
   whether the population now contains non-penalized candidates with real
   objective values, and whether the achieved current trends downward
   over generations toward the true cap.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/problem.py`
- `src/dot/optimize/runner.py` (only if the generation-count wiring needs
  adjustment for the new threshold — check first, it likely already works
  via the existing `set_generation`/`admission_thresholds` mechanism)
- `tests/optimize/test_problem.py`

## Explicit non-goals

- No change to the harmonic/margin annealing logic itself (already
  correct) — only add the analogous current-cap treatment.
- No change to geometry constraints, the genetic operators (task 0022), or
  physics/ROXIE-parity code.
- Do not remove or permanently loosen `max_current_a` — it must still be
  the true, enforced limit by the final generation.
- Do not weaken any existing test's tolerance to force a pass.

## Acceptance criteria

- [ ] `admission_thresholds()` returns a third value (current threshold)
      following the same annealing pattern, with a unit test analogous to
      the existing `test_problem_anneals_target_admission_thresholds_to_final_targets`.
- [ ] The current-cap constraint is graded (not flat `1.0`), verified with
      a unit test showing two different over-cap currents produce
      distinguishable `G` values.
- [ ] Objectives are computed (not skipped) for designs within the
      *annealed* threshold even if over the *final* `max_current_a` —
      verify with a test.
- [ ] Empirical re-run of the stalled CTH scenario (or an equivalent):
      report whether non-penalized candidates now appear in the
      population and whether current trends toward the cap over
      generations. Report honestly if it still doesn't fully converge —
      this task's job is to fix the gradient problem, not guarantee every
      possible campaign configuration finds a feasible design.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material

- `src/dot/optimize/problem.py` — read the existing harmonic/margin
  annealing implementation fully before writing the current-cap version;
  match its style and conventions exactly.
- The coordinator's own campaign scripts at
  `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign3.py`
  and `cth_sampler2.py` (read-only, for reproducing the stalled scenario
  if useful — these are exploratory scratch scripts, not part of the DOT
  package).
