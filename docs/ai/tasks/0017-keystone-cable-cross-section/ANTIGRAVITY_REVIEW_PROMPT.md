# Antigravity independent review prompt — TASK 0017-keystone-cable-cross-section

You are reviewing a diff produced by another AI worker (Codex) adding
keystoned (trapezoid) cable cross-section modeling — another change to
DOT's core geometry, building directly on task 0015 (already merged and
approved). Same rigor bar as before: independently re-derive, pull live
ROXIE data yourself, don't just trust reported numbers.

## Inputs

- `docs/ai/tasks/0017-keystone-cable-cross-section/TASK.md`
- The diff/commit on branch `task/0017-keystone-cable-cross-section`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Trapezoid geometry correctness.** For a hand-picked case with
   `width_inner_mm != width_outer_mm`, independently compute the expected
   4 corners and compare against the implementation's output.
2. **Stacking step uses inner width specifically**, not an average or the
   outer width — check this in the actual `Block.turns()` code (both the
   simple-arc branch and the `_arc_stacked_anchor` fallback), not just in
   one of them.
3. **Live ROXIE validation — run it yourself.** Submit your own live
   ROXIE jobs for the 3 new single-turn cases (r=35/phi=40, r=40/phi=30,
   r=45/phi=50, CTH_HF, alpha=0, n_turns=1, 5T) and the 2 regression cases
   from task 0015 (real CTH-14T design, the original alpha=0 6-turn
   single-block case at r=30/phi=45). Compare your own numbers to Codex's
   reported numbers. All 5 must be under 2%.
4. **No regression on the already-approved task 0015 cases** — this is
   the most important check, since this diff touches the same file that
   task 0015 fixed after two review rounds. If either regression case now
   fails, this is a REJECT regardless of how well the new cases pass.
5. **GUI insulation-thickness fix.** Confirm
   `_cable_spec_from_cadata_text` now reads the real `INSUL` section
   instead of hardcoding `0.0` — test against the real
   `roxie_CTH_cables.cadata` file's `INSXF145` record (expect 0.145mm),
   not a synthetic fixture alone.
6. **Scope discipline.** Only declared files touched? No changes to the
   absolute-alpha/arc-stacking logic itself?

## Output format

Findings ranked most-severe first — a regression on the already-validated
task 0015 cases is the most severe possible finding here. For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run your own live ROXIE
checks for at least the 2 regression cases and at least 1 new case.
