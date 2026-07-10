# Codex worker prompt — TASK 0024-vectorize-biot-savart-field (URGENT)

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. This is an **urgent**
performance task — it blocks all real optimization campaign work,
currently in progress by the coordinator. Read
`docs/ai/tasks/0024-vectorize-biot-savart-field/TASK.md` in this worktree
fully before writing any code. Read `src/dot/physics/field.py`,
`src/dot/physics/sources.py`, and `src/dot/optimize/objectives.py` fully
first.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. **This is a pure speed optimization. The physics must not change.**
   Every existing test (unit and live-ROXIE) must keep passing with
   materially the same numbers as before. If you find yourself needing to
   change what's being computed (not just how fast), stop and reconsider
   — that would be scope creep into already-validated tasks 0018/0019/0020
   territory.
3. Confirm `python -c "import roxieapi"` works on system Python before
   starting — you need live ROXIE re-validation for the acceptance
   criteria, not just unit tests.
4. Measure real wall-clock times, don't estimate. Report actual numbers.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Before/after wall-clock timing for the profiled 4-layer case (see
  TASK.md Background) and for `field_quality_objective`.
- What vectorization approach you used (NumPy arrays, and whether Numba
  was added and why/why not, per TASK.md Goal 3).
- Live ROXIE re-validation numbers for at least 2-3 cases from the
  existing test suite, before and after, confirming no numerical
  regression.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. Start
by reproducing the 24.4-second baseline yourself so you have a real
number to improve against, not an assumed one.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- Wall-clock before/after numbers, explicitly
- Live ROXIE before/after numbers for at least 2-3 cases, explicitly
