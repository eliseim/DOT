# FINAL VERDICT — TASK 0017-keystone-cable-cross-section

- **Date**: 2026-07-10
- **Branch / worktree**: task/0017-keystone-cable-cross-section
- **Coordinator**: Claude Sonnet

## Background

Continuing the ROXIE parity debugging past task 0015: the coordinator's
200-case sweep surfaced that even single-turn cases (no stacking involved)
showed a consistent 2-3.4% error, isolated to `CableSpec` averaging a
keystoned cable's inner/outer widths into one flat rectangle instead of
modeling the real trapezoid shape (CTH_HF tapers 8.4% inner-to-outer).

## Codex summary

`CableSpec` now carries `width_inner_mm`/`width_outer_mm` and independent
radial/azimuthal insulation, with legacy rectangular fields kept for
compatibility. `TurnPolygon` builds a true trapezoid; `Block.turns()`
(both the simple-arc and near-pole fallback branches) uses the inner
insulated width for the stacking step, matching the already-validated
reference convention. Also fixed a related bug in the same file: the
GUI's `.cadata`→`CableSpec` conversion hardcoded insulation thickness to
0.0 instead of reading the real `INSUL` section — now reads it correctly.

**Live ROXIE validation, all 5 cases now under 2%:**

| Case | DOT | ROXIE | Diff |
|---|---:|---:|---:|
| CTH-14T real design (regression) | 12.4757 T | 12.4191 T | **0.456%** |
| alpha=0, 6-turn single block (regression) | 5.0000 T | 5.0732 T | **1.443%** |
| r=35, phi=40, 1 turn (new) | 5.0000 T | 4.9852 T | **0.297%** |
| r=40, phi=30, 1 turn (new) | 5.0000 T | 4.9783 T | **0.435%** |
| r=45, phi=50, 1 turn (new) | 5.0000 T | 4.9964 T | **0.072%** |

Notably the two task-0015 regression cases *improved* (CTH-14T from
1.256% to 0.456%), confirming keystoning was a real, additional
contributing factor even in those already-passing cases.

## Antigravity verdict

- Result: **APPROVE WITH NITS**
- Independently hand-derived trapezoid corners for a different test case
  (phi=30°, alpha=15°, inner width 2.0mm, outer width 4.0mm, height 5.0mm)
  than Codex used, matching exactly.
- Independently confirmed both stacking branches (`simple-arc` and
  `_arc_stacked_anchor` fallback) use the inner insulated width.
- Independently re-ran live ROXIE validation for all 5 cases, confirming
  no regression on the task-0015 cases and all new cases passing.
- Independently confirmed the GUI insulation fix against the real
  `roxie_CTH_cables.cadata` file.
- Nit (non-blocking): a mypy variable-shadowing warning in the GUI code,
  cosmetic, not part of DOT's current gate.

## Gate results

- `ruff check`: pass
- `pytest -q`: 89 passed, 5 deselected (live ROXIE tests need `roxieapi`
  in the venv) — zero failures.
- Scope: exactly the 7 declared files.

## Coordinator decision

- Decision: **MERGE**
- Rationale: closes the remaining systematic gap identified by the
  200-case sweep, verified by two independent live-ROXIE validation
  passes (Codex's and Antigravity's, each run separately against the
  real service) with zero regressions on the previously-hardest-won
  fixes. Keystoning is confirmed to be a real, physically meaningful
  effect for accelerator dipole cables, not overengineering.

## User approval

- [x] User explicitly directed continuing until fully merged and under
      2%, and explicitly confirmed keystoning matters and should be
      modeled — satisfied.
