# Antigravity independent review prompt — TASK 0010-per-layer-angle-and-current-cap

You are reviewing a diff produced by another AI worker (Codex) for DOT's
feasibility-gate correctness: per-layer pole-angle limits and an operating
current cap. You did not see the worker's reasoning — judge only the diff,
the repository, and the task spec.

## Inputs

- `docs/ai/tasks/0010-per-layer-angle-and-current-cap/TASK.md`
- The diff/commit on branch `task/0010-per-layer-angle-and-current-cap`.

## What to check

1. **Per-layer angle correctness.** Confirm the test proving per-layer
   application actually changes behavior (not just API-shape acceptance)
   is real: a turn in layer 1 that would pass at a uniform 85° but must
   fail at layer-1-specific 80°. Trace the lookup logic yourself — is the
   turn's `layer_index` correctly used to index into the per-layer
   sequence, or could there be an off-by-one (e.g. layer 2's limit
   applied to layer 1's turns)?
2. **Backward compatibility.** Confirm a single `float` still works
   exactly as before everywhere it's threaded through — check the diff
   doesn't quietly require all callers to switch to sequences.
3. **Length-mismatch handling.** Confirm a wrong-length sequence raises
   clearly rather than silently truncating/padding/reusing the first
   value.
4. **Current cap correctness.** Confirm exceeding `max_current_a` marks
   the candidate infeasible (`G > 0`, penalty objectives) rather than
   clipping the current or silently ignoring the cap. Confirm the
   comparison uses the correct value — `operating_point(...).operating_current_a`,
   not some other current-like value that might be per-turn or per-strand
   instead of the actual operating current.
5. **Scope discipline.** Only the declared files touched? No genome/alpha
   changes (that's task 0011, out of scope here)?

## Output format

Findings ranked most-severe first. For each: file, line, what's wrong,
concrete failure scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
