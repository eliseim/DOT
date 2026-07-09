# TASK: Coil cross-section feasibility constraints

- **ID**: 0003-geometry-constraints
- **Status**: draft
- **Model/effort**: High effort for both Codex and Antigravity. The user has
  explicitly flagged that geometric feasibility must work correctly, since
  an infeasible candidate (overlapping cables, cables outside the aperture,
  a design that cannot physically be wound) must never be reported as a
  usable result later by the optimizer/GUI. Keep the rule set itself
  minimal and focused — do not try to reproduce every edge case from the
  reference tools, just the physically essential ones.

## Goal

Given a `DipoleDesign` (from task 0002's `src/dot/geometry/primitives.py`),
determine whether the coil cross-section it describes is physically
buildable. Return a clear, structured list of violated constraints (not
just a boolean), so later tasks (optimizer, GUI) can report *why* a
candidate is infeasible.

Keep the constraint set focused on what's essential for a real, buildable,
no-iron dipole cross-section — do not attempt to reproduce every rule from
the reference tools. If in doubt about whether a rule is essential, prefer
leaving it out and noting it as a candidate for a later task over adding
speculative complexity now.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/constraints.py` — the feasibility checker.
- `tests/geometry/test_constraints.py`

## Constraints to implement (keep to this list — do not add more)

1. **Aperture clearance**: no turn polygon may intersect the circular
   aperture (bore) of the given aperture radius.
2. **Inter-layer radial separation**: layers must not radially overlap —
   layer *k+1*'s innermost turn must start at or beyond layer *k*'s
   outermost turn's radial extent (plus a minimum clearance, a parameter
   with a sensible default e.g. 0.1 mm).
3. **Midplane clearance**: no turn polygon may cross the horizontal midplane
   (y=0) inward of the required one-sided midplane gap (a parameter in mm).
4. **Turn-to-turn non-intersection**: no two turn polygons anywhere in the
   whole design may overlap (finite polygon intersection test, not just a
   bounding-radius heuristic).
5. **Pole-angle limit**: no turn's outer edge may exceed a configurable
   maximum angle from the y-axis (pole), representing the physical winding
   limit.

Each constraint is its own small, independently testable function. A single
`check_feasibility(design, params) -> FeasibilityResult` aggregates them,
where `FeasibilityResult` carries `is_feasible: bool` and a list of
structured violations (constraint name + human-readable message + offending
turn/block/layer identifiers).

## Explicit non-goals

- No wedge/spacer placement logic, no turn-density/topology search — that's
  optimizer territory (task 0005), not a feasibility check.
- No reproduction of the full C1–C19 rule set from `dipole_designer` — five
  focused constraints above are the entire scope of this task. If you
  believe an additional rule is essential for correctness (not just
  matching the reference tool), flag it in your summary for the coordinator
  instead of adding it unprompted.
- No optimizer, no GUI, no conductor/critical-current logic.
- No ROXIE code or fixtures.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\core\constraints.py`
  — read for the *definitions* of aperture clearance, midplane gap
  (including the `asin` vs `atan` subtlety for an alpha-zero midplane
  cable — note this if relevant to your test cases), inter-layer spacing,
  and pole-angle limit. Do not copy code; the implementation here operates
  on DOT's own `TurnPolygon`/`Layer`/`DipoleDesign` types from task 0002,
  which have a different shape.
- `C:\Users\elisei\Desktop\dipole-optimization-tool\src\dipole_opt\domain\geometry_validation.py`
  and `turn_intersection.py`-equivalent (if present) — read for the polygon
  intersection test approach (turn-to-turn non-overlap). Do not copy.

## Acceptance criteria

- [ ] Each of the 5 constraints has at least one test proving it correctly
      flags a violating design and at least one test proving it accepts a
      valid design (both directions tested, not just the happy path).
- [ ] The midplane-gap check is tested against a hand-computed geometric
      case (a cable at a known polar radius and angle where the perpendicular
      distance to y=0 is independently computed in the test, not derived
      from the same formula as the implementation).
- [ ] Turn-to-turn non-intersection is tested with an actual overlapping
      polygon pair (not just adjacent/touching), using a real 2D polygon
      intersection test (e.g. separating-axis theorem or equivalent) —
      state which algorithm was used and why it's correct for convex
      quadrilaterals.
- [ ] `check_feasibility` on a fully valid hand-constructed `DipoleDesign`
      (built via task 0002's primitives) returns `is_feasible=True` with an
      empty violation list.
- [ ] `check_feasibility` on the same design with one turn deliberately
      pushed into an overlap/aperture/midplane/pole-angle violation returns
      `is_feasible=False` with a violation identifying the correct
      constraint and the correct offending turn/block/layer.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken; no
      files outside declared scope modified.

## Notes / open questions

- Whether to use `shapely` for polygon intersection is a judgment call —
  `shapely` is a real dependency addition (native binary wheel). Prefer a
  small self-contained polygon-overlap routine (SAT for convex quads is
  ~30 lines) over adding a new heavy dependency for this one check, unless
  Codex judges it clearly better; state the choice and why in the summary.
