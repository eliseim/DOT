# TASK: Keystone-tilt / arc-projection fix for multi-turn block stacking

- **ID**: 0019-keystone-tilt-multiturn-stacking
- **Status**: draft
- **Model/effort**: Highest effort. This modifies `Block.turns()` in
  `src/dot/geometry/primitives.py` — the same core stacking logic
  twice-validated in tasks 0015 and 0017. Same rigor bar: independent
  derivation, live ROXIE re-validation, visual comparison against ROXIE's
  own conductor corner coordinates, and this task specifically requires a
  **fresh** independent review cycle (do not treat the earlier 0015/0017
  approvals as covering this change).

## Background

Task 0018 (peak-field-on-conductor / load-line-margin parity, merged) fixed
the near-field evaluation to sample on bare conductor geometry instead of
insulated geometry, closing single-turn-block peak-field error from
3.5-4.4% down to <0.5% (verified live against ROXIE by both Codex and an
independent Antigravity review).

During that review, Antigravity ran one case beyond what task 0018 required
— a block with `n_turns = 2` — specifically to check the fix generalizes.
It found peak-field error jumps to **9.25%** (margin error 2.86 pp) for
multi-turn blocks, and root-caused it to a real, separate geometry bug,
independent of task 0018's fix. Full derivation is in
`docs/ai/tasks/0018-peak-field-and-loadline-margin-parity/` review history;
summarized below.

### What was found (verbatim from the independent review)

Test case: `cth_lf_custom_two_turns_block` — CTH_LF cable, `radius=35mm`,
`phi_deg=35`, `alpha_deg=0`, `n_turns=2`, single block/layer.

