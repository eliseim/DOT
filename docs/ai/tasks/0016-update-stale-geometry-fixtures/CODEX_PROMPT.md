# Codex worker prompt — TASK 0016-update-stale-geometry-fixtures

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0016-update-stale-geometry-fixtures/TASK.md` in this
worktree fully before writing any code. Read the current (already merged
and verified-correct) `src/dot/geometry/primitives.py` to understand the
current turn-generation formula before recomputing expected values.

## Hard rules

1. Only touch the 3 declared test files. Do not touch
   `src/dot/geometry/primitives.py` or any other source file.
2. Each corrected expected value must be independently recomputed from the
   corrected geometry, not just captured from a test run's actual output
   pasted back in as the new expectation without understanding why.
3. For the partitioned-phi-windows test, if the corrected geometry no
   longer shows a material improvement from partitioning, stop and report
   this rather than silently adjusting numbers to pass.
4. Run `pytest` and `ruff check` yourself, report actual output.
5. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the 3 declared test files. A summary explaining how each
of the 4 corrected values was recomputed, and full test output confirming
zero failures.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
