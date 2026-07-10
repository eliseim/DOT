# Antigravity independent review prompt — TASK 0018-peak-field-and-loadline-margin-parity

You are reviewing a diff produced by another AI worker (Codex) fixing DOT's
peak-field-on-conductor and load-line-margin calculation, which was found to
be badly wrong (0/28 cases within 2% before this fix, mean peak-field error
66.5%) despite the already-merged, twice-validated bore-field geometry being
solid (200/200 within 2%, tasks 0015/0017). Same rigor bar as before:
independently re-derive, pull live ROXIE data yourself, don't just trust
reported numbers. This diff carries real risk of a worker "converging" the
numbers just enough to clear 2% without the underlying model actually being
right — scrutinize the fix's mechanism, not just its output numbers.

## Inputs

- `docs/ai/tasks/0018-peak-field-and-loadline-margin-parity/TASK.md` — read
  fully, including the diagnostic history (the 3x3-discretization bug and
  the residual ~3.5-4.4% gap found even at converged discretization).
- The diff/commit on branch
  `task/0018-peak-field-and-loadline-margin-parity`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Hand-derivation correctness.** Independently re-derive (on paper/by
   hand, not by re-running Codex's code) the expected peak field for at
   least one simple single-turn case with known geometry and current.
   Compare against the implementation's output.
2. **Mechanism, not just numbers.** Understand *why* the fix works, not just
   that it reports <2%. If Codex's fix is "raise n1/n2 until the number
   happens to land under 2% for the tested cases," that is not an
   acceptable fix — check whether the claimed root cause is genuinely
   understood and whether the fix would generalize to other geometries, or
   whether it's tuned to the specific test cases.
3. **Live ROXIE validation — run it yourself.** Submit your own live ROXIE
   jobs for at least 5 cases: reproduce Codex's reported cases where
   possible, and add at least one case Codex did NOT test (different
   radius/phi/turn-count) to check the fix generalizes rather than being
   overfit to the reported cases.
4. **No regression on bore-field parity.** Run the existing bore-field
   live-ROXIE tests
   (`tests/physics/test_roxie_parity_live.py`,
   `tests/physics/test_roxie_parity_cth14t.py`) yourself and confirm they
   still pass with the same (or better) numbers as before this diff. This
   is the most severe possible finding here, per binding precedent from
   task 0017's review.
5. **Honesty check.** If the diff's summary reports the 2%/2pp bar was not
   fully achieved, verify that claim is genuine (i.e. the worker did not
   quietly weaken a tolerance or cherry-pick easy cases) rather than
   penalizing honest reporting of a real residual.
6. **Scope discipline.** Only declared files touched? No changes to the
   bore-field/harmonics code path (`multipole_coefficients`, the
   superposition-based `field_at` call sites used for total field)?
7. **Nb3Sn note handled correctly.** Confirm the diff does NOT attempt a
   Nb3Sn/type-56 critical-current fit (explicitly out of scope) and that
   `resolve_conductor` still degrades cleanly (not a crash) for CTH_HF.

## Output format

Findings ranked most-severe first — a regression on the already-validated
bore-field cases, or a fix that only works by coincidence/overfitting to the
reported test cases, are the most severe possible findings here. For each:
file, line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run your own live ROXIE
checks for at least 5 cases including at least 1 not already tested by
Codex, and independently hand-derive at least 1 case's expected peak field
before approving.
