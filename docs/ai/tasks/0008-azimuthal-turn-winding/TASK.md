# TASK: Azimuthal turn winding within a block (fix ROXIE parity)

- **ID**: 0008-azimuthal-turn-winding
- **Status**: draft
- **Model/effort**: Highest effort for both Codex and Antigravity. This
  changes a merged, foundational module (`src/dot/geometry/primitives.py`)
  that tasks 0003 (constraints), 0005 (optimizer), and 0006 (GUI) all
  build on. It is anchored to a real, verified discrepancy against actual
  ROXIE output, not a hypothetical improvement — treat the acceptance
  criteria's tolerance numbers as hard requirements, not suggestions.

## Background: the bug this fixes

The coordinator ran a parity check: built DOT's exact geometry from a real,
captured ROXIE run (`10042026_CTH-14T.data`/`.output` in
`C:\Users\elisei\Desktop\dipole_designer`, a 9-block/4-layer CTH-14T design,
zero iron elements, so a valid no-iron comparison) and compared DOT's native
`field_at`/`multipole_coefficients` output against ROXIE's real reported
values. Result: bore field off by 56-87%, harmonics off by up to 3 orders
of magnitude.

Root cause: `Block.turns()` currently stacks all `n_turns` of a block
**radially outward** at one fixed `phi`/`alpha` (each turn's radius =
`inner_radius_mm + index * cable.insulated_height_mm`). Real ROXIE blocks
(and real coils) wind multi-turn blocks **azimuthally at ~constant
radius** — each turn steps to a slightly different angular position at the
same nominal radius, not stacked outward behind each other. ROXIE's own
block table confirms this: it lists exactly ONE radius per block regardless
of how many turns (`nco`) that block has (e.g. a 24-turn block lists a
single `radius` value), which only makes sense if all 24 turns share that
one nominal radius.

## Goal

