# Codex worker prompt — TASK 0027-optional-blocks-and-turn-budgets

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0027-optional-blocks-and-turn-budgets/TASK.md` in this
worktree fully before writing any code. This is a real genome/architecture
change — read `src/dot/optimize/genome.py`, `problem.py`, and `runner.py`
fully first, and understand how tasks 0022 (mixed-variable genome), 0023
(graded constraints), and 0025 (annealed current cap) already work before
extending them further.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. **Backward compatibility is critical.** Existing fixed-block-count
   usage (especially `n_blocks=1` layers, and campaigns that don't set the
   new budget fields) must behave exactly as before. Run the full existing
   test suite before and after your change and confirm nothing that
   passed before now fails.
3. No live-ROXIE requirement — this is genome/optimizer architecture, not
   physics.
4. Check what pymoo version is installed and what mixed-variable types are
   available (`Binary`, or fall back to `Integer(bounds=(0,1))`) before
   deciding how to represent the active gene — use pymoo's idiomatic
   approach for the installed version, consistent with how task 0022
   already used `Integer` for `n_turns`.
5. Do not implement anything from TASK.md's "Explicit non-goals" —
   no topology-family niching, no staged refinement, no
   `dipole_designer`-style repair/regeneration machinery.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- How the active-block gene is represented (pymoo variable type) and how
  `decode()` handles variable active-block counts.
- The turn-budget constraint implementation (graded, not annealed) and
  where it's checked relative to the existing geometry/current/harmonic/
  margin checks in `_evaluate`.
- Confirmation of backward compatibility: existing tests pass unmodified.
- The empirical check from TASK.md's acceptance criteria: a small
  campaign run showing the final population uses a genuinely varying
  number of active blocks per layer, not a constant count.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The empirical active-block-count variation check, explicitly
