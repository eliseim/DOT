# Antigravity independent review prompt — TASK 0019-keystone-tilt-multiturn-stacking

You are reviewing a diff produced by another AI worker (Codex) fixing a
multi-turn block stacking bug in DOT's core geometry
(`src/dot/geometry/primitives.py::Block.turns()`) — a bug that a *previous*
Antigravity review (task 0018) found on its own initiative while checking
generalization. This is the **third** modification to this file (after
tasks 0015 and 0017, both independently validated). Same rigor bar as
before, raised if anything: independently re-derive, pull live ROXIE data
yourself, don't just trust reported numbers. A regression here would corrupt
every bore-field and margin result validated so far in this project — treat
that as the single most severe possible finding.

## Inputs

- `docs/ai/tasks/0019-keystone-tilt-multiturn-stacking/TASK.md` — read
  fully, including the diagnostic (real ROXIE conductor coordinates for
  `cth_lf_custom_two_turns_block`, the wrong `width/radius` formula, the
  `3.316 deg` vs `~5.78-6.027 deg` discrepancy).
- The diff/commit on branch `task/0019-keystone-tilt-multiturn-stacking`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Hand-derivation correctness.** Independently re-derive the correct
   arc-tangent projection formula yourself (don't just check Codex's
   derivation reads plausibly — do the geometry independently and compare
   results).
2. **Live ROXIE validation — run it yourself, including your own new
   case.** Reproduce `cth_lf_custom_two_turns_block` and confirm the fix.
   Then construct at least one multi-turn case Codex did NOT test
   (different radius/phi/n_turns combination) to check the fix
   generalizes rather than being tuned to the one known failing case —
   this is exactly the kind of check that found this bug in the first
   place during task 0018's review, so apply the same standard here.
3. **Regression — the most severe possible finding.** Re-run, live against
   ROXIE, at minimum: the CTH-14T real design case (tasks 0015/0017,
   should be ~0.456%), one of the original single-block cases from tasks
   0015/0017, and at least one single-turn case from task 0018 (should be
   <0.5% peak field, <0.15pp margin). Any of these regressing is grounds
   for REJECT regardless of how well the new multi-turn case performs.
4. **Mechanism, not just numbers.** Check whether the fix is a genuine,
   general geometric correction (works because the derivation is right) or
   narrowly tuned to pass the one reported case.
5. **Scope discipline.** Only declared files touched? No changes to
   `src/dot/optimize/objectives.py` (task 0018, already merged) or to
   `TurnPolygon.from_anchor`'s trapezoid construction (task 0017) unless
   clearly justified and explained?
6. **Honesty check.** If the diff's summary reports the 2%/2pp bar was not
   fully achieved for some geometry, verify that's a genuine residual
   (not a weakened tolerance or cherry-picked case).

## Output format

Findings ranked most-severe first — a regression on any previously-validated
case is the most severe possible finding here, full stop. For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run your own live ROXIE
checks for the failing case, at least one new multi-turn case, and all
regression cases listed above before approving.