**Extracted real ROXIE conductor corners** (from that run's `post.xml`):

- Conductor 1 (Turn 0): inner midplane-side corner `(20.219, 28.815)` mm,
  inner pole-side corner `(20.200, 30.551)` mm. Height axis parallel to the
  global x-axis (i.e. matches DOT's alpha=0 convention for turn 0).
- Conductor 2 (Turn 1): inner midplane-side corner `(17.083, 30.774)` mm,
  inner pole-side corner `(17.027, 32.509)` mm. **Height axis tilted by
  1.233 deg relative to Conductor 1** — the cable's own keystone
  (wedge) angle. Angular spacing from Conductor 1 to Conductor 2 is
  **6.027 deg**.

**DOT's current output for the same design:**

- Turn 0: matches ROXIE's Conductor 1 (after accounting for the
  insulation-vs-bare offset already handled correctly).
- Turn 1: height axis stays at 0 deg tilt (DOT keeps every turn in a block
  at the block's single fixed `alpha_deg`, per task 0015's absolute-alpha
  convention). Angular spacing from Turn 0 to Turn 1 is only **3.316 deg**
  — computed via `Block.turns()`'s "simple" branch,
  `delta_phi_deg = degrees(cable.insulated_width_inner_mm /
  inner_radius_mm)` (`src/dot/geometry/primitives.py:135`).

**Diagnosis:** a cable's width offset, when the block's turns wind around a
circle, must be projected onto the true local arc-tangent direction to get
the correct angular step. `Block.turns()`'s simple-branch formula
(`width / radius`) is only exact when the offset direction is already
tangent to the circle — true only at `phi=90 deg` (midplane) for
`alpha=0`. At `phi=35 deg`, the fixed global `width_axis` from `alpha=0`
departs from the true local tangent by roughly 55 deg, so the correct
angular footprint of one cable width is `width / (radius * cos(gamma))`
for the relevant projection angle `gamma`, not `width / radius` — a factor
of ~1.75x here (`3.316 deg` measured vs. `5.78 deg`/`6.027 deg`
ROXIE-observed). The resulting **1.66mm inward shift** of Turn 1 causes the
bare conductors to physically overlap in DOT's model, which is what
produces the spurious near-field peak (9.25% error) — a real geometric
defect, not just a near-field-evaluation artifact.

Separately, ROXIE also **tilts** each subsequent turn's own orientation by
the cumulative keystone angle (1.233 deg for turn 1 here) so that adjacent
keystoned (trapezoidal) turns nest flush against each other, like voussoirs
in an arch. DOT currently keeps every turn in a block at the same single
`alpha_deg` (task 0015's absolute-alpha convention, which was independently
validated to <0.5% for the *far-field* on the full 86-turn CTH-14T design —
so this simplification is a good aggregate approximation for bore field,
but is geometrically wrong turn-by-turn, which only becomes visible in a
near-field/self-field or overlap check).

### Why this wasn't caught by tasks 0015/0017/0018's own validation

- Tasks 0015/0017 validated **bore field**, evaluated far from every
  source — a few tenths-of-a-percent mm-scale per-turn positioning error
  washes out in that far-field superposition.
- Task 0018's own required acceptance cases were all `n_turns=1`
  (single-turn blocks have no stacking at all, so this bug is invisible to
  them). Antigravity's reviewer added the multi-turn case on its own
  initiative specifically to check generalization, per its review
  instructions, and found this.
- The original 200-case field-parity sweep
  (`C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\pipeline.py`) kept
  `n_turns` to 1-2 and reported 100% within 2% on **bore field** — that
  result stands (this bug affects near-field peak/margin accuracy, not
  bore-field accuracy, consistent with the mechanism above).

## Goal

1. Fix `Block.turns()` in `src/dot/geometry/primitives.py` so that
   multi-turn blocks' azimuthal stacking matches ROXIE's real conductor
   placement — both the angular *spacing* (correct arc-tangent projection
   of the cable width, not the current `width/radius` approximation) and,
   if required to hit tolerance, the per-turn *tilt* (whether DOT needs to
   rotate each subsequent turn's own `alpha` by the cumulative keystone
   angle to match ROXIE, or whether a spacing-only fix is sufficient —
   determine this empirically, don't assume).
2. This applies to **both** code paths in `Block.turns()`: the "simple"
   branch (`delta_phi_deg` stepping) and the `_arc_stacked_anchor` fallback
   branch — check both, the projection error likely exists in both since
   they share the same width-axis-offset assumption.
3. Independently re-derive the correct projection formula by hand before
   writing code — show the derivation (angle between global width_axis and
   local arc tangent as a function of `phi_deg` and `alpha_deg`, and how it
   changes the effective angular step) in your summary.
4. **No regression on bore-field parity.** This is the single most
   important constraint: tasks 0015/0017's bore-field results (200/200
   within 2%, CTH-14T real design at 0.456%) and task 0018's single-turn
   peak-field/margin results (<0.5%/<0.15pp) must not regress. Re-run all
   of them live against ROXIE after your fix.
5. Live-validate the specific failing case
   (`cth_lf_custom_two_turns_block`: CTH_LF, `radius=35mm`, `phi_deg=35`,
   `alpha_deg=0`, `n_turns=2`) and at least one additional multi-turn case
   with different radius/phi, both peak-field and margin, against live
   ROXIE.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/primitives.py`
- `tests/geometry/test_primitives.py`
- `tests/physics/test_roxie_parity_live.py`,
  `tests/physics/test_roxie_parity_cth14t.py` (only to add new multi-turn
  coverage or re-confirm existing cases still pass — do not weaken or
  remove any existing assertion)
- `tests/optimize/test_objectives.py` (only if margin-objective test
  fixtures need updating for corrected turn geometry)

## Explicit non-goals

- No change to `src/dot/optimize/objectives.py` (task 0018's fix, already
  merged and validated — this task is purely about turn geometry).
- No change to `TurnPolygon.from_anchor`'s trapezoid corner construction
  itself (task 0017) unless the investigation proves it's implicated —
  if so, stop and report back rather than modifying it without a
  dedicated review cycle for that specific change.
- Do not weaken any existing tolerance to force a pass, per binding
  precedent from tasks 0008, 0015, 0017, 0018.

## Acceptance criteria

- [ ] Hand-derivation shown in the summary: the correct arc-tangent
      projection formula for a cable-width angular step, as a function of
      `phi_deg` and `alpha_deg`, and how it compares numerically to the
      current `width/radius` formula for the failing case (`3.316 deg`
      current vs. ROXIE's observed `~5.78-6.027 deg`).
- [ ] **Live ROXIE re-validation** of `cth_lf_custom_two_turns_block`
      (peak field AND margin) — must reach the standing 2% / 2 percentage
      point bar. Report the honest number if not achieved.
- [ ] Live ROXIE re-validation of at least one additional multi-turn case
      at a different radius/phi.
- [ ] **No regression**: re-run live against ROXIE — the CTH-14T real
      design case, at least one of the original single-block task
      0015/0017 cases, and at least one of task 0018's single-turn cases.
      All must remain within their previously-achieved tolerances.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\core\geometry_helpers.py`
  — already used as reference for tasks 0015/0017's trapezoid and axis
  formulas; re-read specifically for how it handles per-turn stacking
  around an arc for multi-turn blocks (the tilt/nesting behavior), since
  that's the part not yet mined from this reference.
- ROXIE `.data`/`.output`/`post.xml` files and diagnostic scripts already
  gathered at `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\` — in
  particular whatever Antigravity's review session used to extract the
  `cth_lf_custom_two_turns_block` conductor coordinates (check
  `margin_out/` and any `*.post.xml` there first before regenerating).
- `roxieapi` REST service is live at `http://127.0.0.1:8080`; system Python
  has `roxieapi` installed (`python -c "import roxieapi"` to confirm).
