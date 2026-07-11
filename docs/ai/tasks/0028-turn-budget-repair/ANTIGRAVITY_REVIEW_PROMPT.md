# Antigravity independent review prompt — TASK 0028-turn-budget-repair

You are reviewing a diff produced by another AI worker (Codex) that adds
a turn-count budget repair mechanism to DOT's optimizer, following the
precedent of `PhiOrderingRepair` (task 0022). This fixes a real,
reproduced population-collapse bug found during real CTH campaign work:
turn-budget constraints (task 0027) had no repair, so ordinary
crossover/mutation destroyed budget compliance every generation with no
recovery mechanism. No live-ROXIE requirement.

## Inputs

- `docs/ai/tasks/0028-turn-budget-repair/TASK.md` — read fully.
- The diff/commit on branch `task/0028-turn-budget-repair`.

## What to check

1. **Repair correctness.** Confirm the repair genuinely reduces
   over-budget `n_turns` values to within budget, respects each block's
   own lower bound, and doesn't produce an invalid genome (e.g. negative
   turns, or turns below the topology's declared minimum).
2. **Reduction rule justification.** Confirm the chosen rule (whichever
   Codex picked) is reasonable and documented — not an arbitrary,
   unexplained heuristic.
3. **Composition with `PhiOrderingRepair`.** Confirm both repairs run
   correctly together (order matters if one could undo the other's work —
   check for this) and that existing `PhiOrderingRepair` tests still
   pass unmodified.
4. **Empirical reproduction — the core check.** Independently reproduce
   the collapse yourself (construct your own small repro, not necessarily
   identical to Codex's) and confirm: without the repair, real-objective
   individuals collapse toward 0 within a handful of generations; with
   it, the population stays healthy across a realistic generation count.
5. **Scope discipline.** No changes to the current/harmonic/margin
   annealing logic (tasks 0023/0025), no changes to the active/inactive
   block genome encoding (task 0027), no physics/geometry changes.

## Output format

Findings ranked most-severe first — a repair that produces an invalid
genome (e.g. violates a lower bound), or one that doesn't actually fix
the empirical collapse when you test it yourself, are the most severe
possible findings here. For each: file, line, what's wrong, concrete
consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — construct your own repro
and confirm the fix works before approving.
