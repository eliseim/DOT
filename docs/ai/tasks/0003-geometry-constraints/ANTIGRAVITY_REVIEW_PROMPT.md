# Antigravity independent review prompt — TASK 0003-geometry-constraints

You are reviewing a diff produced by another AI worker (Codex) for the DOT
project's geometric feasibility checker. You did not see the worker's
reasoning — judge only the diff, the repository, and the task spec. The user
has explicitly emphasized that these constraints are safety-critical: a
false "feasible" verdict means DOT could report a physically unbuildable
magnet design as a valid answer.

## Inputs

- `docs/ai/tasks/0003-geometry-constraints/TASK.md`
- The diff/commit on branch `task/0003-geometry-constraints`.

## What to check

1. **Correctness of each of the 5 constraints**, individually:
   - Aperture clearance: does it actually catch a turn whose polygon
     crosses into the bore radius, including partial overlap (not just a
     turn fully inside the aperture)?
   - Inter-layer spacing: does it correctly compare layer *k*'s outer
     radial extent against layer *k+1*'s inner extent, or could it be
     fooled by a layer with non-monotonic block radii?
   - Midplane clearance: **independently recompute** the perpendicular
     distance from a representative turn polygon to y=0 for at least one
     test case and confirm it matches what the code asserts — this is a
     classic sign/trig-convention bug spot (e.g. confusing the cable's
     near-edge distance with its centroid distance).
   - Turn-to-turn non-intersection: trace through the SAT (or chosen
     algorithm) implementation for one concrete overlapping pair and one
     concrete non-overlapping-but-close pair by hand; confirm it doesn't
     produce false negatives on edge-touching (non-overlapping) polygons or
     false positives.
   - Pole-angle limit: confirm it checks the polygon's actual outer edge
     angle, not just the block's nominal start angle (which could differ
     once alpha tilt/cable width is applied).
2. **`FeasibilityResult`/`Violation` correctness**: does a violation
   correctly identify which layer/block/turn caused it? Could two
   violations get merged or misattributed?
3. **False negatives are worse than false positives here.** Actively try to
   construct (by reasoning, not necessarily running code) an input that
   would violate a constraint but slip through unflagged. Report any you
   find as high-severity.
4. **Scope discipline**: only `src/dot/geometry/constraints.py` and
   `tests/geometry/test_constraints.py` touched? No extra "helpful"
   constraints added beyond the 5 listed?
5. **Provenance**: no copying from `dipole_designer`'s `constraints.py` or
   `dipole-optimization-tool`'s geometry validation, no ROXIE dependency.
6. **Test quality**: two-directional (accepts valid + rejects invalid) for
   every constraint? Is the midplane test's expected value computed
   independently in the test rather than via the same formula as the
   implementation?

## Output format

Findings ranked most-severe first (missed-violation / false-negative bugs
first). For each: file, line, what's wrong, concrete failure scenario
(what invalid geometry would be reported as feasible). End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

A constraint checker that can be fooled into saying "feasible" for an
unbuildable magnet is a REJECT, not a nit.
