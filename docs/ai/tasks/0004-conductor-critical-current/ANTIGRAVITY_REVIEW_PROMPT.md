# Antigravity independent review prompt — TASK 0004-conductor-critical-current

You are reviewing a diff produced by another AI worker (Codex) for DOT's
conductor critical-current / load-line margin module. You did not see the
worker's reasoning — judge only the diff, the repository, and the task
spec. The user has explicitly flagged that this area's correctness in prior
tools is unverified — apply the same skepticism here. Load-line margin is a
core design objective; if this silently overstates margin, DOT could report
a design as safe when it is actually quench-prone.

## Inputs

- `docs/ai/tasks/0004-conductor-critical-current/TASK.md`
- The diff/commit on branch `task/0004-conductor-critical-current`.

## What to check

1. **Formula fidelity.** Re-derive the Bottura Nb-Ti formula from TASK.md
   yourself and check the implementation matches term-for-term: exponents
   (`C3-1` on B, `C4` on `(1-b)`, `C5` on `(1-t^1.7)`), where `C6`
   multiplies, and `Bc2(T) = C7*(1-t^1.7)` used consistently everywhere
   `Bc2` appears (not recomputed differently in two places).
2. **Boundary/limit behavior**, checked by direct substitution: does
   `Jc -> 0` as `B -> Bc2(T)`? As `T -> Tc0`? Is `Jc` real/finite/positive
   in the physical domain? Could `B^(C3-1)` misbehave for `C3 < 1` at
   `B -> 0` (fractional power of a value near zero) — is this handled or
   does it silently produce `inf`/`nan` for realistic coefficient ranges?
3. **Units.** `C1` is A/m^2 per TASK.md — confirm `B` is in tesla and
   temperature in kelvin consistently, and confirm the strand area
   (mm^2 from a mm diameter) is properly converted to m^2 before
   multiplying by `Jc` (A/m^2) to get amperes. A missed mm^2->m^2 factor of
   1e-6 is the single most likely silent bug here — check explicitly.
4. **Cu:SC ratio interpretation.** Confirm the superconductor area fraction
   is computed correctly: for a Cu:SC ratio of e.g. 1.5:1, superconductor
   fraction should be `1/(1+1.5) = 0.4` of total strand area — verify the
   code doesn't invert this ratio.
5. **`.cadata` parsing.** Does it correctly reject/flag any non-type-1
   REMFIT record rather than silently mis-parsing its coefficients as if
   they were type-1 (which would silently corrupt every downstream Jc/
   margin computation for that cable)? Construct (mentally or by running)
   a type-11-record fixture and confirm the parser actually raises.
6. **Bisection solver correctness.** Does `solve_short_sample_current`
   actually bracket a root (sign change at `i_lo`/`i_hi`)? What happens if
   no root exists in range (e.g. `i_hi` too small) — does it fail loudly or
   silently return a wrong boundary value? Is the margin formula
   `100*(1 - I_op/I_ss)` applied correctly (verify sign: margin should be
   positive when `I_op < I_ss`, i.e. operating safely below quench)?
7. **Test quality & independence.** Are the "expected" numbers in tests
   computed via a separate inline formula/method from the implementation
   under test, or do they call the same helper (tautological)? Are
   boundary/monotonicity tests actually exercising two distinct points, not
   trivially the same value twice?
8. **Scope & provenance.** Only declared files touched? No ROXIE
   dependency? Formula independently re-derived, not copied from the
   reference tool (which itself admits this area is unvalidated)?

## Output format

Findings ranked most-severe first (formula/units/sign bugs that would
overstate margin first — these are the most dangerous class). For each:
file, line, what's wrong, concrete failure scenario (what unsafe design DOT
would report as having adequate margin). End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve on "tests pass" alone. A test suite that validates a formula
against itself proves nothing about whether the formula is the physically
correct one — check the physics, not just internal consistency.
