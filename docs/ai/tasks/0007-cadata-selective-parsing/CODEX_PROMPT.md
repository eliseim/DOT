# Codex worker prompt — TASK 0007-cadata-selective-parsing

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0007-cadata-selective-parsing/TASK.md` in this worktree fully
before writing any code. This is a bug-fix task from a real repro found by
manually driving the merged GUI against the actual reference `.cadata` file.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Still only support REMFIT type 1 (Nb-Ti). The fix is about *which*
   record gets validated when, not about supporting more fit types.
3. Reproduce the exact bug with the real file
   `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata`
   (read-only) in a test before fixing it, then show the same test passes
   after the fix.
4. Write the tests specified in TASK.md's acceptance criteria, run `pytest`
   and `ruff check` yourself, report actual output.
5. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the new
selective-parsing API shape, how the GUI's `_campaign_inputs()` now uses it
(and whether you added a cable-name field or resolve "the first supported
record" — state your choice and why), and full test output including the
real-file regression test.

## Task-specific instructions

1. In `src/dot/conductors/cadata.py`, change parsing so that scanning for a
   specific named cable's fit coefficients does not eagerly validate every
   other REMFIT record's fit type in the file. A reasonable shape: keep
   section-splitting logic, but only construct/validate a
   `Type1FitCoefficients` for the record whose name matches what the caller
   asked for; other records' rows can be skipped without inspection beyond
   what's needed to know they're a different record (i.e., don't call the
   type-1-specific coefficient parser on a row you're not going to use).
   Keep `UnsupportedFitTypeError` behavior for the case where the
   specifically-requested record itself is unsupported.
2. Update `src/dot/gui/target_synthesis_gui.py`'s `_campaign_inputs()` to
   use the new API instead of the current whole-file eager parse.
3. Add the real-file regression test using
   `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata`
   (read the file's content at test time from that path; don't copy it
   into the repo).

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + all previously merged tests must still pass)
