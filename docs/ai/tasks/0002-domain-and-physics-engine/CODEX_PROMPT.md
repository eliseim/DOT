# Codex worker prompt — TASK 0002-domain-and-physics-engine

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0002-domain-and-physics-engine/TASK.md` in this worktree fully
before writing any code. This is DOT's physics core — take it seriously,
prove correctness with tests against closed-form analytic physics, not just
"the code runs without error".

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. You may *read* the reference files listed in TASK.md for the physics
   method and conventions. Do not copy code verbatim — re-derive and
   re-implement independently. If you disagree with the reference
   implementation's approach on any point, say so explicitly in your final
   summary instead of silently picking one.
3. No ROXIE dependency, no ROXIE file formats, no ROXIE fixtures used as
   test oracles. All physics tests must be validated against closed-form
   analytic formulas computed independently inside the test (e.g. infinite
   wire Biot-Savart law, hand-derivable symmetric dipole field), never by
   asserting the code agrees with itself.
4. No feasibility/constraint checking, no optimizer, no GUI — this task is
   geometry primitives (turn/block/layer construction) + Biot-Savart field
   + analytic multipole extraction only.
5. Use consistent units throughout (millimeters for geometry, tesla for
   field, amperes for current) and document the convention once, explicitly,
   at the top of `physics/field.py`.
6. Write the tests specified in TASK.md's acceptance criteria yourself, run
   `pytest` and `ruff check`, and report actual output — do not claim a test
   passes without having run it.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the discretization
approach chosen (n1/n2 defaults and why), the mirror-symmetry construction
and why it's correct for a 2D no-iron dipole, the multipole convention/
normalization used, and full test output (`pytest -q`, `ruff check .`). If
you found and fixed a suspected bug in the reference tool's approach while
re-deriving the physics, call it out explicitly — this is valuable
information, not scope creep.

## Task-specific instructions

Implement exactly what `docs/ai/tasks/0002-domain-and-physics-engine/TASK.md`
describes, file by file, in this order (each layer depends on the previous):

1. `src/dot/geometry/cable.py` — `CableSpec` dataclass: `width_mm: float`,
   `height_mm: float`, `insulation_thickness_mm: float`.
2. `src/dot/geometry/primitives.py`:
   - `TurnPolygon`: the 4 corner points (x, y) in mm of one turn's
     cross-section, plus the current it carries (A). Corners should be
     computed from: inner radius of the turn, angular position `phi` (deg,
     measured from the y-axis toward the pole per standard ROXIE-style
     convention — pick one, document it), block tilt `alpha` (deg), and the
     cable's width/height (accounting for insulation).
   - `Block`: given a starting `phi`, `alpha`, number of turns, cable spec,
     and starting radius, generate the list of `TurnPolygon`s stepping
     radially or azimuthally as turns are added (pick and document a single
     simple stacking rule — e.g. turns stack radially outward within a
     block at fixed `phi`/`alpha`, matching a simple single "pancake"
     block; this can be refined in a later task, keep it simple and
     correct here).
   - `Layer`: a list of `Block`s at a given inner radius.
   - `DipoleDesign`: aperture radius + list of `Layer`s; a method to flatten
     into a single list of all `TurnPolygon`s across the whole design.
3. `src/dot/physics/sources.py` — `place_line_current_sources(turn: TurnPolygon, n1: int, n2: int) -> list[LineCurrentSource]` (or similar), bilinearly distributing `n1 x n2` equal-current sub-filaments across the turn's quadrilateral, each carrying `turn.current / (n1*n2)`.
4. `src/dot/physics/field.py` — `field_at(sources, x, y) -> (Bx, By)` using
   `mu0/(2*pi) * I / rho` per source (2D infinite-wire Biot-Savart law),
   with the documented mirror-image construction for dipole symmetry (state
   explicitly: does the source list already contain all four
   quadrant-images, or does `field_at` generate them internally? Pick one
   and be consistent/tested).
5. `src/dot/physics/multipoles.py` — `multipole_coefficients(sources, order, r_ref_mm) -> (b_n, a_n)` using the closed-form per-source multipole formula (complex expansion of `1/z` around the reference radius), normalized to the CERN/European relative-multipole convention (units of 1e-4 of the main field at `r_ref`).

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + existing task-0001 smoke test)
