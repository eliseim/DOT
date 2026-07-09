# Antigravity independent review prompt — TASK 0005-optimizer-core

You are reviewing a diff produced by another AI worker (Codex) for DOT's
optimizer core — the integration point where geometry, physics, feasibility
constraints, and load-line margin all get wired into an NSGA-II search. You
did not see the worker's reasoning — judge only the diff, the repository,
and the task spec. This is an integration task: individually-correct
modules can still be wired together incorrectly.

## Inputs

- `docs/ai/tasks/0005-optimizer-core/TASK.md`
- The diff/commit on branch `task/0005-optimizer-core`.
- The already-merged modules it builds on: `src/dot/geometry/`,
  `src/dot/physics/`, `src/dot/conductors/` — read their actual public APIs
  to check the new code calls them correctly (right argument order, right
  units, right meaning of returned values).

## What to check

1. **Operating-current linear scaling.** Is the "field is exactly linear in
   current for no-iron" claim actually correctly exploited? Check: does the
   code evaluate the field at 1 A (or any known current) and scale
   correctly (`target_field / field_at_reference_current *
   reference_current`), and is that scale factor applied to *every* turn's
   current, not just some? A partial current update (e.g. scaling one
   block but not others) would silently produce a design that doesn't
   actually hit its target field. This is the single highest-value thing to
   verify in this review.
2. **Feasibility gating.** Does an infeasible decoded design actually
   short-circuit before objectives are computed with garbage/undefined
   geometry (e.g. self-overlapping turns feeding into the field solver),
   or could `check_feasibility`'s violation be computed but still let a
   bad design silently receive a competitive objective score anyway (check
   `problem.py`'s `G`/`F` construction directly)? A candidate marked
   infeasible must not out-compete a feasible one in the Pareto ranking due
   to an artificially good `F` value.
3. **Objective sign/direction.** Confirm both `F` values are to be
   *minimized* by pymoo convention: field-quality (raw max|harmonic|, lower
   is better, correct as-is) and margin (must be negated: `-margin_percent`,
   since higher margin is better) — check the actual sign used in
   `problem.py`, not just `objectives.py`'s docstring claim.
4. **Genome decode correctness.** Round-trip a genome through decode and
   manually verify the resulting `DipoleDesign`'s block `phi_deg`/
   `n_turns`/layer radii match what the genome encoded — off-by-one errors
   in indexing blocks/layers within the flattened genome array are the
   classic bug here.
5. **Margin proxy honesty.** TASK.md requires the margin objective to use
   the peak field found anywhere on the coil's own turns (a simple,
   explicitly-approximate proxy). Confirm the code actually searches across
   all turns for the peak field rather than assuming e.g. only the
   innermost/first turn is field-limiting (which is often true but not
   always, depending on geometry) — if it hardcodes an assumption, check if
   it's at least documented as such.
6. **Test independence.** Are the "expected" values in tests computed by
   calling the *same* code path under test, or independently (e.g. calling
   `field_at`/`multipoles`/`loadline` functions directly with the same raw
   inputs, separate from going through the full `problem.py` pipeline)?
7. **Scope discipline & provenance.** Only declared files + the
   `pyproject.toml` `pymoo` addition touched? No topology search
   introduced despite being explicitly out of scope? No ROXIE dependency?

## Output format

Findings ranked most-severe first — anything that could make an infeasible
or non-target-hitting design look like a good/feasible Pareto candidate is
critical. For each: file, line, what's wrong, concrete failure scenario.
End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve on "tests pass" alone — trace the actual data flow from
genome to Pareto output at least once by hand/reasoning.
