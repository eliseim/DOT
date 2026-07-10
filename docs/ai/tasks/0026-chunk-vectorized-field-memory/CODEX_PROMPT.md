# Codex worker prompt — TASK 0026-chunk-vectorized-field-memory

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0026-chunk-vectorized-field-memory/TASK.md` in this
worktree fully before writing any code. Read `src/dot/physics/field.py`
fully first — this is task 0024's already-merged vectorization, which you
are fixing a real memory-scaling bug in, not rewriting from scratch.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. **This is a pure memory-management fix. The physics must not change.**
   Numerical outputs must match the current implementation to floating
   point precision or an extremely tight, justified tolerance.
3. First reproduce the actual crash from TASK.md's Background section
   yourself, so you have a real before-state to fix, not an assumed one.
4. Confirm `python -c "import roxieapi"` works on system Python before
   starting — you need live ROXIE re-validation for the acceptance
   criteria.
5. Report real measured numbers (memory, timing), don't estimate.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Your chunking strategy and chosen chunk size, with justification.
- Before (crash) / after (bounded, actual number) memory measurements for
  the large-design reproduction case.
- Wall-clock timing before/after for both a small/medium case and the
  large case.
- Live ROXIE re-validation numbers for 2-3 cases, confirming no numerical
  regression.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- Memory and timing numbers, explicitly, before and after
- Live ROXIE validation numbers, explicitly
