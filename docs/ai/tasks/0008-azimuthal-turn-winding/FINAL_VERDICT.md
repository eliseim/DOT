# FINAL VERDICT — TASK 0008-azimuthal-turn-winding

- **Date**: 2026-07-09
- **Branch / worktree**: task/0008-azimuthal-turn-winding — .worktrees/0008-azimuthal-turn-winding
- **Coordinator**: Claude Sonnet

## Background

Triggered by the coordinator's own ROXIE parity investigation (real captured
ROXIE run, `10042026_CTH-14T.data`/`.output` in `dipole_designer`, zero iron
elements): DOT's native physics engine was found to be 56-87% off on bore
field and up to 3 orders of magnitude off on harmonics versus real ROXIE
output for an identical geometry.

## Process (two rounds, plus coordinator hands-on diagnosis)

**Round 1 (Codex):** Diagnosed the root cause correctly — `Block.turns()`
stacked turns radially outward at fixed phi/alpha; real ROXIE/coil winding
places multi-turn blocks azimuthally at ~constant radius. Implemented the
fix in `primitives.py`. Built the ROXIE parity test from data supplied in
TASK.md. **Result did not converge on harmonics; Codex correctly reported
this honestly rather than forcing a pass or loosening tolerances itself**,
per explicit instruction.

**Coordinator diagnosis:** Investigated further directly, since this
required careful coordinate-convention reasoning. Found a second bug:
ROXIE's `alpha_deg` sign convention is opposite to DOT's. Verified by
direct experiment: with both the phi conversion (`90 - phi_roxie`, already
correct) and the newly-found alpha negation (`-alpha_roxie`) applied, bore
field matches ROXIE to **0.09%** (was 87% off). Harmonics still don't
match ROXIE's specific values even with both fixes — diagnosed as expected
and out of scope: ROXIE's reference turns are individually optimized to
cancel those harmonics; DOT's formula-based azimuthal placement reproduces
the bulk current distribution correctly but has no reason to reproduce
someone else's harmonic-cancelling fine geometry for a design DOT didn't
itself optimize. **User explicitly agreed** to accept bulk-field parity as
the validated claim and relax the harmonic-matching requirement rather than
chase further (would be overengineering).

**Round 2 (Codex):** Applied the alpha-sign fix to the parity test's input
conversion only (confirmed `primitives.py` needed no further change — the
azimuthal-stepping formula and `+` direction were already correct). Rewrote
the parity test's assertions to reflect the real, validated claim: bulk
field within 5% (achieves ~0.09%), main dipole term near 10000, all normal
harmonics finite/bounded (sanity, not ROXIE-matching), skew terms near zero
(a real symmetry property, still holds). 67 tests, ruff clean.

## Antigravity verdict

- Result: **APPROVE**, no findings.
- Independently re-read the raw ROXIE source files
  (`10042026_CTH-14T.data`, `10042026_CTH-14T.output`,
  `roxie_CTH_cables.cadata`) and confirmed every transcribed number in the
  test — main field, all six harmonic reference values, both cables'
  dimensions, the full 9-block table — matches character-for-character.
- Independently wrote and ran its own comparison script reproducing the
  coordinator's 0.09%-error result and confirming the `+` stepping
  direction is the only one of the two that converges within tolerance.
- Confirmed no existing constraint/optimizer tests were touched, and that
  `test_primitives.py`'s changes are a straightforward replacement of
  now-incorrect radial-stacking coordinate assertions with correct
  azimuthal ones.

## Gate results

- `ruff check`: pass
- `pytest`: pass (67 passed)
- Independently re-verified by the coordinator in a throwaway venv, in
  addition to extensive direct hands-on diagnosis of the underlying
  physics/geometry (not just running tests) throughout this task.
- Scope: `src/dot/geometry/primitives.py`, `tests/geometry/test_primitives.py`,
  `tests/physics/test_roxie_parity_cth14t.py` — matches TASK.md.

## Coordinator decision

- Decision: **MERGE**
- Rationale: fixes a real, measured, substantial discrepancy against
  actual ROXIE output (87% field error down to 0.09%). The relaxed
  harmonic tolerance reflects an honest, well-reasoned scope decision
  (confirmed with the user) rather than a weakened test — the test still
  makes a real, load-bearing, independently-verified claim about DOT's
  physics engine.

## User approval

- [x] User pre-authorized autonomous commit/merge for this task chain.
- [x] User explicitly chose to relax the harmonic-parity requirement
      rather than continue chasing exact ROXIE harmonic reproduction,
      after being shown the diagnosis and tradeoff.
