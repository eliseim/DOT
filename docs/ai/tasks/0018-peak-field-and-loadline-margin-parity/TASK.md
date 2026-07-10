# TASK: Peak-field-on-conductor and load-line-margin parity with ROXIE

- **ID**: 0018-peak-field-and-loadline-margin-parity
- **Status**: draft
- **Model/effort**: Highest effort. Same rigor bar as tasks 0015/0017: independent
  derivation, live ROXIE re-validation across multiple cases, do not weaken any
  tolerance to force a pass.

## Background

Tasks 0015 and 0017 closed the **bore-field** parity gap: 200/200 randomly
generated cross-sections are within 2% of live ROXIE on total field magnitude
(mean 0.088%). That validation only exercises the field far from any single
conductor (evaluated at/near the bore center via superposition of all
sources), where per-turn discretization error washes out.

`src/dot/optimize/objectives.py::load_line_margin_objective` (and its helper
`_peak_field_on_own_turns`) computes a *different* quantity: the peak field
**on a turn's own boundary**, i.e. very close to that same turn's own current
sources. This is the field ROXIE reports per block as `PEAK FIELD IN
CONDUCTOR N (T)` in the `.output` file, and it is the input to the load-line
margin (`PERCENTAGE ON THE LOAD LINE`, and `MAXIMUM LOADLINE IN BLOCK N`).
This quantity has never been validated against ROXIE and, when checked, is
badly wrong.

### What was found

Live-ROXIE comparison on a focused CTH_LF-only (Nb-Ti; see "Nb3Sn note"
below) sweep of 30 single/multi-layer designs, alpha=0, 1-2 turns/block,
current chosen by DOT's own operating-point solve, 5T target:

- Peak field: **0/28 within 2%**, mean error 66.5%, max 83.5%, using the
  current default `place_line_current_sources(turn, n1=3, n2=3)` (3x3
  filaments per turn — the hard-coded default in `objectives.py`'s call
  path).
- Load-line margin (`load_line_margin_percent`): 0/28 within 2 percentage
  points, mean discrepancy ~309 percentage points — a direct consequence of
  the peak-field error, since margin is derived from it via
  `solve_short_sample_current`.

**Root cause #1 (dominant, already diagnosed): the 3x3 filament
discretization is far too coarse for a near-field/self-field evaluation.**
`_peak_field_on_own_turns` samples the field at points on a turn's own
boundary (its 4 corners + 4 edge midpoints) — i.e. very close to that same
turn's own sources. A coarse filament grid concentrates current at a few
discrete points, producing spurious near-field spikes at nearby sample
points. This does not affect the bore-field calculation (evaluated far from
every source) but dominates the near-field/self-field case.

Confirmed by re-running two of the 30 cases with a much finer, *exactly
reproduced* design (same RNG trace) at increasing `(n1, n2)`:

```
Case A (1 layer, 1 turn, r=36.539mm, phi=27.667deg, I=-442893A; ROXIE peak = 24.2803 T)
  n1=n2=3:   DOT peak=43.6483T  diff=79.77%
  n1=n2=8:   DOT peak=22.1784T  diff= 8.66%
  n1=n2=20:  DOT peak=23.0705T  diff= 4.98%
  n1=n2=80:  DOT peak=23.2161T  diff= 4.38%
  n1=n2=150: DOT peak=23.2227T  diff= 4.36%   <- converged, plateaus here

Case B (2 layers; ROXIE peak = 14.4284 T)
  n1=n2=3:   DOT peak=23.5019T  diff=62.89%
  n1=n2=20:  DOT peak=13.8534T  diff= 3.98%
  n1=n2=150: DOT peak=13.9297T  diff= 3.46%   <- converged, plateaus here
```

So raising the discretization resolves the bulk of the error (80% -> ~4%),
but **a genuine, reproducible ~3.5-4.4% residual remains even once the
filament count is converged** (increasing further from 80 to 150 changes the
answer by <0.1%, so this is not an under-discretization artifact). Denser
boundary-point sampling (40 points/edge instead of 4 corners + 4
midpoints) does not close this residual either — it converges to the same
plateau.

This residual is the open problem for this task. Plausible causes to
investigate (not yet distinguished):

1. ROXIE's own `PEAK FIELD IN CONDUCTOR` may use a genuinely different
   definition/reference point than "max field magnitude sampled on the
   turn's own polygon boundary" — e.g. a specific canonical corner, or a
   field evaluated via an analytic closed-form solution for a
   uniformly-current-filled trapezoid rather than a filament sum (a
   converged filament sum should equal the analytic integral in the limit,
   so if it doesn't, something about the geometry or source placement is
   subtly off, not just under-resolved).
2. A small systematic error in the turn's own corner geometry (already
   validated to <0.3% for far-field purposes, but near-field self-field
   evaluation is far more sensitive to exact boundary position than
   far-field superposition is).
3. ROXIE's internal `n1`/`n2` BLOCK-record columns (used here as 2x15 for
   CTH_LF, 2x20 for CTH_HF in the `.data` file) were tested directly as
   DOT's own filament mesh and gave a *worse* match (30% error at n1=2,n2=15)
   — so ROXIE's own peak-field number is almost certainly not simply "sum
   the same n1xn2 filament mesh it was told about"; it likely uses its own
   internal (finer, or analytic) near-field model independent of that
   column. Do not assume ROXIE's own n1/n2 values are the answer.

### Nb3Sn note (separate, smaller, in-scope fix)

