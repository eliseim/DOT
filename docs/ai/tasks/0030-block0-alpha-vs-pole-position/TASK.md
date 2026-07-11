# TASK: Resolve block-0 fixed-alpha vs. pole-side genome windowing conflict

- **ID**: 0030-block0-alpha-vs-pole-position
- **Status**: draft
- **Model/effort**: High effort, design judgment required. Likely touches
  `src/dot/optimize/genome.py` (genome_bounds/decode's block-0/alpha
  convention) and possibly `src/dot/optimize/runner.py`. This is an
  architecture decision, not a mechanical bug fix -- read the whole
  Background section before proposing an approach, and if multiple
  reasonable designs exist, lay them out with tradeoffs rather than
  picking one unilaterally.

## Background

Task 0029 (turn-aware phi gap, merged) fixed a real bug in
`PhiOrderingRepair`'s minimum-gap formula. After merging it, the real CTH
campaign (`cth_campaign5.py`, a coordinator scratch script, path below)
still showed the population collapsing almost entirely to geometry
infeasibility (`turn_non_intersection`) within a couple of generations.
Investigating further (coordinator, not yet a dispatched task) found a
second, deeper, and distinct root cause:

1. `genome.py`'s `decode()` hard-fixes `alpha_deg = 0.0` for block index 0
   in every layer, with no genome slot for it (see the module docstring
   and `decode()`'s handling of `block_index == 0`).
2. `genome.py`'s `genome_bounds()` partitions each layer's
   `phi_bounds_deg` range into `n_blocks` equal, non-overlapping windows
   in **ascending block-index order** -- block index 0 always gets the
   window closest to `phi_bounds_deg[0]` (the lower bound), and higher
   block indices get windows progressively closer to
   `phi_bounds_deg[1]`.
3. Turn geometry (`dot.geometry.primitives.TurnPolygon.from_anchor`,
   `_turn_axes`) treats `alpha_deg` as an angle **absolute in the global
   x-y plane**, not relative to the turn's own `phi_deg`. This is a
   documented, deliberate ROXIE-consistent convention (see the module
   docstring in `primitives.py`, and task 0015's chord-stacking fix) --
   not itself a bug.
4. The practical consequence: `alpha_deg = 0` only produces a turn whose
   "height" axis (radial buildup direction) is close to the *true* local
   radial direction when the turn's `phi_deg` is close to 90 (the
   midplane). Confirmed empirically (coordinator): for the CTH HF cable at
   r=30mm, a single block with `alpha_deg=0`, 2 turns, self-overlaps
   (`check_turn_non_intersection` fails) below roughly `phi=20`; needing
   `phi>=54` for 8 turns; `phi>=78` for 15 turns; 30 turns has no safe phi
   in the entire 0-90 range at that radius. The alpha actually required to
   keep a turn's axes aligned with its true local radial direction is
   approximately `alpha = phi - 90` (confirmed by direct numeric scan,
   e.g. phi=3 needs alpha near -88, phi=10 needs alpha near -81) --
   i.e. large and *negative* for blocks far from the midplane, not
   positive.

Combining (1)+(2): block index 0 is **always** placed in the *lowest*
(most pole-ward, if `phi_bounds_deg[0]` is chosen near the pole, which is
the natural choice for a layer meant to span from near-pole to
near-midplane) phi sub-window, and it is the **one block that cannot use
any alpha compensation at all** (hard-fixed to 0). This is backwards from
what's needed: the block nearest the pole is exactly the one that most
needs alpha compensation, and block 0 is the one block guaranteed not to
have it.

`DEFAULT_ALPHA_BOUNDS_DEG = (-10.0, 70.0)` in `genome.py` (applied to
blocks 1..n-1, which *do* have a free alpha gene) is asymmetric in the
*positive* direction, which does not match the actual empirically-needed
*negative* direction found above -- this default range may itself be
miscalibrated, or may reflect a different intended sign/offset convention
that the coordinator's investigation did not fully reconcile. This needs
to be resolved as part of this task, not assumed.

A single coordinator attempt to work around this by reversing
`PhiOrderingRepair`'s block-index-to-phi assignment direction (making
block 0 land in the *highest* sub-window instead) was tried and reverted:
it directly conflicts with `genome_bounds()`'s own hardcoded ascending
per-block windowing (a different, more fundamental piece of the genome
encoding), producing duplicate/degenerate phi assignments in existing
tests. Any fix here must be consistent with (or deliberately and
coherently change) `genome_bounds()` itself, not fight it from
`runner.py` alone.

