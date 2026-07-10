# Antigravity independent review prompt — TASK 0023-graded-staged-admission-thresholds

You are reviewing a diff produced by another AI worker (Codex) that adds
graded constraint severity and staged/annealed admission thresholds to
DOT's optimizer, touching `src/dot/geometry/constraints.py` — a
previously-validated file. This is optimizer search-behavior code, not
ROXIE-parity physics, so there is no live-ROXIE requirement — but the
no-regression bar on `constraints.py` is strict.

## Inputs

- `docs/ai/tasks/0023-graded-staged-admission-thresholds/TASK.md` — read
  fully.
- The diff/commit on branch
  `task/0023-graded-staged-admission-thresholds`.

## What to check

1. **`constraints.py` backward compatibility — most severe check.**
   Confirm `is_feasible`'s boolean result is unchanged for every existing
   test case (run the existing constraint test suite yourself). Confirm
   the new severity field is populated from the same numeric value
   already computed in each `check_*` function (not reverse-engineered
   from a message string, not a separately-recomputed value that could
   drift from the actual boolean check).
2. **Graded `G` correctness.** Confirm two infeasible genomes of
   different severity get distinguishable `G` values now, and that a
   feasible genome's `G` is still `<= 0` (or whatever pymoo's convention
   is) consistent with before.
3. **Annealing schedule correctness.** Confirm the threshold genuinely
   relaxes early and tightens to the user's true target by the final
   generation — check the actual schedule values at a few generation
   indices, don't just trust a docstring claim.
4. **No regression.** Run `pytest -q` yourself; confirm `constraints.py`'s
   existing test file passes unmodified (or only extended, not weakened).
5. **Empirical honesty.** Independently re-run at least one of the
   reported before/after comparisons yourself.
6. **Scope discipline.** No operator/sampler changes (task 0022's scope),
   no physics changes, no change to the underlying geometry math.

## Output format

Findings ranked most-severe first — a change to `is_feasible`'s boolean
semantics for any existing case is the most severe possible finding here.
For each: file, line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run the existing
constraint test suite and at least one empirical comparison yourself
before approving.
