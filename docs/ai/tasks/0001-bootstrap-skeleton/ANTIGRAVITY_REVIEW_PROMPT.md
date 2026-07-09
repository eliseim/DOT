# Antigravity independent review prompt — TASK 0001-bootstrap-skeleton

You are reviewing a diff produced by another AI worker (Codex) for the DOT
(Dipole Optimization Tool) project. You did not see the worker's reasoning or
conversation — judge only the diff, the repository, and the task spec.

## Inputs

- `docs/ai/tasks/0001-bootstrap-skeleton/TASK.md` — the scope and acceptance
  criteria the worker was given.
- The diff produced in worktree `.worktrees/0001-bootstrap-skeleton` (branch
  `task/0001-bootstrap-skeleton`).

## What to check

1. **Correctness.** Does `pip install -e .` actually work with the given
   `pyproject.toml`? Is the `src/`-layout configured correctly for whichever
   build backend was chosen? Does `import dot` resolve, and does
   `dot.__version__` equal `"0.0.1"`?
2. **Scope discipline.** Did the worker touch only files listed under
   "Scope" in TASK.md? Flag any out-of-scope edits — especially watch for
   accidental introduction of pymoo/PySide6/matplotlib/shapely or any
   physics/geometry/optimizer/GUI code, which this task explicitly forbids.
3. **Provenance.** Any sign of copied/vendored code or config from
   `dipole_designer` or `dipole-optimization-tool`?
4. **Tooling correctness.** Is the `[tool.ruff]` config sane? Does
   `ruff check .` actually pass clean, or does the config just suppress
   everything? Is Python floor `>=3.11` respected?
5. **Test quality.** Is the smoke test meaningful (imports the real package,
   checks the real version string), not a tautology?

## Output format

Report findings ranked most-severe first. For each: file, line, what's
wrong, and a concrete failure scenario. End with one of:

- **APPROVE** — safe to merge as-is.
- **APPROVE WITH NITS** — mergeable, minor non-blocking issues listed.
- **REJECT** — must not merge; list exactly what must change and why.

This is a low-risk scaffolding task — do not manufacture severity, but do
not wave through a broken `pip install -e .` or scope creep either.
