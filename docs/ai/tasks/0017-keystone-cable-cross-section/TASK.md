# TASK: Keystoned (trapezoid) cable cross-section

- **ID**: 0017-keystone-cable-cross-section
- **Status**: draft
- **Model/effort**: Highest effort. This touches the core geometry model
  again (`TurnPolygon`) — same rigor bar as task 0015: independent
  derivation, live ROXIE re-validation, visual comparison.

## Background

After task 0015's fix (absolute alpha + arc stacking), live ROXIE
validation of the two originally-targeted cases succeeded (CTH-14T 1.26%,
one alpha=0 single-block case 1.53% — both under 2%). Continuing to debug
per explicit instruction to reach 2% generally (not just for those two
cases), the coordinator tested new single-turn cases (no stacking
involved at all, ruling out the stacking formula) at different
radius/phi values and found a consistent **2.1-3.4% error**, e.g.:

```
r=35.0 phi=40.0: DOT=5.0000 ROXIE=4.8478 diff=3.140%
r=40.0 phi=30.0: DOT=5.0000 ROXIE=4.8365 diff=3.381%
r=45.0 phi=50.0: DOT=5.0000 ROXIE=4.8983 diff=2.076%
```

Since stacking is not involved (`n_turns=1`), this points at the basic
single-turn cross-section model. `CableSpec` currently uses one averaged
`width_mm` for a cable that is actually **keystoned** (trapezoidal) — real
`.cadata` data has independent inner and outer widths, e.g. CTH_HF:
`width_inner=1.53mm, width_outer=1.658mm` (an 8.4% taper), and DOT
currently averages these into a single flat-rectangle width. Real ROXIE
(and `dipole_designer`'s independently-validated reference,
`geometry_helpers.py`) model the cable cross-section as a trapezoid with
independent inner/outer widths. This averaging is the most likely
remaining cause of the residual error.

**Also found in the same investigation** (separate, smaller bug, same
file): `src/dot/gui/target_synthesis_gui.py::_cable_spec_from_cadata_text`
hardcodes `insulation_thickness_mm=0.0` — it never reads the `.cadata`
file's `INSUL` section at all. Fix this in the same pass since it's the
same function being touched.

## Goal

1. Extend `CableSpec` to carry independent inner/outer cable widths
   (keystone), and independent radial/azimuthal insulation thickness (the
   real `.cadata` `INSUL` table already has these as two separate values
   per the CTH conductors' `INSXF145`/`ALLPOLYIL` records, both 0.145mm
   for CTH but not necessarily equal in general — check whether they're
   ever unequal in the reference file and support both being unequal).
2. Change `TurnPolygon.from_parameters`/`from_anchor` to build a proper
   trapezoid (independent inner-face and outer-face half-widths) instead
   of a uniform rectangle.
3. Change `Block.turns()`'s stacking formulas (both the simple-arc branch
   and the `_arc_stacked_anchor` fallback) to use the cable's **inner**
   insulated width specifically for the width-offset step (matching the
   already-validated reference convention), not an averaged width.
4. Fix `_cable_spec_from_cadata_text` in the GUI to read the actual
   `INSUL` section for insulation thickness instead of hardcoding 0.0, and
   to pass the real inner/outer widths through instead of averaging.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/cable.py`
- `src/dot/geometry/primitives.py`
- `src/dot/gui/target_synthesis_gui.py` (only `_cable_spec_from_cadata_text`
  and its direct call sites — do not touch unrelated GUI code)
- `tests/geometry/test_primitives.py`
- `tests/gui/test_target_synthesis_gui.py`
- `tests/physics/test_roxie_parity_cth14t.py`, `tests/physics/test_roxie_parity_live.py`
  — update cable construction to use real inner/outer widths (CTH_HF:
  1.53/1.658mm; CTH_LF: 1.736/2.084mm, both +0.145mm insulation each side)
  instead of the averaged value, and add new live-ROXIE coverage for the
  specific single-turn cases that exposed this gap (see acceptance
  criteria).

## Explicit non-goals

- No change to the already-validated absolute-alpha or arc-stacking logic
  from task 0015 — only the cross-section shape and the stacking step's
  width value change.
- No change to `CableRecord` (task 0004's critical-current module) — this
  is purely about geometric cross-section shape, unrelated to Jc/Ic.

## Acceptance criteria

- [ ] `CableSpec` (or a new type) carries independent inner/outer widths;
      existing single-width call sites are updated, not left broken.
- [ ] Direct unit test: a trapezoid turn's four corners are NOT a
      rectangle when `width_inner_mm != width_outer_mm` — assert the
      actual corner coordinates for a hand-picked case.
- [ ] **Live ROXIE re-validation** of the exact 3 single-turn cases that
      exposed this gap (r=35/phi=40, r=40/phi=30, r=45/phi=50, CTH_HF
      cable, `alpha=0`, `n_turns=1`, scaled to 5T) — all three must be
      under 2%. Report the actual numbers; do not weaken this to force a
      pass.
- [ ] Live ROXIE re-validation that the two already-passing task-0015
      cases (CTH-14T real design, the original alpha=0 6-turn single-block
      case) **remain** under 2% after this change (regression check).
- [ ] `_cable_spec_from_cadata_text` now reads real insulation thickness
      from the `.cadata` file's `INSUL` section (test with the real
      `roxie_CTH_cables.cadata` file's `INSXF145`/`ALLPOLYIL` records,
      expecting 0.145mm) instead of hardcoding 0.0.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\core\geometry_helpers.py`
  — `_turn_polygon_corners_mm`'s trapezoid construction
  (`cable.width_inner_insulated_mm`, `cable.width_outer_insulated_mm`),
  already used correctly for task 0015's axis formulas. Read for
  understanding, do not copy.
- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — real
  `CABLE` and `INSUL` table entries for `CXF150HT5` (CTH_HF) and
  `CTH_CERN` (CTH_LF).
