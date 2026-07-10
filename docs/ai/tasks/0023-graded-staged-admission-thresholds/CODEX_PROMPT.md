# Codex worker prompt — TASK 0023-graded-staged-admission-thresholds

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0023-graded-staged-admission-thresholds/TASK.md` in this
worktree fully before writing any code. This continues from task 0022
(should already be merged — check `git log` on main before starting; if
it isn't merged yet, stop and report back rather than building on an
unmerged branch). Read the current
`src/dot/geometry/constraints.py`, `src/dot/optimize/problem.py`, and
`runner.py` fully first.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. **`constraints.py` is a previously-validated file** (feasibility logic
   used throughout the project). Your change must be strictly additive:
   every existing test must keep passing unmodified, and `is_feasible`'s
   boolean result must not change for any existing case — you are adding
   a severity *field*, not changing the feasibility boundary.
3. This task has no live-ROXIE requirement — validation is empirical
   (feasibility-rate/convergence) comparison, reported honestly.
4. Do not implement anything from TASK.md's "Explicit non-goals" — no
   change to the geometry math itself, no operator/sampler changes (task
   0022's scope), no physics changes.
5. If the new approach does not empirically improve on the old one for
   some tested configuration, report that honestly.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- The severity field's unit/sign convention and how each `check_*`
  function populates it.
- How the annealing schedule for target-based admission is threaded
  through (how generation index reaches `_evaluate`).
- The empirical before/after comparison from TASK.md's Goal 4, for 2-3
  configurations, reported honestly.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The empirical before/after comparison numbers explicitly