`CTH_HF` resolves (via `resolve_conductor`) to a Nb3Sn REMFIT (fit type 56,
via the `QXF89H_HF` filament in `roxie_CTH_cables.cadata`). DOT's cadata
parser only implements the type-1 Bottura Nb-Ti fit
(`Type1FitCoefficients`), so `resolve_conductor(text, "CTH_HF")` currently
returns `status="unsupported_fit_type"` and margin cannot be computed for
*any* design containing a CTH_HF layer at all — which is every case in the
original 200-case field-parity sweep (layer 0 there always alternates
starting with CTH_HF). This is why the peak-field/margin validation above
had to be restricted to a separate CTH_LF-only design set. **This task does
not require implementing a full Nb3Sn (type-56) critical-surface fit** (that
is a substantial separate physics task) — just confirm
`resolve_conductor`/`ConductorResolution` degrades cleanly (as it already
does, returning an `unsupported_fit_type` status rather than crashing) and
note this limitation explicitly in the deliverable summary. Do not attempt
the Nb3Sn fit itself in this task.

## Goal

1. Fix the dominant bug: `_peak_field_on_own_turns` /
   `load_line_margin_objective` in `src/dot/optimize/objectives.py`
   currently discretizes each turn into a 3x3 filament grid via
   `place_line_current_sources(turn)` (using that function's default
   `n1=3, n2=3`). Raise this to a resolution sufficient for near-field
   convergence (the diagnostic above shows ~80 is where it plateaus;
   determine and justify the actual number empirically, don't just copy
   80 verbatim — check the tradeoff against evaluation cost since this
   sits on the optimizer's objective-evaluation hot path).
2. **Root-cause and close the residual ~3.5-4.4% gap** that remains after
   fixing (1). This is the real target of this task — do not stop at "much
   better than before," the standing bar is 2%. Independently re-derive
   what "peak field on a conductor" should mean for a straight 2D
   current-carrying trapezoid (by hand, before touching code), and compare
   against both DOT's filament-sum result and ROXIE's reported value for
   at least 2 independent single-turn cases. If the true source of the
   residual turns out to be irreducible given DOT's line-current
   modeling approach (i.e. a genuine, understood, and justified modeling
   limit rather than a bug), report that honestly with the derivation
   that shows it — do not force a fix that isn't real.
3. Once peak field is within tolerance, re-validate that
   `load_line_margin_objective`'s margin output (which is downstream of
   peak field via `solve_short_sample_current`) is also within 2
   percentage points of ROXIE's `100 - PERCENTAGE ON THE LOAD LINE` for
   the same cases.
4. Do not touch the already-validated bore-field/harmonics code path
   (`multipole_coefficients`, `field_at` as used by
   `dot_field_and_harmonics`-style callers) — this task is scoped to the
   near-field/self-field peak evaluation used by the margin objective only.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/objectives.py`
- `src/dot/physics/sources.py` (only if a source-placement-level fix is
  needed, e.g. changing how filaments are distributed within a turn for
  near-field accuracy — do not change the bore-field call sites' behavior)
- `tests/optimize/test_objectives.py`
- `tests/physics/test_roxie_parity_live.py` (add margin/peak-field live
  coverage; do not modify the existing bore-field test cases in this file)

## Explicit non-goals

- No Nb3Sn (REMFIT type 56 or any non-type-1) critical-current fit
  implementation. `CTH_HF` margin support stays out of scope; document the
  limitation instead.
- No change to turn/block geometry (`primitives.py`, `cable.py`) unless the
  investigation in goal (2) proves the turn corner geometry itself is the
  source of the residual — if so, stop and report back rather than modifying
  the already-twice-validated geometry code without a fresh, equally
  rigorous review cycle.
- No change to the bore-field multipole/field-quality code path.

## Acceptance criteria

- [ ] Hand-derived (shown in the summary, not just code) expectation for
      the peak field of at least one simple single-turn case, compared
      against both the fixed DOT implementation and live ROXIE.
- [ ] **Live ROXIE re-validation** of peak field AND load-line margin for
      at least 5 cases (reuse or extend the CTH_LF-only design generator
      pattern from this task's background, or use fixed hand-picked
      designs — cases must include at least 1 single-turn and at least 1
      multi-layer case). Report actual numbers.
- [ ] State plainly whether 2% (peak field) / 2 percentage points (margin)
      is achieved. If not achieved, report the honest final number and the
      derivation showing why, per goal (2) — do not weaken the tolerance.
- [ ] No regression: re-run the existing bore-field live-ROXIE tests
      (`tests/physics/test_roxie_parity_live.py`,
      `tests/physics/test_roxie_parity_cth14t.py`) and confirm they still
      pass unchanged.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- ROXIE `.output` files already gathered at
  `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\margin_out\case_*\*.output`
  — grep for `PEAK FIELD IN CONDUCTOR`, `PERCENTAGE ON THE LOAD LINE`,
  `MAXIMUM LOADLINE IN BLOCK`.
- Diagnostic scripts (coordinator's own exploratory tools, not part of the
  DOT package, read for methodology only):
  `C:\Users\elisei\.claude\jobs\3eb3c5d7\tmp\roxie_test\margin_sweep.py`,
  `peak_field_diag2.py`.
- `roxieapi` REST service is live at `http://127.0.0.1:8080`; system Python
  has `roxieapi` installed (`python -c "import roxieapi"` to confirm).
- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — real
  cable/strand/REMFIT records for CTH_HF (Nb3Sn, unsupported) and CTH_LF
  (Nb-Ti, supported).
- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\roxie\parser.py`
  — for reference only: shows that `dipole_designer` sources its own
  `peak_field_T_by_block`/margin values directly from parsing ROXIE's
  `.output`, not from an independent from-scratch calculation. There is no
  independently-validated reference formula to copy from that codebase for
  this quantity — this is genuinely new physics work for DOT.
