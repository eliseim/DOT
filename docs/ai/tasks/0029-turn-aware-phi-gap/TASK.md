# TASK: Make PhiOrderingRepair's minimum gap turn-count-aware

- **ID**: 0029-turn-aware-phi-gap
- **Status**: draft
- **Model/effort**: Moderate effort. Touches `src/dot/optimize/runner.py`
  (`PhiOrderingRepair`, `_minimum_phi_gap_deg`, and possibly
  `ConstructiveMixedVariableSampling` which shares the same helper). No
  live-ROXIE requirement — optimizer search behavior, not physics.
  Validation is empirical (feasibility survival across generations).

## Background

Task 0028 added `TurnBudgetRepair` to fix a population collapse
(real-objective-individual count -> 0 within a handful of generations)
caused by turn-budget constraint violations after mating. It was merged,
and a real CTH campaign script was updated to use the new `CampaignRepair`
(composing `PhiOrderingRepair` + `TurnBudgetRepair`). The collapse
persisted anyway, at both small (pop=15/gen=5) and moderate (pop=60/gen=30)
scale: `real_F=15` at generation 1 collapsing to `0` by generation 5 and
staying there.

Root cause, confirmed empirically by the coordinator (not Codex) via direct
inspection: `PhiOrderingRepair._repair_sample` (in `src/dot/optimize/runner.py`)
uses `_minimum_phi_gap_deg(radius, cable.insulated_width_inner_mm, min_gap_mm)`
to compute the minimum angular gap to leave between adjacent blocks' phi
anchors after mating. This helper only accounts for **one cable width** —
i.e. the angular footprint of a single turn — regardless of how many turns
either adjacent block actually has. But a block's real angular footprint
scales with its `n_turns` (each turn adds roughly one cable-width's worth of
angle, stacked around the arc). Concretely, for the CTH layer-0 cable at
r=28mm: a single-turn gap is ~4.03deg, but a 25-turn block's real angular
span is ~90deg. `check_feasibility`'s actual geometry check
(`check_turn_non_intersection` in `src/dot/geometry/constraints.py`) checks
true per-turn polygon geometry — it does NOT use this shortcut, so it
correctly flags overlapping turns as infeasible even when
`PhiOrderingRepair` reports the sample as "repaired."

Net effect: after ordinary mixed-variable crossover/mutation, offspring
with any reasonably large `n_turns` (allowed up to
`n_turns_bounds` upper, e.g. 30 in a real campaign) routinely have adjacent
blocks whose phi anchors are only ~4deg apart despite one or both blocks
spanning tens of degrees of real turns — i.e. massive turn-level overlap.
`PhiOrderingRepair` does not catch or fix this because its notion of
"minimum gap" is turn-count-blind. The result: nearly the entire mated
population fails `check_feasibility` (`check_turn_non_intersection`
specifically) every generation, hits the `_PENALTY` short-circuit in
`problem.py`'s `_evaluate` (the geometry-infeasibility branch, which comes
*before* the turn-budget check), and the population never recovers —
exactly the collapse pattern observed, and NOT something task 0028's
turn-budget repair could have fixed, since this is a different constraint
(geometry/turn-overlap) failing for a different reason.

This is the same underlying gap previously logged (but left unfixed, as a
"known gap" for the *default* `ConstructiveMixedVariableSampling`) —
except it turns out `PhiOrderingRepair` (task 0022) shares the exact same
turn-count-blind helper function (`_minimum_phi_gap_deg`), so the gap
exists in both places, and now that the coordinator's own campaign uses
`PhiOrderingRepair`-based repair (not the default sampler alone) at
realistic turn counts, this gap actively breaks the search.

## Goal

1. Make the minimum angular gap enforced by `PhiOrderingRepair` (and, if
   you determine it's needed for consistency, `_ordered_phi_values` /
   `ConstructiveMixedVariableSampling`) account for each block's actual
   `n_turns`-dependent angular footprint, not a fixed single-turn
   placeholder. The gap between two adjacent blocks' phi anchors must be
   large enough that their real turn geometries (given their current
   `n_turns`) cannot overlap — i.e. it should be at least the sum of half
   the angular footprint of each of the two blocks (or another well-
   justified formula — your call, but it must be genuinely sufficient to
   prevent turn-level overlap for realistic turn counts, and you must
   justify the formula against how `check_turn_non_intersection` actually
   computes turn footprints).
