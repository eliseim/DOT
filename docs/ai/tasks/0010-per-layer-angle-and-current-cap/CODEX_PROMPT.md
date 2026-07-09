# Codex worker prompt — TASK 0010-per-layer-angle-and-current-cap

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0010-per-layer-angle-and-current-cap/TASK.md` in this
worktree fully before writing any code. Read the actual current
implementations of `src/dot/geometry/constraints.py`,
`src/dot/optimize/problem.py`, `src/dot/optimize/operating_point.py`, and
`src/dot/gui/target_synthesis_gui.py` before changing anything — do not
guess signatures.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. `max_angle_deg` becomes `float | Sequence[float]` everywhere it's
   threaded through (constraints.py, FeasibilitySettings) — a single float
   must keep working exactly as before (backward compatibility is a hard
   requirement, verified by the existing test suite passing unmodified).
3. The current cap must be a real feasibility gate (candidate marked
   infeasible, not silently clipped or ignored).
4. Write the tests specified in TASK.md's acceptance criteria — especially
   the one proving per-layer angles actually produce different results
   than uniform angles, not just that the API accepts the new shape.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact
per-layer angle API shape chosen, how the current cap integrates into
`problem.py`'s `_evaluate`, the default angle values used in the GUI
(layer 1 = 80°, others = 85°, per TASK.md), and full test output.

## Task-specific instructions

Follow TASK.md's "Scope" and "API design guidance" sections precisely.
Read `_iter_indexed_turns` in `constraints.py` to reuse its per-turn
`layer_index` for the per-layer angle lookup.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite)
