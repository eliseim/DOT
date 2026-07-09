# TASK: Conductor critical-current (Jc) fit and load-line margin

- **ID**: 0004-conductor-critical-current
- **Status**: draft
- **Model/effort**: High effort for both Codex and Antigravity. Load-line
  margin is one of DOT's three core design objectives (alongside field
  strength and field quality); a wrong Jc fit silently reports a design as
  having margin it doesn't actually have. The user explicitly flagged that
  the prior tool's handling of this is of uncertain correctness — do not
  trust it, re-derive from the published physics.

## Goal

Give DOT a native (ROXIE-free) way to compute, for a Nb-Ti superconducting
cable, its critical current `Ic` at a given peak field and temperature, and
the load-line margin at a given operating current — i.e. answer "how close
to quench is this conductor at this operating point".

Physics: superconductor critical current density `Jc(B, T)` follows a
published empirical scaling law (the Bottura fit for Nb-Ti, used by ROXIE's
`.cadata` `REMFIT` type-1 records):

```
b(B, T) = B / Bc2(T)
t(T)    = T / Tc0
Bc2(T)  = C7 * (1 - t^1.7)
Jc(B,T) = C1 * C6 * B^(C3-1) / Bc2(T)^C3 * (1 - b)^C4 * (1 - t^1.7)^C5
```

where `C1..C7` are per-conductor fit coefficients read from a `.cadata` file
(`C1`=Jc scale [A/m^2], `C2`=Tc0 [K], `C3`=alpha, `C4`=beta, `C5`=gamma,
`C6`=normalization, `C7`=Bc20 [T]). This is the ONLY fit type in scope (see
non-goals). A real example (from `roxie_CTH_cables.cadata`, for reference
only, do not hardcode as a magic default):
`C1=3e9, C2=9.2, C3=0.57, C4=0.9, C5=2.32, C6=27.04, C7=14.5`.

Strand critical current: `Ic_strand = Jc(B,T) * A_superconductor`, where
`A_superconductor` is the strand's superconductor cross-section area,
derived from strand diameter and copper-to-superconductor ratio. Cable
critical current: `Ic_cable = n_strands * Ic_strand`, optionally reduced by
a cabling degradation percentage.

Load-line margin: for an operating current `I_op` and a linear field-per-
current coefficient `k` (T/A, i.e. peak field on the conductor scales as
`B_peak = k * I_op` — this `k` is supplied by the caller, computed
elsewhere from the field solver, not derived in this task), find the
short-sample current `I_ss` where `Ic_cable(k * I_ss, T) = I_ss` (the
current at which the operating load-line intersects the critical-current
curve), by root-finding (bisection is sufficient — no SciPy dependency
needed). Margin percentage: `100 * (1 - I_op / I_ss)`.

## Scope (files/modules Codex may touch)

- `src/dot/conductors/__init__.py`
- `src/dot/conductors/cadata.py` — minimal `.cadata` reader: parses
  `STRAND` (diameter, Cu/SC ratio), `CABLE` (strand count, degradation %),
  and `REMFIT` (fit type + C1..C7, **type 1 only**) sections into plain
  dataclasses. Ignore all other sections (`INSUL`, `FILAMENT`, `TRANSIENT`,
  `QUENCH`, `CONDUCTOR`, etc.) for this task.
- `src/dot/conductors/critical_surface.py` — the Bottura Nb-Ti `Jc(B, T)`
  function above.
- `src/dot/conductors/critical_current.py` — strand/cable `Ic` composition.
- `src/dot/conductors/loadline.py` — short-sample current + margin
  bisection solver.
- `tests/conductors/test_cadata.py`
- `tests/conductors/test_critical_surface.py`
- `tests/conductors/test_critical_current.py`
- `tests/conductors/test_loadline.py`

## Explicit non-goals

- **Nb3Sn / REMFIT type 11 or any other fit type is explicitly out of
  scope.** If a `.cadata` file contains a non-type-1 REMFIT record, the
  parser must raise a clear, typed exception (e.g.
  `UnsupportedFitTypeError`) naming the type it doesn't support — never
  silently ignore it or fall back to a guess. This mirrors the honesty the
  reference tool itself uses for this exact gap.
- No wiring into the optimizer or GUI yet.
- No geometry/field-solver code (the `k` field-per-current coefficient is
  a parameter passed in, not computed here).
- No ROXIE dependency, no ROXIE `.output` parsing.
- Do not try to also validate against `dipole-optimization-tool`'s numeric
  test fixtures — that tool's own code/ADR admits this area lacks external
  validation. Validate against the published formula and internally
  consistent physical sanity checks instead (see acceptance criteria).

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — a
  real example `.cadata` file with a type-1 REMFIT record, for
  understanding the on-disk format/column layout only.
- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\io\cadata_reader.py`
  — read for parsing conventions (whitespace/column handling) only; this
  reader does not itself parse REMFIT, so there's little to copy.
- `C:\Users\elisei\Desktop\dipole-optimization-tool\src\dipole_opt\conductors\critical_surfaces.py`,
  `critical_currents.py`, `loadlines.py` — read to see one implementation
  of this same formula/algorithm and to understand what NOT to trust
  blindly (per the user: correctness here is unverified). Re-derive
  independently from the formula given above; do not copy code or treat
  its test fixtures as ground truth.

## Acceptance criteria

- [ ] `Jc(B, T)` matches the formula above exactly for at least 3 hand/
      independently-computed `(B, T, C1..C7)` combinations, computed in the
      test using a plain inline expression separate from the
      implementation's internal code path (not by importing and calling a
      shared helper both sides use).
- [ ] Physical sanity boundary tests: `Jc -> 0` as `B -> Bc2(T)` (b -> 1);
      `Jc -> 0` as `T -> Tc0` (t -> 1); `Jc` is finite and positive for
      `0 < B < Bc2(T)` and `0 <= T < Tc0`; `Jc` strictly decreases as `B`
      increases at fixed `T` (monotonicity check via two sample points, not
      just one).
- [ ] `.cadata` parser correctly extracts a type-1 REMFIT record's 7
      coefficients from a realistic fixture string (inline test fixture,
      not requiring the actual `dipole_designer` file on disk) and raises
      `UnsupportedFitTypeError` (or similar) for a type-11/other record,
      never silently mis-parsing it as type 1.
- [ ] `Ic_strand`/`Ic_cable` composition tested against a hand-computed
      example (given strand diameter, Cu/SC ratio, strand count, and a
      known `Jc`, the expected `Ic_cable` is computed independently in the
      test, e.g. `Ic = Jc * pi/4 * d^2 * (1/(1+Cu:SC ratio)) * n_strands`
      — state the exact area formula used and why).
- [ ] Load-line margin solver: for a constructed case where `Ic_cable(k*I,
      T)` is a known simple decreasing function of `I` (e.g. by picking
      coefficients where the intersection is analytically solvable or at
      least numerically pin-downable to high precision by an independent
      method in the test), the bisection solver converges to the correct
      `I_ss` within a documented tolerance, and margin at `I_op < I_ss`
      is positive and matches `100*(1-I_op/I_ss)` computed independently.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken; no
      files outside declared scope modified.

## Notes / open questions

- If Codex finds the Bottura formula as commonly published differs subtly
  from what's stated above (e.g. a different placement of `C6`), it should
  flag the discrepancy explicitly rather than silently "fixing" it to match
  either source — this is exactly the kind of ambiguity that needs a human
  or Antigravity's independent judgment, not a silent pick.
