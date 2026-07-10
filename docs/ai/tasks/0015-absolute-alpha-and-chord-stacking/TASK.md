# TASK: Fix turn geometry — absolute (phi-independent) alpha + straight-chord turn stacking

- **ID**: 0015-absolute-alpha-and-chord-stacking
- **Status**: draft
- **Model/effort**: Highest effort for both Codex and Antigravity. This
  fixes a major, verified bug in `src/dot/geometry/primitives.py`
  (`TurnPolygon.from_parameters`, `Block.turns()`) — foundational,
  already-merged geometry code used by every downstream module
  (constraints, optimizer, GUI). The bug causes tens-of-percent field
  errors for blocks with non-trivial `alpha`. This must be fixed with the
  same rigor as tasks 0002/0008 (independent hand-derivation, live ROXIE
  re-validation), not just "tests pass."

## Background — how this was found and verified

Investigating a ~13-21% DOT-vs-ROXIE field discrepancy (with the ROXIE
Docker REST service now live at `http://127.0.0.1:8080`), a research pass
over `dipole_designer`'s own reverse-engineered geometry code
(`dipole_optimizer/core/geometry_helpers.py`, specifically
`_alpha_height_vector_mm`, `_width_axis_vector_mm`, `_turn_polygon_corners_mm`)
revealed that code's docstrings document an **empirical finding against
real ROXIE `post.xml` conductor corner ground truth**: ROXIE's `alpha` is
an **absolute global Cartesian angle**, not a tilt applied relative to the
turn's local radial/tangent frame. Quoting that reference (read for
understanding only — this task must not copy its code):

> "`alpha_deg` is the ROXIE block's absolute global inclination angle of
> the cable cross-section's radial axis (NOT a tilt expressed relative to
> the local `phi` direction)... verified empirically against the retained
> CTH no-iron benchmark's ROXIE-native `post.xml` conductor corners: for
> every checked block, the Cartesian vector from the inner-edge anchor
> corner to the outer-edge anchor corner has magnitude
> `height_insulated_mm` and a polar direction equal to `alpha_deg` itself."

That same reference also documents that turns within a block are **not**
stacked by rotating at constant polar radius (an arc) — they are stacked
by a **straight Cartesian translation** perpendicular to alpha (a chord),
so turn `k`'s inner anchor is `base + k * inner_step`, where `inner_step`
is a fixed Cartesian vector (not a re-projection onto `radius=const`).

**The coordinator independently re-derived and numerically verified this**
in DOT's own `phi_deg`/`alpha_deg` convention (converting via the already-
validated `phi_dot_deg = 90 - phi_roxie_deg`, `alpha_dot_deg = -alpha_roxie_deg`
relations from task 0008):

```
DOT's CURRENT height_axis(phi_dot, alpha_dot)  [WRONG - phi-dependent]:
    = rotate((sin(phi_dot), cos(phi_dot)), alpha_dot)
    = (sin(phi_dot - alpha_dot), cos(phi_dot - alpha_dot))

CORRECT height_axis(alpha_dot)  [phi-INDEPENDENT]:
    = (cos(alpha_dot), -sin(alpha_dot))

CORRECT width_axis(alpha_dot)  [phi-INDEPENDENT, turn-to-turn stacking direction]:
    = (sin(alpha_dot), cos(alpha_dot))
```

Verified numerically for a real CTH block (`phi_roxie=48.7, alpha_roxie=46.4651`,
so `phi_dot=41.3, alpha_dot=-46.4651`): DOT's current formula gives
`height_axis = (0.9992, 0.0390)`; the corrected formula gives
`height_axis = (0.6888, 0.7249)`, which matches
`(cos(46.4651°), sin(46.4651°)) = (0.6888, 0.7250)` — the independently-
computed ground truth — essentially exactly. DOT's current formula is
**not even close**. This is the dominant source of the parity gap for any
block with non-trivial `alpha`.

## Goal

1. Change `TurnPolygon.from_parameters` (or introduce a new internal
   helper it uses) so that the turn's height axis (inner→outer edge
   direction) and width axis (turn-to-turn stacking direction) are
   computed as **phi-independent** functions of `alpha_deg` alone, using
   the corrected formulas above (still expressed in DOT's own
   `phi_deg`/`alpha_deg` convention — do not change that convention or the
   `phi_dot = 90 - phi_roxie` relationship itself, only the height/width
   axis formulas).