Change `Block.turns()` to generate turns by stepping azimuthally (in
`phi_deg`) at constant `inner_radius_mm` and `alpha_deg`, with the angular
step per turn derived from the cable's insulated width and the radius
(small-angle arc-length approximation: `delta_phi_rad ≈
cable.insulated_width_mm / inner_radius_mm`). Verify the fix directly
against the real ROXIE data below.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/primitives.py` — `Block.turns()` only; do not change
  `TurnPolygon`, `Layer`, or `DipoleDesign`.
- `tests/geometry/test_primitives.py` — update/add tests for the new
  azimuthal stepping behavior.
- `tests/physics/test_roxie_parity_cth14t.py` (new file) — the ROXIE
  parity regression test described below.
- If (and only if) existing tests in `tests/geometry/test_constraints.py`
  or `tests/optimize/*` fail because they hardcoded assumptions about the
  old radial-stacking layout (e.g. asserted exact turn coordinates that
  are now different), update only the specific assertions that encoded the
  old (now-incorrect) geometry — do not change the constraint-checking or
  optimizer *logic* itself, only test fixtures/expectations if needed.

## Explicit non-goals

- Do not change DOT's `phi_deg`/`alpha_deg` angular convention (documented
  in `primitives.py`'s module docstring: phi=0 at pole, phi=90 at
  midplane). ROXIE's own convention is the opposite (phi=0 at midplane,
  phi=90 at pole) — handle this via a conversion when constructing the
  parity test's input data (`phi_dot = 90.0 - phi_roxie`), not by changing
  DOT's internal convention.
- Do not touch `constraints.py`'s logic, `optimize/*`, or `gui/*` — they
  operate generically on turn polygons and should not need logic changes,
  only possibly test-fixture updates (see scope note above).
- Do not add cable keystoning (trapezoidal width_i/width_o) support —
  `CableSpec` stays rectangular; use the average of ROXIE's width_i/width_o
  for the parity test's cable dimensions (documented approximation).
- Do not attempt exact ROXIE agreement — real ROXIE modeling includes
  effects DOT deliberately doesn't replicate (keystoning, precise strand
  geometry). The acceptance tolerance below is deliberately not
  razor-tight; do not chase closer agreement than what's specified.

## ROXIE reference data (real, captured output — use exactly as given)

Cable specs derived from `roxie_CTH_cables.cadata`:
- `CTH_HF`: `width_mm = (1.53 + 1.658) / 2 = 1.594`, `height_mm = 18.363`, `insulation_thickness_mm = 0.145`
- `CTH_LF`: `width_mm = (1.736 + 2.084) / 2 = 1.91`, `height_mm = 16.17`, `insulation_thickness_mm = 0.145`

Operating current: `12238.0` A (same for every block/turn).

Block table (`no, n_turns, radius_mm, phi_roxie_deg, alpha_deg, cable`) —
convert `phi_roxie_deg` to DOT's convention via `phi_dot_deg = 90.0 -
phi_roxie_deg` before constructing `Block`s:

```
1   4  25.0     0.343771   0.0       CTH_HF
2   6  25.0    20.2269    23.4754    CTH_HF
3   3  25.0    48.7       46.4651    CTH_HF
4   2  25.0    66.5       65.9882    CTH_HF
5  13  44.153   0.194649   0.0       CTH_HF
6  14  44.153  33.9911    42.3351    CTH_HF
7  18  63.306   0.135759   0.0       CTH_LF
8   2  63.306  35.0656    35.0776    CTH_LF
9  24  80.269   0.10707    0.0       CTH_LF
```

Group into 4 layers by radius: layer 1 = blocks 1-4 (r=25.0, CTH_HF), layer
2 = blocks 5-6 (r=44.153, CTH_HF), layer 3 = blocks 7-8 (r=63.306, CTH_LF),
layer 4 = block 9 (r=80.269, CTH_LF).

ROXIE's real reported output for this exact geometry (reference radius
16.6667 mm):
- Main bore field: `14.005771` T (magnitude; ROXIE reports it negative by
  sign convention, compare magnitudes)
- Normal relative multipoles (1e-4 units): `b1=10000.0, b3=-1.14988,
  b5=1.55955, b7=1.86287, b9=0.70775, b11=1.26332, b13=0.15072`
- All skew multipoles ≈ 0 (pure normal dipole, as expected for this
  symmetric no-iron design)

## Turn-stacking direction (needs empirical confirmation)

Within a block, it is not 100% certain from the block table alone whether
successive turns step toward increasing or decreasing `phi_dot_deg`. Try
turns stepping toward **decreasing** `phi_dot_deg` (i.e. toward the pole in
DOT's convention, `phi -= delta_phi_deg` per turn index) first, since block
index order (1→9) moves from ROXIE's midplane-side low-phi to pole-side
high-phi, suggesting each block's turns extend further toward the pole as
turn-index increases. **If the parity test does not converge within
tolerance, try the opposite direction (`phi += delta_phi_deg`) before
concluding something else is wrong** — this is exactly what the parity
test is for. Report which direction worked and why in your summary.

## Acceptance criteria

- [ ] `Block.turns()`'s new azimuthal-stepping behavior has a direct unit
      test: for a hand-picked simple case (e.g. inner_radius=100mm,
      n_turns=3, known cable width), assert each turn's angular step
      matches `degrees(cable.insulated_width_mm / inner_radius_mm)` and all
      turns share the same radius (their inner-face midpoint distance from
      origin is equal within numerical tolerance) — this is the core
      behavior change, prove it directly, not just via the end-to-end
      parity test.
- [ ] **The ROXIE parity regression test** (`tests/physics/test_roxie_parity_cth14t.py`):
      build the exact 9-block/4-layer design from the reference data above,
      compute `field_at` at the bore center and `multipole_coefficients` at
      r_ref=16.6667mm, and assert:
      - Bore field magnitude within **5% relative** of 14.005771 T.
      - Each of b3, b5, b7, b9, b11, b13 within **2.0 units absolute** of
        ROXIE's reported value.
      - All skew coefficients (a1..a13) within 1.0 unit absolute of 0.
      This test must actually pass — do not weaken the tolerance to make a
      failing implementation pass; if it doesn't pass, the turn-generation
      fix is wrong and needs further correction, not a loosened test.
- [ ] `ruff check` clean; `pytest` passes (all new tests, plus all
      previously-merged tests either still pass unmodified or were updated
      per the narrow allowance in "Scope" above — list exactly which
      existing tests you touched and why, if any).
- [ ] No files outside declared scope modified.

## Notes / open questions

- If after correctly implementing azimuthal stepping (both directions
  tried) the parity test still doesn't converge within tolerance, stop and
  report the actual numbers achieved plus your best diagnosis, rather than
  forcing a pass — this would indicate a second, distinct issue worth the
  coordinator's attention (e.g. the phi-convention conversion formula, or
  the block-to-radius grouping) rather than silently shipping a still-wrong
  model.
