# Antigravity independent review prompt — TASK 0008-azimuthal-turn-winding

You are reviewing a diff produced by another AI worker (Codex) for a fix to
DOT's core geometry module (`src/dot/geometry/primitives.py`), anchored to
a real, measured discrepancy against actual ROXIE output. You did not see
the worker's reasoning — judge only the diff, the repository, and the task
spec. This is the highest-stakes review yet: it changes a module that
tasks 0003, 0005, and 0006 all already depend on.

## Inputs

- `docs/ai/tasks/0008-azimuthal-turn-winding/TASK.md` — contains the exact
  reference ROXIE data (block table, cable specs, expected field/harmonic
  values) this fix must reproduce within stated tolerance.
- The diff/commit on branch `task/0008-azimuthal-turn-winding`.

## What to check — be skeptical, this claims to fix a real measured bug

1. **Re-derive the parity numbers yourself, independently, if at all
   feasible** (or at minimum re-run the new `test_roxie_parity_cth14t.py`
   test and inspect its actual printed/asserted values) — do not just
   trust that "tests pass" means the fix is real. A test author under
   pressure to make a hard test pass could subtly loosen a tolerance, hardcode
   an expected value that matches the implementation rather than the true
   ROXIE reference, or construct the test in a way that doesn't actually
   exercise the fixed code path. Check the test's expected values (14.005771 T,
   b3=-1.14988, b5=1.55955, b7=1.86287, b9=0.70775, b11=1.26332, b13=0.15072)
   match TASK.md's stated reference exactly, character for character — a
   transposed digit here would silently validate against the wrong number.
2. **Turn-stepping formula correctness.** Confirm `Block.turns()` now
   holds `inner_radius_mm` constant across all turns in a block (not
   incrementing it) and steps `phi_deg` by `degrees(cable.insulated_width_mm
   / inner_radius_mm)` per turn. Check the `delta_phi_deg` computation uses
   the correct cable width (not height, not a hardcoded value) and the
   correct block's own inner_radius_mm (not, e.g., accidentally the
   aperture radius or a different layer's radius).
3. **No regression to task 0002/0003's other invariants.** Do other turns'
   corner-construction logic (`TurnPolygon.from_parameters`) remain
   unchanged? Does `Layer`/`DipoleDesign` construction remain unchanged?
   Confirm the diff is actually scoped to `Block.turns()` as the task
   demanded, not a broader rewrite.
4. **Scope discipline on test-fixture updates.** If any existing test in
   `test_constraints.py` or `optimize/*` was modified, check that only
   assertions encoding the *old, now-incorrect* geometry were touched —
   flag if any test's actual pass/fail *logic* (not just expected
   coordinate values) was weakened to force a pass.
5. **Tolerance honesty.** Confirm the parity test's assertions use exactly
   the tolerances TASK.md specified (5% relative on field, 2.0 units
   absolute per harmonic, 1.0 unit absolute on skew) — not loosened
   tolerances chosen after the fact to make a still-imperfect
   implementation pass.
6. **Provenance/scope.** Only `src/dot/geometry/primitives.py` and the
   listed test files touched? No changes to `constraints.py` or
   `optimize/*` logic (only possibly their test fixtures, per the narrow
   allowance)?

## Output format

Findings ranked most-severe first — a hardcoded-to-pass test or a wrong
reference number transcription is the most severe class here, since it
would make the whole codebase falsely believe it has ROXIE parity. For
each: file, line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on "the test passes" without independently confirming
the test's reference numbers and tolerances are the real, unweakened ones
from TASK.md.
