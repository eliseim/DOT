# Codex worker prompt — TASK 0008-azimuthal-turn-winding

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0008-azimuthal-turn-winding/TASK.md` in this worktree fully
before writing any code. This fixes a real, measured discrepancy against
actual ROXIE output found by the coordinator — the task spec contains all
the reference data you need. Do not re-derive it from scratch; use the
numbers given exactly as specified.

## Hard rules

1. Only touch `src/dot/geometry/primitives.py`'s `Block.turns()`, plus the
   test files listed in TASK.md's scope. Do not change `TurnPolygon`,
   `Layer`, `DipoleDesign`, `constraints.py` logic, `optimize/*` logic, or
   `gui/*`.
2. Do not change DOT's phi/alpha angular convention — only the parity
   test's input construction converts ROXIE's phi to DOT's convention, as
   specified in TASK.md.
3. The ROXIE parity test's tolerances (5% on field, 2.0 units on each
   harmonic, 1.0 unit on skew terms) are hard requirements. Do not loosen
   them to make a wrong implementation pass — if it doesn't converge, try
   the alternate winding direction described in TASK.md, and if it still
   doesn't converge, stop and report the actual numbers plus your
   diagnosis instead of forcing a pass.
4. If existing tests break due to the geometry change, only update the
   specific assertions that hardcoded the old (now-incorrect) radial-stack
   layout — do not weaken or remove tests that are still testing something
   real and correct.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact
turn-stepping formula implemented, which winding direction worked (and
whether you had to try both), the actual field/harmonic values your
implementation produces for the ROXIE parity case versus the reference
values, and full test output.

## Task-specific instructions

1. In `src/dot/geometry/primitives.py`, change `Block.turns()`: instead of
   incrementing `inner_radius_mm` per turn index, keep `inner_radius_mm`
   fixed for all turns in the block and instead step `phi_deg` per turn
   index by `delta_phi_deg = math.degrees(cable.insulated_width_mm /
   inner_radius_mm)`. Try `phi -= index * delta_phi_deg` first (per
   TASK.md's reasoning); if the parity test doesn't converge, try `phi +=
   index * delta_phi_deg` instead.
2. Add the direct unit test for the new stepping behavior in
   `tests/geometry/test_primitives.py` (see TASK.md's first acceptance
   criterion).
3. Add `tests/physics/test_roxie_parity_cth14t.py` using the exact block
   table, cable specs, and reference values given in TASK.md. Build the
   `DipoleDesign`, compute `field_at` and `multipole_coefficients` (reuse
   `place_line_current_sources` for discretization — use `n1=2, n2=20` for
   `CTH_HF` blocks and `n1=2, n2=15` for `CTH_LF` blocks, matching ROXIE's
   own discretization density from the block table), and assert the
   tolerances from TASK.md.
4. Run the existing full test suite. If anything in
   `tests/geometry/test_constraints.py` or `tests/optimize/*` fails because
   it hardcoded old radial-stacking geometry, fix only that specific
   assertion (document which and why in your summary) — do not touch
   `constraints.py` or `optimize/*` source logic.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite — report pass count, and explicitly confirm the
  new ROXIE parity test is among the passing tests)
