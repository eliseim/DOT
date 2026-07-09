# TASK: Coil geometry primitives + native (ROXIE-free) electromagnetic engine

- **ID**: 0002-domain-and-physics-engine
- **Status**: draft
- **Model/effort**: High effort for both Codex and Antigravity. This is
  DOT's core physics — a wrong Biot-Savart implementation or a wrong
  multipole convention silently produces a "feasible" design that is
  physically nonsense. Correctness here must be proven with tests against
  known analytic solutions, not just "it runs".
- **Worktree**: .worktrees/0002-domain-and-physics-engine (branch task/0002-domain-and-physics-engine)

## Goal

Give DOT a self-contained, ROXIE-free way to compute the 2D magnetic field
and multipole harmonics produced by a superconducting dipole coil
cross-section, given its geometry and operating current. This is the engine
that later tasks (geometry constraints, optimizer, GUI) will build on.

Physical setup: a 2D (infinitely long in z) no-iron dipole magnet. The coil
cross-section is built from **layers**, each layer built from **blocks** of
turns, each **turn** a small polygon (roughly rectangular cross-section of
one cable) carrying a current. Field is computed at any point in the 2D
plane by superposing the Biot-Savart contribution of every turn, discretized
into line-current sources. Multipole (harmonic) coefficients are computed
analytically from those same line-current sources (no field sampling/curve
fitting needed for the ideal-current-source case).

## Scope (files/modules Codex may touch)

- `src/dot/geometry/__init__.py`
- `src/dot/geometry/primitives.py` — plain data model: `TurnPolygon` (its 4
  corner points), `Block` (list of turns generated from block parameters:
  starting angle `phi`, tilt `alpha`, number of turns, cable width/height,
  inner radius), `Layer` (list of blocks, inner radius), `DipoleDesign`
  (list of layers + aperture radius). Pure geometry construction — given
  block parameters, produce turn polygons. **No feasibility/overlap
  checking** — that is task 0003, explicitly out of scope here.
- `src/dot/geometry/cable.py` — a minimal `CableSpec` dataclass: width_mm,
  height_mm, insulation_thickness_mm. Nothing about critical current /
  load-line yet (later task).
- `src/dot/physics/__init__.py`
- `src/dot/physics/sources.py` — discretize each `TurnPolygon` into a grid
  of line-current sources (position + current per source), given the turn's
  total current and a discretization density (e.g. n1 x n2 sub-filaments).
- `src/dot/physics/field.py` — 2D Biot-Savart field `(Bx, By)` at an
  arbitrary point from a set of line-current sources, exploiting the
  up-down and left-right mirror symmetry of an ideal 2D dipole (four mirror
  images per physical source: the source itself plus its reflections needed
  to enforce dipole symmetry — document the symmetry assumption explicitly
  in a docstring and make it a named, testable function, not folded
  silently into source generation).
- `src/dot/physics/multipoles.py` — analytic multipole (harmonic)
  coefficients from a set of line-current sources at a given reference
  radius, in the normal CERN/European relative-multipole convention (units
  of 1e-4 at the reference radius), separating normal (`b_n`) and skew
  (`a_n`) components.
- `tests/geometry/test_primitives.py`
- `tests/physics/test_sources.py`
- `tests/physics/test_field.py`
- `tests/physics/test_multipoles.py`

## Explicit non-goals

- No feasibility/overlap/spacing constraints (task 0003).
- No optimizer, no genome/decoder (task 0004).
- No GUI (task 0005).
- No ROXIE code, no ROXIE file formats, no dependency on ROXIE output for
  correctness — tests must validate against **closed-form analytic physics**
  (e.g. field of a single infinite straight wire at a known distance;
  multipole coefficients of a symmetric, hand-computable source
  arrangement), not against any ROXIE fixture.
- No `.cadata`/conductor-catalogue file parsing yet — `CableSpec` here is
  just geometry (width/height/insulation), not electrical properties.
- No GUI-facing units conversion layer — use SI-consistent units internally
  (millimeters for geometry, tesla for field, amperes for current, and
  document the convention once at the top of `physics/field.py`) and be
  consistent everywhere.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole-optimization-tool\src\dipole_opt\electromagnetics\sources.py`,
  `field.py`, `multipoles.py` — an existing (reasonably mature, tested)
  implementation of exactly this: line-current discretization, Biot-Savart
  with mirror symmetry, analytic multipole expansion. Study the *method*
  (Biot-Savart superposition, mirror-image symmetry trick, multipole
  convention/normalization) and the physics, but do not copy the code
  verbatim — DOT's implementation, naming, and structure must be
  independently written and independently testable. If you find their
  approach correct, re-derive and re-implement it in your own words/code;
  if you find a bug in their approach, do not carry it over.
- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\core\geometry.py`
  — for the general idea of how block/turn geometry (phi, alpha, corner
  points) is parameterized in this domain. Do not copy.

## Acceptance criteria

- [ ] `Layer`/`Block`/`TurnPolygon` construction from simple parameters
      (aperture radius, layer radial position, block start angle, tilt,
      turn count, cable width/height) produces the expected number of turns
      with plausible, non-overlapping-looking corner coordinates for at
      least one hand-checked example (assert exact or near-exact expected
      corner coordinates for a simple single-turn case computed by hand in
      the test).
- [ ] Field of a single straight infinite wire carrying current `I` at
      perpendicular distance `d`: test asserts computed `|B|` matches
      `mu0*I/(2*pi*d)` to within a tight numerical tolerance (e.g. 1e-6
      relative), for at least 3 different distances/currents.
- [ ] Field at the exact center of a symmetric arrangement of sources
      representing an idealized dipole (e.g. two infinite wires placed
      symmetrically above/below the midplane carrying opposite-sign
      current) matches the hand-derivable closed-form value.
- [ ] Multipole extraction: for a source arrangement with a known pure
      dipole field (test case above), the extracted `b_1` (dipole term)
      matches the expected value and all higher-order normal/skew terms
      (`b_2`, `a_1`, `a_2`, ...) are ~0 (within numerical tolerance).
      For a deliberately constructed asymmetric source arrangement,
      extracted higher harmonics must be nonzero and match a hand/np-
      computed reference value (compute the expected value independently in
      the test using the same closed-form multipole formula, not by calling
      the code under test).
- [ ] Mirror-symmetry assumption is documented and has its own unit test
      showing that a single source plus its 3 required mirror images
      reproduces correct up-down/left-right antisymmetric dipole field
      behavior (`Bx`, `By` sign flips verified at mirrored points).
- [ ] `ruff check` clean on changed files.
- [ ] `pytest` passes, all new tests green, no existing tests broken.
- [ ] No files outside declared scope were modified.

## Notes / open questions

- Discretization density (`n1`, `n2` sub-filaments per turn) is a tunable
  parameter — Codex should pick a sensible default (e.g. n1=n2=3 or similar,
  matching the order of magnitude used in the reference tool) and expose it
  as a function argument, not a hardcoded magic number buried in logic.
- If Codex's re-derivation of the multipole convention disagrees with the
  reference tool's, that disagreement itself should be surfaced clearly in
  the task summary for coordinator/Antigravity attention — don't silently
  pick one.
