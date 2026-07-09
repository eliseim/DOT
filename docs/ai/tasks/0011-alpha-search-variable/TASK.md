# TASK: Alpha as a searchable genome variable, midplane block fixed at zero

- **ID**: 0011-alpha-search-variable
- **Status**: draft
- **Model/effort**: High effort. This changes the genome encoding shape
  used by tasks 0005/0009's merged optimizer — a bug here corrupts every
  campaign's search space silently (e.g. reading the wrong genome slot as
  `alpha` for the wrong block). Real ROXIE/CTH designs use substantial
  non-zero `alpha` for most blocks (e.g. the real CTH-14T design used
  `alpha` values up to ~66°) — DOT's current "alpha always 0" simplification
  is a real search-space restriction likely limiting achievable load-line
  margin, per the coordinator's own CTH campaign findings.

## Goal

Currently every block's `alpha_deg` is hardcoded to `0.0` in
`genome.py::decode` (task 0005's "intentional simplification for the first
optimizer core"). The user now requires: the **first block of each layer**
(the midplane-adjacent block) must keep `alpha_deg = 0` (matching real
CTH/ROXIE designs and `dipole_designer`'s "force midplane alpha zero" C18
constraint), but **all other blocks in a layer should have `alpha_deg` as a
searchable genome variable**, bounded per layer.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/genome.py` — `LayerTopology` gains
  `alpha_bounds_deg: tuple[float, float]` (bounds used for every
  non-first block in that layer; the first block's alpha is not a genome
  variable at all — always exactly `0.0`). `Topology.n_var`, `encode`,
  `decode`, and `genome_bounds` all updated consistently: block index 0 in
  each layer contributes 2 genome slots (`phi_deg`, `n_turns`), block
  indices 1..n-1 contribute 3 slots (`phi_deg`, `n_turns`, `alpha_deg`).
- `src/dot/optimize/problem.py` — no logic change expected (it calls
  `decode`/`genome_bounds` generically), but update its tests if genome
  shape assumptions are hardcoded there.
- `src/dot/gui/target_synthesis_gui.py` — add a per-layer "Alpha bounds
  [deg]" (min/max) input field, defaulting to a sensible range (e.g.
  `-10.0` to `70.0` — wide enough to matter, bounded to avoid nonsensical
  tilts; document the choice).
- `tests/optimize/test_genome.py`, `tests/optimize/test_problem.py`,
  `tests/optimize/test_runner.py`, `tests/gui/test_target_synthesis_gui.py`
  — extend/update as needed.

## Explicit non-goals

- No change to which block is "first" (block ordering within a layer is
  unchanged — index 0 in `LayerTopology`'s block list is always the
  midplane-fixed one).
- No per-layer angle or current-cap changes — that's task 0010 (may
  already be merged; if so, do not touch its code beyond what's needed to
  keep tests passing).
- No changes to `Block`/`TurnPolygon`/`Layer` geometry primitives
  (`src/dot/geometry/primitives.py`) — this task only changes what values
  the *optimizer* searches over and feeds into the existing `Block`
  constructor, which already accepts `alpha_deg` as a parameter.

## Acceptance criteria

- [ ] `Topology.n_var` correctly reflects the new variable-width-per-block
      genome (2 slots for block 0, 3 slots for blocks 1..n-1, per layer) —
      test with a multi-layer, multi-block topology and assert the exact
      expected `n_var`.
- [ ] `encode`/`decode` round-trip: encoding a hand-built `DipoleDesign`
      with a non-zero alpha on a non-first block, then decoding, reproduces
      the same `phi_deg`/`n_turns`/`alpha_deg` values — AND confirms the
      first block's decoded `alpha_deg` is always exactly `0.0` regardless
      of what's in the genome array at that position (i.e. there must be
      no genome slot at all for the first block's alpha — verify this by
      shape, not just by value, since a slot that exists but is ignored
      would still "work" for this test but waste search space).
- [ ] `genome_bounds` produces bounds arrays whose shape matches `n_var`
      and whose alpha-related entries (for non-first blocks) match each
      layer's `alpha_bounds_deg`.
- [ ] A full `run_campaign` smoke test (small pop/gen, matching the style
      of existing tests) with a topology that has at least one layer with
      2+ blocks completes without error and produces decoded designs whose
      first-block alphas are exactly 0.0 and whose other blocks' alphas
      fall within the configured bounds.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken (note:
      existing tests that hardcode the old fixed n_var formula
      `1 + 2*n_blocks` per layer WILL need updating — this is expected,
      update them to the new formula, don't work around it).
- [ ] No files outside declared scope modified.

## Notes / open questions

- If `LayerTopology.n_blocks == 1` for some layer (only the midplane
  block, no searchable-alpha blocks), `alpha_bounds_deg` is still a
  required field but simply unused for that layer — do not special-case
  this away, just let it be inert, and note this in your summary.
