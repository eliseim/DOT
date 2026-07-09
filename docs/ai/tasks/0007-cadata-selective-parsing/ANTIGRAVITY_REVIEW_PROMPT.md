# Antigravity independent review prompt — TASK 0007-cadata-selective-parsing

You are reviewing a diff produced by another AI worker (Codex) for a
bug-fix task in DOT's `.cadata` parser. You did not see the worker's
reasoning — judge only the diff, the repository, and the task spec.

## Inputs

- `docs/ai/tasks/0007-cadata-selective-parsing/TASK.md`
- The diff/commit on branch `task/0007-cadata-selective-parsing`.

## What to check

1. **The exact bug is actually fixed.** Confirm a test loads the real
   `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` file
   and successfully resolves its type-1 record by name, and that this test
   would have failed before the fix (trace through the old vs new logic).
2. **No silent over-permissiveness introduced.** If the caller asks for a
   record by name and that specific record IS an unsupported type, does it
   still raise `UnsupportedFitTypeError` clearly? A fix that makes
   unsupported-type errors "go away" by silently skipping them entirely
   (rather than only skipping *unrelated* records) would be a correctness
   regression, not a fix — verify this distinction is actually preserved.
3. **Name matching correctness.** Is the record-name lookup exact-match,
   case-sensitive/insensitive as appropriate for the real file's format? A
   mismatch here could silently resolve to the wrong conductor's
   coefficients (wrong Jc fit applied to a design — high severity).
4. **GUI wiring.** Does `_campaign_inputs()` correctly pass through to the
   new API in a way that doesn't just move the same eager-parse-everything
   behavior one level up?
5. **Scope discipline.** Only `src/dot/conductors/cadata.py`,
   `tests/conductors/test_cadata.py`,
   `src/dot/gui/target_synthesis_gui.py`, and
   `tests/gui/test_target_synthesis_gui.py` touched?

## Output format

Findings ranked most-severe first (wrong-conductor-resolved bugs and
unsupported-type-silently-ignored bugs are most severe). For each: file,
line, what's wrong, concrete failure scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
