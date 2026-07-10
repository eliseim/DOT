# Antigravity independent review prompt — TASK 0015-absolute-alpha-and-chord-stacking

You are reviewing a diff produced by another AI worker (Codex) fixing a
major, verified geometry bug in DOT's core turn-generation code
(`src/dot/geometry/primitives.py`) — foundational, already-merged, used by
every downstream module. This is the highest-stakes review of the session:
a wrong sign or wrong axis here silently produces wrong physics for every
future DOT design. You did not see the worker's reasoning — judge only the
diff, the repository, and the task spec, but you have live ROXIE access and
should use it.

## Inputs

- `docs/ai/tasks/0015-absolute-alpha-and-chord-stacking/TASK.md` — contains
  the coordinator's full derivation with exact formulas and a verified
  numeric example. Re-derive this yourself, don't just trust it.
- The diff/commit on branch `task/0015-absolute-alpha-and-chord-stacking`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first; if unreachable, say so explicitly and do as much static
  verification as possible, but flag that the live-validation claim in
  Codex's summary could not be independently confirmed).

## What to check — be maximally skeptical, re-derive everything

1. **Re-derive the height_axis/width_axis formulas yourself from scratch.**
   Do not just check that the code matches TASK.md's formula — TASK.md's
   formula could itself be wrong. Starting from
   `dipole_designer/dipole_optimizer/core/geometry_helpers.py`'s
   `_alpha_height_vector_mm`/`_width_axis_vector_mm` (ROXIE's raw
   `phi_roxie`/`alpha_roxie` convention) and the already-validated
   `phi_dot_deg = 90 - phi_roxie_deg`, `alpha_dot_deg = -alpha_roxie_deg`
   relations (from task 0008), independently substitute and simplify to
   get the DOT-convention formula. Confirm you arrive at
   `height_axis(alpha_dot) = (cos(alpha_dot), -sin(alpha_dot))` and
   `width_axis(alpha_dot) = (sin(alpha_dot), cos(alpha_dot))` — if you get
   something different, that is a critical finding, not a nitpick.
2. **Numerically spot-check** with at least one value not already used in
   TASK.md's worked example (pick a different real CTH block, e.g.
   `phi_roxie=33.9911, alpha_roxie=42.3351`) and confirm the implementation
   produces the expected phi-independent height axis.
3. **Confirm phi-independence directly in the code**, not just by output
   value — trace whether the implementation's height_axis/width_axis
   computation still has any `phi_deg` term in it anywhere (even
   multiplied by zero or cancelled algebraically — check the actual
   expression, not just one evaluated output).
4. **Chord-stacking correctness.** Confirm turn `k`'s anchor is computed as
   a Cartesian offset from turn 0's anchor, not via any remaining
   phi-recomputation per turn. Check the off-by-one: is turn index 0 truly
   unshifted, and is the step applied `k` times (not `k+1` or `k-1`) for
   turn `k`?
5. **Live ROXIE validation — run it yourself, independently.** Do not just
   trust Codex's reported numbers. Submit your own live ROXIE job (real
   CTH-14T geometry, genuinely iron-free per TASK.md's template recipe)
   and independently compute DOT's field for the same geometry using the
   fixed code. Compare your own numbers to Codex's reported numbers — do
   they match? Is the result actually within 2%, or does Codex's summary
   overstate it?
6. **Check the alpha=0 isolation case** (single block, alpha=0) separately
   — confirm this case's accuracy improvement (or lack thereof) is
   consistent with it isolating the chord-stacking fix alone (since
   alpha=0 makes the two fixes' height_axis/width_axis formulas coincide
   with the old ones — verify this claim algebraically: at alpha=0, does
   `(cos(0), -sin(0)) = (1,0)` match what the OLD phi-dependent formula
   would give at alpha=0 too? If yes, this case only exercises the
   chord-stacking fix, which is exactly the diagnostic value TASK.md
   claims — confirm or refute this reasoning explicitly).
7. **Test independence.** Are the expected values in the new unit tests
   computed via a formula/method independent of the implementation under
   test (e.g., plain inline trig, not calling the same helper)?
8. **Scope discipline & the live-ROXIE test's skip behavior.** Only
   declared files touched? Does the new live-ROXIE test actually skip
   cleanly (not fail, not error) when the service is unreachable — verify
   this by reasoning through the skip-check code, and if you can, by
   actually testing against a deliberately-wrong port/URL.

## Output format

Findings ranked most-severe first — any sign error, axis swap, or
off-by-one in the geometry formulas is critical (silently wrong physics
for every future design). For each: file, line, what's wrong, concrete
consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on "the reported live-ROXIE number looks good" without
running your own independent live-ROXIE check. If you cannot reach the
ROXIE service yourself, say so explicitly in your verdict and treat the
live-validation claim as unverified rather than confirmed.
