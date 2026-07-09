# Antigravity independent review prompt — TASK 0011-alpha-search-variable

You are reviewing a diff produced by another AI worker (Codex) for DOT's
genome encoding — changing from "alpha always 0" to "alpha searchable for
all blocks except the first (midplane) block per layer." You did not see
the worker's reasoning — judge only the diff, the repository, and the task
spec. Genome-indexing bugs are silent and severe: a one-slot
misalignment corrupts every value read after it for the rest of that
layer's blocks (phi/n_turns/alpha all shift), producing plausible-looking
but wrong designs that would not obviously crash.

## Inputs

- `docs/ai/tasks/0011-alpha-search-variable/TASK.md`
- The diff/commit on branch `task/0011-alpha-search-variable`.

## What to check — trace the indexing by hand, don't just trust tests

1. **Hand-trace `encode`/`decode`/`genome_bounds` together** for a
   constructed 2-layer topology (e.g. layer A: 1 block; layer B: 3
   blocks) and confirm all three functions agree on exactly which flat
   array index holds which value. Write out the expected index map
   yourself (radius, phi0, n_turns0, [layer B only:] phi1, n_turns1,
   alpha1, phi2, n_turns2, alpha2, ...) and compare against the actual
   code.
2. **First-block alpha is structurally absent from the genome**, not just
   value-0.0 by convention. Confirm `decode` hardcodes `0.0` for block
   index 0's alpha without reading any genome slot for it, and that
   `genome_bounds`/`encode` never allocate a slot for it either. If a test
   only checks the *decoded value* is 0.0 without checking the *genome
   shape* doesn't waste a slot on it, note this as a test-quality gap
   (TASK.md explicitly calls for the shape check).
3. **`n_var` formula correctness.** Recompute `n_var` by hand for a test
   topology and compare against `Topology.n_var`'s actual computed value.
4. **Bounds correctness.** Confirm `genome_bounds`'s alpha-related entries
   for non-first blocks actually pull from that layer's own
   `alpha_bounds_deg` (not, e.g., a different layer's bounds due to index
   confusion, or the phi bounds by copy-paste error).
5. **Existing test updates.** Where old tests hardcoded the previous
   `1 + 2*n_blocks` formula, confirm they were updated to the new formula
   correctly (not just changed to make the number match without
   understanding why).
6. **Scope discipline.** Only declared files touched? No changes to
   `Block`/`TurnPolygon`/geometry primitives?

## Output format

Findings ranked most-severe first — any genome index misalignment is
critical (silently wrong optimizer results with no crash). For each: file,
line, what's wrong, concrete failure scenario (what wrong value would be
read as what). End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on "tests pass" without independently re-deriving the
index map for at least one non-trivial topology yourself.
