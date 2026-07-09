# Codex worker prompt — TASK 0003-geometry-constraints

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0003-geometry-constraints/TASK.md` in this worktree fully
before writing any code. The user has explicitly emphasized that geometric
feasibility must work correctly — an infeasible design must never be
silently reported as feasible downstream.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md: exactly
   `src/dot/geometry/constraints.py` and `tests/geometry/test_constraints.py`.
2. Implement exactly the 5 constraints listed in TASK.md. Do not add more
   rules, even if you notice something else that "should" be checked — flag
   it in your summary instead.
3. Build on top of task 0002's `TurnPolygon`/`Block`/`Layer`/`DipoleDesign`
   from `src/dot/geometry/primitives.py` (already merged into this branch)
   — do not redefine or duplicate that geometry model.
4. You may read the reference files listed in TASK.md for constraint
   *definitions* only. Do not copy code; DOT's types differ from theirs.
5. No ROXIE dependency. No optimizer, no GUI, no conductor/critical-current
   code.
6. Write real two-directional tests (accepts valid, rejects invalid) for
   every constraint, run `pytest` and `ruff check` yourself, report actual
   output.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared two files. A summary stating: the polygon
intersection algorithm chosen for turn-to-turn overlap and why it's correct
for convex quadrilaterals, and confirmation all 5 constraints are
independently testable functions aggregated into `check_feasibility`.

## Task-specific instructions

Implement `src/dot/geometry/constraints.py`:

- A `Violation` (or similarly named) dataclass: constraint name, a
  human-readable message, and identifiers for the offending
  layer/block/turn (indices are fine).
- A `FeasibilityResult` dataclass: `is_feasible: bool`,
  `violations: tuple[Violation, ...]`.
- Five independent check functions, one per constraint in TASK.md:
  1. `check_aperture_clearance(design, aperture_radius_mm) -> list[Violation]`
  2. `check_inter_layer_spacing(design, min_clearance_mm=0.1) -> list[Violation]`
  3. `check_midplane_clearance(design, min_gap_mm) -> list[Violation]`
  4. `check_turn_non_intersection(design) -> list[Violation]`
  5. `check_pole_angle_limit(design, max_angle_deg) -> list[Violation]`
- `check_feasibility(design, *, aperture_radius_mm, min_gap_mm, max_angle_deg, min_layer_clearance_mm=0.1) -> FeasibilityResult` that runs all five and aggregates.

For turn-to-turn intersection, implement a small self-contained
separating-axis-theorem (SAT) check for convex quadrilaterals rather than
adding `shapely` as a dependency, unless you have a strong reason to do
otherwise (state it if so).

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + all previously merged tests from tasks
  0001/0002 must still pass)
