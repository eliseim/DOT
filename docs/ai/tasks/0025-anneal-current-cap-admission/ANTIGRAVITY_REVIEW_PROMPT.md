# Antigravity independent review prompt — TASK 0025-anneal-current-cap-admission

You are reviewing a diff produced by another AI worker (Codex) that
extends DOT's existing harmonic/margin admission-annealing pattern to
also cover the current-cap constraint. This is optimizer search-behavior
code, not physics — no live-ROXIE requirement, but check the change is a
genuine, consistent extension of the existing pattern, not a divergent
one-off.

## Inputs

- `docs/ai/tasks/0025-anneal-current-cap-admission/TASK.md` — read fully.
- The diff/commit on branch `task/0025-anneal-current-cap-admission`.

## What to check

1. **Pattern consistency.** Confirm the current-cap annealing genuinely
   mirrors the existing harmonic/margin annealing (same linear relaxation
   structure, same style of threshold computation) rather than
   implementing a different mechanism.
2. **Graded, not flat.** Confirm the current-cap constraint value is now
   continuous (`max(0.0, abs(current) - threshold)` or equivalent), not a
   flat `1.0` flag. Verify with your own quick test: two designs at
   different amounts over the cap should produce different `G` values.
3. **Objectives still computed for annealed-feasible-but-cap-exceeding
   designs.** Confirm a design within the relaxed early-generation
   threshold but over the true `max_current_a` still gets real
   `field_quality`/`margin_percent` objective values, not a skip.
4. **Final generation enforces the true cap.** Confirm
   `admission_thresholds()` converges to exactly `max_current_a` (not some
   permanently-relaxed value) by the final generation — check the actual
   numbers, don't just trust a docstring claim.
5. **No regression.** Confirm existing tests pass, and this doesn't affect
   behavior when `max_current_a is None` (the constraint should not appear
   at all in that case, matching current behavior).
6. **Empirical honesty.** Independently re-run at least one of the
   reported before/after comparisons yourself.
7. **Scope discipline.** No changes to harmonic/margin logic, genetic
   operators, geometry, or physics code.

## Output format

Findings ranked most-severe first. For each: file, line, what's wrong,
concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run at least one
empirical comparison yourself before approving.
