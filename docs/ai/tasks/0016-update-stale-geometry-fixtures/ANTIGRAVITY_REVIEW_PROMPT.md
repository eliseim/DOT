# Antigravity independent review prompt — TASK 0016-update-stale-geometry-fixtures

You are reviewing a diff produced by another AI worker (Codex) updating 4
test fixtures to match task 0015's already-merged, already-verified
geometry fix. You did not see the worker's reasoning — judge only the
diff, the repository, and the task spec.

## Inputs

- `docs/ai/tasks/0016-update-stale-geometry-fixtures/TASK.md`
- The diff/commit on branch `task/0016-update-stale-geometry-fixtures`.

## What to check

1. **Each updated value is independently justified**, not just copy-pasted
   from a test run. Spot-check at least 2 of the 4 by recomputing them
   yourself from the corrected geometry formula in
   `src/dot/geometry/primitives.py`.
2. **No weakening.** Confirm no assertion's tolerance was loosened or its
   intent changed — only the numeric expectation was corrected.
3. **The partitioned-phi-windows test still demonstrates a real
   improvement** (not just updated to whatever number happens to pass) —
   check the qualitative claim (partitioned windows > shared windows for
   feasibility) still holds.
4. **Scope discipline.** Only the 3 declared test files touched? No
   changes to `src/dot/geometry/primitives.py` or any other source file?
5. **Full suite passes with zero failures.**

## Output format

Findings ranked most-severe first. For each: file, line, what's wrong,
concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
