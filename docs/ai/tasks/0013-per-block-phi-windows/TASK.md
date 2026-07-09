# TASK: Partition each layer's phi search window across its blocks

- **ID**: 0013-per-block-phi-windows
- **Status**: draft
- **Model/effort**: High effort. Fixes a real, empirically-confirmed
  search-space defect blocking real campaigns, discovered by the
  coordinator while running a real CTH-spec campaign: not a hypothetical
  improvement.

## Background

The coordinator ran a real campaign (4 layers, CTH_HF/CTH_HF/CTH_LF/CTH_LF,
12.4 T target, real geometric constraints from tasks 0008-0012) and found
it could never produce a feasible candidate with more than 1 block per
layer. Diagnosis (500 random genome samples per configuration):
- With each layer's blocks all drawing `phi_deg` independently from the
  *same* shared `phi_bounds_deg` range (current `genome_bounds` behavior),
  2+ blocks in one layer overlap (`turn_non_intersection` violation) in
  effectively 100% of random samples, and NSGA-II across tens of thousands
  of evaluations never found a feasible one either.
- Restricting to exactly 1 block per layer raised geometric feasibility to
  ~31%, but then made every candidate massively current-inefficient
  (19,000-230,000 A required to hit 12.4 T, vs. the real CTH-14T
  reference's 12,238 A for a similar total turn count at 14 T) — because a
  single concentrated block cannot approximate the spread-out,
  near-cosine-theta current distribution that real multi-block coil layers
  use to generate field efficiently per amp-turn.

Multiple, well-separated blocks per layer are therefore not a cosmetic
preference — they are necessary for the optimizer to find
current-efficient (and thus margin-viable) designs at all.

## Goal

Automatically partition each layer's `phi_bounds_deg` into `n_blocks`
equal, non-overlapping sub-windows — one per block index — used as that
specific block's own search bounds in `genome_bounds`. Block index 0 gets
the sub-window closest to the layer's `phi_bounds_deg[0]` (midplane side,
by the existing convention), block index `n_blocks - 1` gets the
sub-window closest to `phi_bounds_deg[1]`, and so on in order. This does
not change `decode`'s per-genome-value interpretation (a genome value is
still "the block's phi_deg" directly) — it only changes what range
`genome_bounds` offers the optimizer to search within for each block's
slot, dramatically reducing the chance of the optimizer proposing
overlapping blocks in the first place while still leaving it free to
explore within each sub-window (including up to that sub-window's own
edges, so blocks can still end up close together if that's genuinely
optimal — this is about making non-overlapping configurations the
*common* case for random/mutated genomes, not a hard constraint by
itself; `check_feasibility`'s `turn_non_intersection` check remains the
actual feasibility gate).

## Scope (files/modules Codex may touch)

- `src/dot/optimize/genome.py` — `genome_bounds` only (`encode`/`decode`
  do not need to change, since they already just read/write whatever
  value is at each genome slot; only the *bounds offered to the optimizer*
  change).
- `tests/optimize/test_genome.py` — extend.

## Explicit non-goals

- No change to `decode`'s interpretation of genome values — a genome
  value at a block's phi slot is still that block's `phi_deg` directly, no
  offset/relative encoding introduced.
- No change to `check_feasibility`/`constraints.py` — the actual
  feasibility gate is unchanged; this task only improves the odds that
  randomly-sampled or mutated genomes land in the feasible region.
- No forced non-overlap guarantee — a block can still be placed anywhere
  within its own sub-window, including near its edges (adjacent to a
  neighboring block's sub-window), so overlap is still *possible* just far
  less *likely*. Do not add a hard-separation buffer beyond the equal
  partition itself (avoid overengineering — the equal partition alone is
  what the diagnosis shows is needed).

## Acceptance criteria

- [ ] For a layer with `n_blocks=4` and `phi_bounds_deg=(2.0, 78.0)`,
      `genome_bounds` assigns block 0 bounds `(2.0, 21.0)`, block 1
      `(21.0, 40.0)`, block 2 `(40.0, 59.0)`, block 3 `(59.0, 78.0)`
      (four equal 19° sub-windows) — test this exact partition
      numerically for a constructed topology.
- [ ] For a layer with `n_blocks=1`, the single block's bounds equal the
      full `phi_bounds_deg` unchanged (no partitioning effect when there's
      only one block) — regression-proof backward compatibility for
      existing single-block-per-layer campaigns/tests.
- [ ] A repeat of the coordinator's empirical diagnosis, as a test: for a
      4-block layer with the partitioned bounds, random-sampling genomes
      within the new per-block bounds and checking geometric feasibility
      achieves a **materially higher feasible fraction** than sampling
      with the old shared-bounds behavior for the same layer (construct
      both and compare counts over e.g. 200 samples each with a fixed
      seed) — this is the actual real-world claim this task makes, prove
      it empirically in a test, not just via the bounds-shape assertion
      above.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken (note:
      any existing test hardcoding the old shared-bounds behavior for
      multi-block layers will need updating — expected, do it
      deliberately).
- [ ] No files outside declared scope modified.

## Notes / open questions

- If `n_blocks` doesn't divide `phi_bounds_deg`'s span evenly, use plain
  float division (no need for anything fancier) — sub-window edges don't
  need to be "nice" numbers.
