# Codex worker prompt — TASK 0025-anneal-current-cap-admission

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0025-anneal-current-cap-admission/TASK.md` in this worktree
fully before writing any code. Read the current
`src/dot/optimize/problem.py` fully first — pay close attention to the
existing `admission_thresholds()` method and how harmonic/margin
constraints are graded in `_evaluate`; your job is to add a third,
analogous threshold, not invent a new mechanism.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Match the existing harmonic/margin annealing pattern exactly in style
   and structure — this should look like a natural extension of existing
   code, not a bolted-on special case.
3. No live-ROXIE requirement — this is optimizer search behavior, not
   physics. Validation is empirical (feasibility/convergence), reported
   honestly.
4. Do not remove or permanently loosen `max_current_a` — by the final
   generation it must be the true, enforced hard limit.
5. If your empirical re-run of the stalled scenario still doesn't fully
   converge to a target-satisfying candidate, report that honestly — this
   task's job is to fix the gradient problem (non-penalized candidates
   with real objective values existing in the population), not to
   guarantee any specific campaign finds a fully feasible design.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- The annealing schedule you chose for the current-cap threshold and why.
- Before/after empirical comparison on the stalled scenario (or an
  equivalent smaller repro): does the population now contain non-penalized
  candidates? Does achieved current trend toward the cap over generations?

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The empirical before/after comparison numbers explicitly
