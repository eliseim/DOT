# Antigravity independent review prompt — TASK 0022-integer-aware-genetic-operators

You are reviewing a diff produced by another AI worker (Codex) that
changes DOT's NSGA-II optimizer to use integer-aware genetic operators for
`n_turns` and a constructive initial-population sampler, replacing
pymoo's plain defaults. This is optimizer search-behavior code, not
physics — there is no live-ROXIE requirement for this review. Focus on
correctness of the pymoo integration and honesty of the empirical
comparison.

## Inputs

- `docs/ai/tasks/0022-integer-aware-genetic-operators/TASK.md` — read
  fully.
- The diff/commit on branch `task/0022-integer-aware-genetic-operators`.

## What to check

1. **Correctness of the mixed-variable/integer handling.** Confirm
   `n_turns` genes are actually treated as integers throughout
   sampling/crossover/mutation (not just rounded post-hoc after a
   real-valued operator), and that continuous genes (radius, phi, alpha)
   still use appropriate real-valued operators. Run a small script
   yourself generating an offspring population and inspect the genome
   values directly if needed.
2. **Constructive sampler correctness.** Confirm it uses
   `src/dot/geometry/constraints.py`'s actual gap/angle definitions (not
   a reinvented, possibly-inconsistent notion of "gap"), and that it
   produces genomes within the declared bounds (`genome_bounds`).
3. **No regression.** Confirm every existing test still passes, and that
   nothing outside the declared scope changed.
4. **Empirical honesty.** Independently re-run the same before/after
   comparison yourself (or a similar one) for at least one configuration
   — confirm the reported numbers are real and not selectively favorable.
   If you get meaningfully different numbers, say so.
5. **Scope discipline.** No topology search, no staged refinement, no
   constraint/admission changes introduced (those are explicitly out of
   scope for this task).

## Output format

Findings ranked most-severe first. For each: file, line, what's wrong,
concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run the comparison
yourself for at least one configuration before approving.
