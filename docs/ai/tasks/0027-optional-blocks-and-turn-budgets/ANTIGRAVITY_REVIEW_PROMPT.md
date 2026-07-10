# Antigravity independent review prompt — TASK 0027-optional-blocks-and-turn-budgets

You are reviewing a diff produced by another AI worker (Codex) that adds
optional (searchable-count) blocks per layer and turn-count budget
constraints to DOT's genome/optimizer. This is a real architecture change
to `src/dot/optimize/genome.py` (the third time `problem.py` has been
modified, second time for `runner.py`, first time genome.py's core
decode logic has changed since it was written) — no live-ROXIE
requirement, but backward compatibility with every prior NSGA-II task
(0022, 0023, 0025) is the critical bar.

## Inputs

- `docs/ai/tasks/0027-optional-blocks-and-turn-budgets/TASK.md` — read
  fully.
- The diff/commit on branch `task/0027-optional-blocks-and-turn-budgets`.

## What to check

1. **Backward compatibility — most severe check.** Confirm every existing
   test in `test_genome.py`, `test_problem.py`, `test_runner.py` still
   passes, and specifically confirm `n_blocks=1` layers (no active gene)
   and campaigns without `max_total_turns`/`max_turns_per_layer` set
   behave identically to before this diff — run the tests yourself, don't
   just trust the reported pass count.
2. **Active-block decode correctness.** Independently construct a genome
   by hand with a known mix of active/inactive blocks (different from
   whatever Codex's own tests use) and verify `decode()` produces exactly
   the expected `Layer.blocks`.
3. **Turn-budget constraint correctness.** Confirm the constraint values
   are genuinely graded (verify with your own two over-budget designs of
   different severity) and are computed cheaply (before/without a full
   physics evaluation) — check the actual code path in `_evaluate`.
4. **Genome consistency.** Confirm `genome_bounds`/`genome_variables`/
   `mixed_variable_spec`/`flatten_mixed_genome`/`encode` are all mutually
   consistent with the new active genes — a mismatch here (e.g. `n_var`
   off by one relative to what `genome_variables` actually enumerates)
   would be a serious, possibly silent bug. Check this carefully, it's
   the kind of thing that's easy to get subtly wrong.
5. **Empirical variation check.** Independently run a small campaign
   (your own configuration, not necessarily identical to Codex's) with
   `n_blocks` as a real maximum (e.g. 4) and confirm the population
   genuinely explores different active-block counts, not just always the
   max or always the min.
6. **Scope discipline.** No physics/geometry changes, no
   `dipole_designer`-style repair/regeneration/topology-niching
   machinery ported in.

## Output format

Findings ranked most-severe first — a backward-compatibility regression on
any existing fixed-topology test, or a silent genome-length/indexing
mismatch, are the most severe possible findings here. For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — construct your own
hand-verified decode test case and run your own empirical campaign check
before approving.
