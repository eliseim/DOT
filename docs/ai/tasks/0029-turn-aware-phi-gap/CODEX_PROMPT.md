# Codex worker prompt — TASK 0029-turn-aware-phi-gap

You are implementing a single scoped task inside an isolated git worktree
for the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0029-turn-aware-phi-gap/TASK.md` in this worktree fully
before writing any code. Read `src/dot/optimize/runner.py` fully first —
understand `PhiOrderingRepair`, `TurnBudgetRepair`, `CampaignRepair`, and
`_minimum_phi_gap_deg` completely before changing anything. Also read
`src/dot/geometry/constraints.py`'s `check_turn_non_intersection` and
whatever it calls to build each turn's actual polygon/angular footprint —
your fix must be justified against how that ground-truth check actually
works, not guessed.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. This is a bug fix in an existing repair mechanism, not a new one — keep
   the class structure (`PhiOrderingRepair`, `CampaignRepair`) intact
   unless you have a specific, documented reason to restructure.
3. No live-ROXIE requirement — optimizer search behavior, not physics.
4. Do not touch `src/dot/geometry/constraints.py` — it's correct; you're
   fixing the repair's approximation to match it, not changing ground
   truth.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files
   outside this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- The exact bug (turn-count-blind gap formula) and your fix (the new gap
  formula, and why it's sufficient against `check_turn_non_intersection`'s
  actual turn-footprint geometry).
- Your decision on `CampaignRepair`'s repair order (phi-ordering vs.
  turn-budget first) and why.
- The before/after empirical repro from TASK.md's acceptance criteria:
  turn-overlap infeasibility rate after mating+repair, before and after
  your fix.
- The result of running
  `python C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py 60 30 42`
  (read-only reference script outside the repo) before and after your fix
  — specifically the `real_F`/`feasible` progression printed every 5
  generations. This is the actual real-world symptom this task exists to
  fix, so this check matters more than any synthetic repro.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- The before/after empirical repro, explicitly, including the
  `cth_campaign5.py` run above
