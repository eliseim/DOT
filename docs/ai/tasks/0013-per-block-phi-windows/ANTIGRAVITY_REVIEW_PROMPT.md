# Antigravity independent review prompt — TASK 0013-per-block-phi-windows

You are reviewing a diff produced by another AI worker (Codex) for DOT's
genome bounds — partitioning each layer's phi search window across its
blocks instead of sharing one window. You did not see the worker's
reasoning — judge only the diff, the repository, and the task spec. This
fixes a real, measured problem (near-100% overlap rate for multi-block
layers under the old shared-window behavior) found while running a real
campaign — verify the fix actually addresses it, not just that bounds
shapes changed.

## Inputs

- `docs/ai/tasks/0013-per-block-phi-windows/TASK.md`
- The diff/commit on branch `task/0013-per-block-phi-windows`.

## What to check

1. **Partition formula correctness.** Hand-compute the expected
   sub-windows for a `n_blocks=4`, `phi_bounds_deg=(2.0, 78.0)` layer
   (should be four equal 19° windows: `(2,21), (21,40), (40,59), (59,78)`)
   and compare against the actual `genome_bounds` output.
2. **`n_blocks=1` no-op.** Confirm a single-block layer's bounds are
   exactly the unmodified `phi_bounds_deg` — no accidental narrowing.
3. **The empirical test is real and meaningful.** Confirm the test
   comparing feasible-fraction under old vs. new bounds actually
   constructs two genuinely different bounds configurations (not
   accidentally testing the same thing twice) and that the new bounds
   produce a materially higher feasible fraction, not just a marginal or
   noise-level difference — re-run or trace the numbers yourself if
   feasible.
4. **No `decode`/`encode` changes.** Confirm the diff is scoped to
   `genome_bounds` only — a genome value must still mean the same thing
   (`decode` unaware of any partitioning), otherwise other code paths that
   construct genomes directly (tests, `encode`) would silently
   misinterpret values.
5. **Scope discipline.** Only the two declared files touched?

## Output format

Findings ranked most-severe first. For each: file, line, what's wrong,
concrete failure scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
