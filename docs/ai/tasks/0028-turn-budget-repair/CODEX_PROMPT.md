# Codex worker prompt — TASK 0028-turn-budget-repair

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0028-turn-budget-repair/TASK.md` in this worktree fully
before writing any code. Read `src/dot/optimize/runner.py` fully first —
`PhiOrderingRepair` (task 0022) is the direct precedent for what you're
building; understand it completely before adding a parallel mechanism for
turn budgets.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. This is a **repair** mechanism, not an annealing one — the Background
   section explains why that's the right call for this specific
   constraint (a discrete structural sum, not a continuous physics
   quantity). Don't substitute annealing for convenience without a
   specific, documented reason repair doesn't work.
3. No live-ROXIE requirement — optimizer search behavior, not physics.
4. Respect each block's own `n_turns_bounds` lower limit when reducing
   turns — don't produce an invalid genome.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Your chosen turn-reduction rule and why.
- How the new repair composes with `PhiOrderingRepair` in
  `_mixed_variable_nsga2`/`run_campaign`.
- The before/after empirical repro from TASK.md's acceptance criteria:
  real-objective-individual count collapsing without repair, staying
  healthy with it.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The before/after empirical repro, explicitly
