# Antigravity independent review prompt — TASK 0009-unsupported-conductor-handling

You are reviewing a diff produced by another AI worker (Codex) for DOT,
adding named-conductor resolution and graceful unsupported-conductor
handling across the conductors/optimizer/GUI stack. You did not see the
worker's reasoning — judge only the diff, the repository, and the task
spec. This closes a real correctness gap (silent component mismatching)
found by the coordinator while preparing a real multi-conductor campaign —
treat "does this actually work correctly for CTH_HF + CTH_LF in the same
file" as the central question.

## Inputs

- `docs/ai/tasks/0009-unsupported-conductor-handling/TASK.md`
- The diff/commit on branch `task/0009-unsupported-conductor-handling`.
- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — the
  real file this must work correctly against (read-only).

## What to check

1. **CONDUCTOR parsing correctness.** Re-read the real file's CONDUCTOR
   section yourself. Confirm `resolve_conductor(text, "CTH_LF")` returns
   the *correct* linked strand (`STR01_12`), cable (`CTH_CERN`), and
   remfit (`NBTILHC`, type 1) — not some other row that happens to parse
   without error. Off-by-one column parsing here would silently link the
   wrong strand to the wrong cable.
2. **Unsupported-conductor propagation.** Confirm `resolve_conductor(text,
   "CTH_HF")` returns a clean "unsupported, type 3" result — not an
   uncaught exception, not a silent fallback to a different conductor.
   Trace this result through `objectives.py`, `problem.py`/`runner.py`,
   and the GUI: does "unsupported" reach the GUI's results panel as a
   clear message, or does it get lost/swallowed somewhere in the middle?
3. **Margin proxy correctness with mixed supported/unsupported layers.**
   This is the highest-value check: construct (or find in the diff's own
   tests) a case where the true field-limiting turn is in an unsupported
   layer. Confirm the margin proxy correctly falls back to the
   highest-field turn *among supported layers*, not just silently produces
   a wrong or nonsensical margin. Check the exclusion happens *before* the
   search picks a "best" turn, not as a post-hoc filter that could still
   leave stale state.
4. **No silent regression for the all-supported case.** Run/inspect the
   existing single-conductor tests (from tasks 0004/0005) — do they still
   pass with this refactor? A `LayerConductorData | None` type change
   touches a lot of call sites; check none of them got the None-handling
   backwards (e.g. treating "conductor data present" as "None" by an
   inverted check).
5. **GUI backward compatibility.** Does the new conductor-name field
   default to empty and fall back to the old `first_supported_remfit`
   behavior, as TASK.md specifies, so existing single-conductor-file
   workflows (task 0006/0007) don't break?
6. **Scope discipline.** Only the declared files touched? No Nb3Sn physics
   added?

## Output format

Findings ranked most-severe first — a wrong strand/cable/remfit linkage or
a margin computed from the wrong turn are the most severe class (silent
wrong physics, exactly the kind of bug this task exists to prevent). For
each: file, line, what's wrong, concrete failure scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
