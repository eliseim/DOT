# TASK: Update stale test fixtures after the geometry fix (task 0015)

- **ID**: 0016-update-stale-geometry-fixtures
- **Status**: draft
- **Model/effort**: Medium effort. Low-risk (test-only changes), but
  correctness matters: each updated expected value must be independently
  recomputed from the corrected geometry formula, not just adjusted until
  the assertion passes.

## Goal

Task 0015 fixed `src/dot/geometry/primitives.py`'s turn-generation formula
(now merged to `main`). Four existing tests elsewhere in the suite hardcode
expected values computed from the OLD, now-corrected formula, and
currently fail:

- `tests/geometry/test_constraints.py::test_midplane_clearance_accepts_hand_computed_gap`
- `tests/geometry/test_constraints.py::test_pole_angle_limit_accepts_outer_edge_below_limit`
- `tests/optimize/test_genome.py::test_partitioned_phi_windows_materially_improve_random_feasible_fraction`
- `tests/optimize/test_problem.py::test_problem_marks_operating_current_above_cap_as_constraint_violation`

Update each test's expected/hand-computed values to match the corrected
geometry. Do not weaken any assertion's intent (e.g. don't loosen a
tolerance or change what's being tested) — only correct the numeric
expectation to what the new, verified-correct geometry actually produces.

## Scope (files/modules Codex may touch)

- `tests/geometry/test_constraints.py`
- `tests/optimize/test_genome.py`
- `tests/optimize/test_problem.py`

## Explicit non-goals

- No changes to `src/dot/geometry/primitives.py` or any other source file
  — task 0015's geometry fix is correct and already verified against live
  ROXIE; this task only updates test expectations to match it.
- No changes to constraint-checking or optimizer logic.

## Acceptance criteria

- [ ] For each of the 4 failing tests, the new expected value is derived
      independently (e.g. recompute the hand-derivation in the test's own
      docstring/comment using the corrected formula, not by just running
      the code and pasting whatever it outputs) — state in your summary
      how each was recomputed.
- [ ] `test_partitioned_phi_windows_materially_improve_random_feasible_fraction`
      still demonstrates a **material improvement** from partitioned phi
      windows (task 0013's point) — update the specific count, but confirm
      the qualitative claim (partitioned > shared) still holds with the
      corrected geometry; if it doesn't, stop and report this as a finding
      rather than silently forcing new numbers to pass.
- [ ] `ruff check` clean; `pytest -q` passes with **zero** failures
      (previously-passing tests must remain passing).
- [ ] No files outside declared scope modified.