2. Since a block's own `n_turns` can itself change during mating/repair
   (mutation, or `TurnBudgetRepair` running after `PhiOrderingRepair` in
   `CampaignRepair`), consider ordering: should turn-budget repair run
   *before* phi-ordering repair instead (so phi-gap decisions are made
   using the final, budget-compliant `n_turns`)? Currently `CampaignRepair`
   runs phi-ordering first, then turn-budget. Determine the correct order
   and update `CampaignRepair` if needed — document your reasoning either
   way.
3. Empirically validate the actual failure mode: construct a repro (a
   small-to-moderate topology with turn counts in the realistic CTH range,
   e.g. up to 25-30 turns/block) showing that, with the *current* (buggy)
   gap calculation, running `CampaignRepair` on mutated/crossed-over
   offspring frequently produces genomes that still fail
   `check_feasibility` due to turn overlap (`check_turn_non_intersection`
   specifically — confirm this is the actual violated check, not
   pole-angle or aperture). Then show that with your fix, repaired
   offspring reliably pass `check_feasibility` (or, if a genuinely tight
   topology makes some offspring unrepairable without other tradeoffs,
   show the *rate* of turn-overlap infeasibility drops dramatically, not
   necessarily to exactly zero).
4. Run the actual smoke test that surfaced this bug and confirm it's
   fixed: `python C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py 60 30 42`
   (read-only reference — this script lives outside the DOT package, do
   not modify it, but do run it to confirm `real_F` no longer collapses to
   0 by generation 5 and stays at 0 through generation 30). Report the
   `real_F`/`feasible` progression you observe.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/runner.py`
- `tests/optimize/test_runner.py`

## Explicit non-goals

- No change to `TurnBudgetRepair` itself (task 0028, already correct for
  what it does) beyond possibly reordering it relative to
  `PhiOrderingRepair` inside `CampaignRepair` if you determine that's
  necessary (see Goal 2).
- No change to the current/harmonic/margin annealing logic (tasks
  0023/0025).
- No change to the active/inactive block genome encoding (task 0027).
- No change to `src/dot/geometry/constraints.py` or any physics/geometry
  ground-truth code — `check_feasibility`/`check_turn_non_intersection`
  are correct; only the repair's approximation of "safe gap" is wrong and
  needs fixing to match reality more closely.
- Do not weaken any existing test's tolerance to force a pass.

## Acceptance criteria

- [ ] `PhiOrderingRepair`'s gap calculation accounts for each adjacent
      block's actual `n_turns`, with a documented, justified formula.
- [ ] Reproduce the current bug (turn-level overlap surviving repair) with
      a small-to-moderate repro at realistic turn counts, then show it's
      fixed (or dramatically reduced with clear justification for any
      residual cases) with your change.
- [ ] `python cth_campaign5.py 60 30 42` (the coordinator's real campaign
      script, read-only reference, path above) no longer shows `real_F`
      collapsing to 0 by generation 5 — report the actual progression.
- [ ] Existing tests (including task 0022's `PhiOrderingRepair` tests and
      task 0028's `TurnBudgetRepair` tests) continue to pass, updated only
      if their fixtures assumed the old (buggy) gap formula.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material

- `src/dot/optimize/runner.py` — `PhiOrderingRepair`, `TurnBudgetRepair`,
  `CampaignRepair`, `_minimum_phi_gap_deg`, `_ordered_phi_values`.
- `src/dot/geometry/constraints.py` — `check_turn_non_intersection`,
  `check_feasibility` — the ground-truth geometry check the repair must
  actually satisfy.
- `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\cth_campaign5.py`
  and `cth_sampler3.py` (read-only, exploratory scratch scripts, not part
  of the DOT package) — the real campaign showing the collapse.
