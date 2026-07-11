# Antigravity independent review prompt — TASK 0029-turn-aware-phi-gap

You are reviewing a diff produced by another AI worker (Codex) that fixes
a real, coordinator-confirmed bug: `PhiOrderingRepair`'s minimum angular
gap between adjacent blocks only accounted for a single cable width (one
turn), not each block's actual `n_turns`-dependent angular footprint. This
caused post-mating offspring with realistic turn counts (e.g. 25-30
turns/block) to routinely fail `check_turn_non_intersection` (real
turn-level overlap) despite `PhiOrderingRepair` reporting them "repaired,"
collapsing an entire NSGA-II population's real-objective count to 0 within
a handful of generations. No live-ROXIE requirement.

## Inputs

- `docs/ai/tasks/0029-turn-aware-phi-gap/TASK.md` — read fully.
- The diff/commit on branch `task/0029-turn-aware-phi-gap`.

## What to check

1. **Gap formula correctness.** Confirm the new gap formula is actually
   sufficient to prevent turn-level overlap given how
   `check_turn_non_intersection` (in `src/dot/geometry/constraints.py`)
   computes real turn footprints — don't just trust Codex's stated
   justification, verify it yourself (read the actual turn-geometry
   construction code, e.g. how `block.turns()` places each turn
   angularly).
2. **Empirical validation — the core check.** Independently construct a
   repro: build a topology/genome with blocks carrying realistic turn
   counts (20-30 turns), run mating + `CampaignRepair`, and confirm
   post-repair genomes pass `check_feasibility` (specifically
   `check_turn_non_intersection`) at a much higher rate than before the
   fix. Don't rely solely on Codex's reported numbers.
3. **Repair order.** Confirm `CampaignRepair`'s repair order (phi-ordering
   vs. turn-budget) is justified given that changing `n_turns` after
   phi-ordering repair could invalidate the gap decisions phi-ordering
   made (or vice versa) — check whichever order was chosen actually
   avoids this.
4. **Real campaign check.** Run
   `python C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py 60 30 42`
   yourself (read-only script outside the repo, do not modify) and confirm
   `real_F` no longer collapses to 0 by generation 5 — this is the actual
   symptom that motivated this task; a fix that doesn't resolve it in
   this real script is not actually fixing the problem, regardless of
   synthetic repro results.
5. **Scope discipline.** No changes to `TurnBudgetRepair`'s own reduction
   logic (task 0028), no changes to `check_turn_non_intersection` or other
   geometry ground-truth code, no changes to admission-threshold annealing
   (tasks 0023/0025), no changes to the active/inactive block genome
   encoding (task 0027).

## Output format

Findings ranked most-severe first — a gap formula that's still
insufficient (overlap survives repair) for some realistic turn-count
range, or one that doesn't actually fix the `cth_campaign5.py` collapse
when you run it yourself, are the most severe possible findings here. For
each: file, line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — construct your own repro
and run the real campaign script yourself before approving.