## Goal

Propose and implement a coherent fix so that a genome with block 0 in the
pole-side sub-window of a wide multi-block layer, at realistic CTH turn
counts (up to `n_turns_bounds` upper, e.g. 15-30), can actually be
geometrically valid (not guaranteed-infeasible by construction). Concrete
directions worth evaluating -- pick one, or something better, and justify
the choice:

1. **Give block 0 a free (or differently-fixed) alpha too**, removing the
   hard-fix-to-0 special case, and instead enforce "alpha=0 for the
   midplane block" (the user's original requirement) as a *position-aware*
   constraint applied to whichever block is actually closest to phi=90,
   rather than unconditionally to block index 0. This likely requires
   `decode()`/`genome_bounds()` changes and probably a new repair or
   constraint to keep it near-zero only when appropriate.
2. **Reverse `genome_bounds()`'s own per-block windowing direction**
   (block index 0 gets the window closest to `phi_bounds_deg[1]` instead
   of `phi_bounds_deg[0]`), so block 0 (fixed alpha=0) is structurally
   guaranteed to be the midplane-side block, and campaign authors choose
   `phi_bounds_deg` with the pole side at the lower bound as before. This
   is probably the more surgical fix but changes a foundational genome
   convention used elsewhere -- audit all call sites and existing tests
   for assumptions about which end block 0 lands on.
3. **Make the fixed-alpha convention configurable per topology** (e.g. a
   `LayerTopology` field controlling which end of the phi range gets the
   zero-alpha treatment, or removing the automatic fixing entirely and
   letting campaign authors decide via bounds), if neither blanket
   direction is always correct.

Whichever direction is chosen, also determine and correct the right
`alpha_bounds_deg` default/sign convention for the free-alpha blocks,
backed by the `alpha = phi - 90`-style empirical relationship above (or a
more rigorous derivation from `_turn_axes`/`TurnPolygon.from_anchor` if
that turns out to be more precise than the coordinator's numeric scan).

## Scope (files/modules Codex may touch)

- `src/dot/optimize/genome.py`
- `src/dot/optimize/runner.py` (only if the chosen fix requires
  repair/sampling changes to match)
- `src/dot/geometry/primitives.py` (read-only reference; only touch if
  you determine the alpha/axis convention itself needs correcting, which
  would be a major finding -- justify extremely carefully, this file is
  ROXIE-parity-critical and has live-ROXIE tests)
- `tests/optimize/test_genome.py`, `tests/optimize/test_runner.py`
- `tests/geometry/test_primitives.py` (only if primitives.py changes)

## Explicit non-goals

- No change to `PhiOrderingRepair`'s turn-aware gap formula (task 0029,
  correct and merged).
- No change to `TurnBudgetRepair` (task 0028, correct).
- Do not touch live-ROXIE-validated physics/field code.
- Do not weaken any existing test's tolerance to force a pass.

## Acceptance criteria

- [ ] A documented, justified design decision on how block 0's alpha
      convention and `genome_bounds()`'s windowing direction interact,
      with the chosen fix implemented.
- [ ] Empirical validation: a layer with 4 blocks, realistic CTH cable
      dimensions, radius ~30mm, phi range spanning from near-pole
      (~3-10deg) to near-midplane (~75-85deg), and turn counts up to a
      realistic per-block cap (e.g. 15-30), can produce geometrically
      *valid* (feasible) designs at a healthy rate -- not the near-100%
      infeasibility currently observed. Show before/after.
- [ ] Run the coordinator's real campaign script as the ultimate check:
      `python C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py 60 30 42`
      (read-only reference, do not modify) -- report the `real_F`
      progression before and after.
- [ ] Existing tests pass, updated only where they encoded the old (now
      changed) convention, with a clear note on why each was updated.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.

## Reference material

- `src/dot/optimize/genome.py` -- `decode()`, `genome_bounds()`,
  `DEFAULT_ALPHA_BOUNDS_DEG`.
- `src/dot/geometry/primitives.py` -- `TurnPolygon.from_anchor`,
  `_turn_axes`, `Block.turns()`, `_arc_stacked_anchor`.
- `src/dot/geometry/constraints.py` -- `check_turn_non_intersection`
  (ground truth for what "valid" means here).
- `src/dot/optimize/runner.py` -- `PhiOrderingRepair` (task 0029, already
  correct for gap sizing; do not re-litigate).
- `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py`
  and `cth_sampler3.py` (read-only scratch scripts, not part of the DOT
  package) -- the real campaign exhibiting this failure.