2. Change `Block.turns()` so that turns are stacked via a **straight
   Cartesian translation** (`turn_k_anchor = turn_0_anchor + k * step_mm *
   width_axis`, where `step_mm` is the cable's insulated width) instead of
   the current polar-arc stepping (`phi += k * delta_phi`, holding radius
   constant). The first turn's anchor (`k=0`) is still computed from
   `(inner_radius_mm, phi_deg)` exactly as today.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/primitives.py`
- `tests/geometry/test_primitives.py`
- `tests/physics/test_roxie_parity_cth14t.py` — this test's tolerances
  and/or reference comparison may need updating now that a real fix is
  available; do not weaken it, tighten it if the fix allows.
- **New**: `tests/physics/test_roxie_parity_live.py` — see acceptance
  criteria; this test talks to a live ROXIE REST service and must be
  skipped gracefully (not failed) if the service is unreachable (use
  `pytest.importorskip`/a connection-check skip, matching how such
  integration tests are conventionally guarded).

## Explicit non-goals

- Do not implement the keystone/trapezoid cable cross-section (different
  inner vs. outer cable width) mentioned in the same reference material —
  that is a secondary, smaller effect; assess after this fix whether it's
  still needed to hit the 2% target, and if so, that is a follow-up task,
  not part of this one.
- Do not change DOT's `phi_deg` convention or the `90 - phi_roxie`
  relationship — only the alpha/height/width axis formulas.
- Do not touch `constraints.py`, `optimize/*`, or `gui/*` logic — if
  existing tests there hardcoded geometry produced by the old (buggy)
  formula, update only those specific expected values, not the logic.

## Acceptance criteria

- [ ] Direct unit test reproducing the coordinator's numeric derivation
      above: for `alpha_dot_deg = -46.4651`, the computed height axis
      matches `(cos(46.4651°), sin(46.4651°))` to high precision, and is
      the same regardless of what `phi_deg` is passed (test with at least
      two different `phi_deg` values to prove phi-independence directly).
- [ ] Direct unit test for chord-stacking: for a block with `n_turns >= 3`,
      assert turn `k`'s inner anchor equals
      `turn_0_anchor + k * cable.insulated_width_mm * width_axis(alpha)`
      exactly (not merely "close to" — this is a closed-form check).
- [ ] **Live ROXIE re-validation** (the real bar for this task): with the
      ROXIE REST service reachable at `http://127.0.0.1:8080`, rebuild the
      real CTH-14T block-table design (same data as
      `test_roxie_parity_cth14t.py`), submit a genuinely iron-free version
      to ROXIE (a clean template with `LIRON=F`, `LBEMFEM=F`, blanked
      `.bhdata`/`.iron` references, and **`LIMAGX=F`/`LIMAGY=F`** matching
      the working reference template — do not reuse a template with
      `LIMAGX=T`/`LIMAGY=T`), and confirm DOT's native field now matches
      ROXIE's no-iron field to **within 2%**. If it does not reach 2%,
      report the actual number honestly, show your work (what you tried),
      and do not weaken this criterion to force a pass — this mirrors the
      instruction already proven necessary in task 0008.
- [ ] Also re-check the single-block minimal case the coordinator used
      during investigation (radius=30mm, phi_deg=45°, alpha_deg=0°,
      n_turns=6, cable=CTH_HF-equivalent dimensions, aperture=25mm,
      scaled to 5T) against live ROXIE — this case has `alpha=0` so it
      isolates the chord-vs-arc stacking fix specifically from the
      alpha-axis fix; report both the with-alpha and alpha=0 cases'
      resulting accuracy separately in your summary so the coordinator can
      see which fix contributed what.
- [ ] `ruff check` clean; `pytest -q` passes (the new live-ROXIE test
      should be written to skip cleanly, not fail, in environments without
      ROXIE reachable — verify this by checking the skip path works, e.g.
      by pointing at an unreachable URL in a quick manual check, don't
      leave this unverified).
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\core\geometry_helpers.py`
  — the empirically-validated formulas (`_alpha_height_vector_mm`,
  `_width_axis_vector_mm`, `_turn_polygon_corners_mm`,
  `block_polygon_corners_mm`). Read for the physics/geometry understanding
  only; DOT's implementation must be independently written in DOT's own
  types and convention (see the coordinator's derivation above for the
  DOT-convention-native formulas to implement — use those directly, they
  are already correctly converted).

## Notes for the live ROXIE test

- The ROXIE Docker container may not always be running in every
  environment this test suite executes in. The test MUST skip (not error,
  not fail) when the service is unreachable — check connectivity with a
  short-timeout request first and use `pytest.skip(...)` if it fails, so
  this test never blocks CI/other developers without ROXIE access.
- Use `roxieapi.tool_adapter.RoxieToolAdapter.RestRoxieToolAdapter` (already
  installed on this machine at
  `C:\Users\elisei\AppData\Local\Programs\Python\Python311\Lib\site-packages\roxieapi`)
  for the REST submission — service_url `http://127.0.0.1:8080`,
  `input_files=[data_file, cadata_file]` for a no-iron submission (no
  bhdata/iron files needed once LIRON=F and those references are blanked).
- The real `roxie_CTH_cables.cadata` file is at
  `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata`.
- A working, genuinely-iron-free `.data` template (option flags already
  correctly matched to the reference file's working configuration) can be
  built by taking `C:\Users\elisei\Desktop\dipole_designer\10042026_CTH-14T.data`
  as a base and only changing: blank the `.bhdata` and `.iron` path lines
  (lines 3 and 5, 1-indexed) to `'none'`, and flip both `LIRON=T` ->
  `LIRON=F` and `LBEMFEM=T` -> `LBEMFEM=F` (leave every other flag,
  including `LIMAGX=F`/`LIMAGY=F`/`LSELF=T`, unchanged) — this exact recipe
  was validated by the coordinator to submit and run successfully.
