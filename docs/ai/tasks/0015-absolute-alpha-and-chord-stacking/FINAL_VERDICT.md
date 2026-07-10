# FINAL VERDICT — TASK 0015-absolute-alpha-and-chord-stacking

- **Date**: 2026-07-10
- **Branch / worktree**: task/0015-absolute-alpha-and-chord-stacking
- **Coordinator**: Claude Sonnet

## Background

Triggered by re-investigating the ROXIE parity gap once the ROXIE Docker
REST service became live. Research into `dipole_designer`'s own
reverse-engineered geometry code, combined with the coordinator's own
numeric derivation, found DOT's `height_axis`/`width_axis` formulas were
incorrectly phi-dependent (rotating a local frame) when they should be
phi-independent absolute-alpha directions. The coordinator verified this
derivation numerically against real block data before dispatching.

## Process (two rounds, with independent verification pulling real ROXIE post.xml data both times)

**Round 1 (Codex):** Implemented the phi-independent axes fix correctly,
but also implemented straight-chord turn stacking (following a literal
reading of `dipole_designer`'s reference code). Live ROXIE validation:
CTH-14T improved from ~13% to 1.35% (huge win), but the alpha=0
single-block isolation case still failed at 10.4%.

**Antigravity review (round 1): REJECT.** Went further than reading code —
pulled real ROXIE `post.xml` conductor corner data directly and found
turns actually stack at a **constant mandrel radius (arc)**, not a
straight chord. Quantified: chord-stacking drifted turn 6 in the
single-block case to a 37.26mm radius from a 30mm nominal (23% radial
error), and shifted CTH-14T Block 3's center by 1.75mm. Confirmed the
phi-independent axes fix should be kept. This finding directly explained
the round-1 failure.

**Coordinator:** Independently confirmed this visually — plotted real
ROXIE `post.xml` corners against DOT's chord-stacked corners for the
single-block case; the shapes clearly diverged (ROXIE: consistent arc,
same-size turns; DOT: turns fanning outward radially).

**Round 2 (Codex):** Reverted to arc/constant-radius stacking while
keeping the phi-independent axes fix, with phi stepping subtracted per
turn index (empirically confirmed correct direction — the opposite sign
gave 9.39% error). Added a near-pole circle-intersection fallback needed
for turns whose stacking offset approaches the mandrel radius. Live ROXIE
results: **CTH-14T 1.256% error, single-block 1.529% error — both under
the 2% target.**

**Antigravity review (round 2): APPROVE.** Independently re-ran live ROXIE
validation (matched Codex's numbers exactly), verified the near-pole
fallback is a legitimate geometric necessity — not masking a bug — by
confirming it produces centers within 0.01mm of the simple-case formula
where both are applicable, and confirmed the phi-subtraction direction
algebraically.

**Coordinator:** Independently re-confirmed visually for both the
single-block case and the full real 9-block/86-turn CTH-14T design —
DOT's computed layout now closely matches ROXIE's real geometry in both
cases, with only a small residual offset consistent with the ~1.3-1.5%
numeric error.

## Gate results

- `ruff check`: pass
- `pytest -q` (excluding the live-ROXIE test, which needs `roxieapi` in
  the environment): 83 passed, 4 failed — all 4 failures are expected and
  out of scope (stale hardcoded expectations from the old, now-fixed
  geometry, in `test_constraints.py` ×2, `test_genome.py` ×1,
  `test_problem.py` ×1). Follow-up task needed to update these fixtures.
- Live ROXIE test: skip-path verified (unreachable URL → clean skip, not
  failure); pass path verified independently by both Codex and Antigravity
  with matching numbers.
- Scope: exactly the 4 declared files across both rounds.

## Coordinator decision

- Decision: **MERGE**
- Rationale: this is the most consequential fix of the session — it
  corrects DOT's core turn geometry model, verified through two full
  review rounds, direct pulls of real ROXIE ground-truth corner data (not
  just aggregate field numbers), independent numeric re-derivation, and
  visual confirmation for both a minimal isolation case and the full real
  CTH-14T design. Both live-validated cases are now under the user's 2%
  target.
- Follow-up needed (tracked separately): update the 4 stale test fixtures
  in `test_constraints.py`/`test_genome.py`/`test_problem.py` to reflect
  the corrected geometry.

## User approval

- [x] User explicitly directed continued debugging until under 2%,
      including parallel Codex/Antigravity work and visual verification —
      all satisfied.
