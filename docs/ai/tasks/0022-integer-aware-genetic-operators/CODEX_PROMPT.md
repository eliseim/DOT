# Codex worker prompt — TASK 0022-integer-aware-genetic-operators

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0022-integer-aware-genetic-operators/TASK.md` in this
worktree fully before writing any code. Read the current
`src/dot/optimize/genome.py`, `problem.py`, and `runner.py` fully first —
do not guess their structure.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. This task has **no live-ROXIE requirement** — it's optimizer search
   behavior, not physics. Validation is empirical (feasibility-rate,
   convergence) comparison, reported honestly, not a live external check.
3. Check what pymoo version is installed
   (`python -c "import pymoo; print(pymoo.__version__)"`) and use its
   idiomatic mixed-variable API if one exists for that version, rather
   than hand-rolling everything from scratch.
4. Do not implement anything from TASK.md's "Explicit non-goals" — no
   topology search, no staged refinement, no topology-family niching, no
   change to constraint/admission handling (that's a separate task).
5. If the new operators do not empirically improve on the old ones for
   some tested configuration, report that honestly — do not cherry-pick
   only favorable comparisons or tune the comparison to hide a
   regression.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- What mixed-variable/integer-aware approach you used and why (pymoo
  built-in vs. custom).
- The constructive sampler's design and how it matches
  `check_feasibility`'s actual gap/angle definitions.
- The empirical before/after comparison from TASK.md's Goal 3, for 2-3
  configurations, reported honestly.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The empirical before/after comparison numbers explicitly
