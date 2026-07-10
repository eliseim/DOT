# TASK: Nb3Sn REMFIT type-11 (CERN/Bordini fit) support for CTH_HF

- **ID**: 0020-nb3sn-remfit-type11
- **Status**: draft
- **Model/effort**: High effort. New physics code (a second critical-current
  fit family alongside the existing Bottura Nb-Ti type-1 fit), with a live
  ROXIE validation requirement — same rigor bar as the geometry tasks:
  hand-derive first, then validate live, don't weaken tolerances.

## Background

`CTH_HF` (used in every layer-0 position of every CTH design generated so
far) resolves to a REMFIT **type 11** row (`HFM1`, via the `QXF89H_HF`
filament indirection in `roxie_CTH_cables.cadata`). DOT's cadata parser only
implements type-1 (Bottura Nb-Ti); type 11 currently returns
`status="unsupported_fit_type"` from `resolve_conductor`, so **DOT has never
been able to compute load-line margin for CTH_HF at all** — every margin
validation so far (tasks 0018, 0019, and the coordinator's own broad sweep)
had to use CTH_LF-only designs to work around this.

The user has now supplied the ROXIE "Help on Remfit field, 'Type'"
documentation (screenshot, referenced by the coordinator as
`critical_current_density_fits.png` in the repo root — read it directly,
it has the authoritative formulas for all 11 REMFIT types with LaTeX-quality
rendering). Type 11 is documented as:

```
11. CERN High Field Nb3Sn - with t = T/Tc0 and b = Bp/Bc2(t)

    Jc(B,T) = C(t)/Bp * b^p * (1-b)^q

    Bc2(t) = Bc20 * (1 - t^v)

    C(t) = C0 * (1 - t^v)^alpha * (1 - t^2)^alpha
```

(Note: `Bp` in the formula denotes the field magnitude `B` at the strand
position — same meaning as `B` in the type-1 Bottura formula already
implemented in `critical_surface.py`. `b = B/Bc2(t)`.)

### Column mapping (verified by the coordinator against real cadata rows)

The REMFIT table header comment in `roxie_CTH_cables.cadata` is generic:
`No Name Type C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 Comment` (same 11-column
layout used for every fit type, unused trailing columns are `0`). The three
real type-11 rows in that file:

```
12 PIT192 11  1.7834E+11  30     16  0.96  1.52  0.5  2  0 0 0 0
13 MQXFS5 11  1.6051E+11  30     16  0.96  1.52  0.5  2  0 0 0 0
14 HFM1   11  2.14462E+11 29.38  16  0.96  1.52  0.5  2  0 0 0 0
```

`C4=0.96` and `C5=1.52` are **identical across all three rows** (different
strand/batch references), and `C6=0.5`/`C7=2` are also identical across all
three. This matches the published literature for the CERN/Bordini Nb3Sn
parametrization, where `v=1.52` and the Kramer-style field exponents
`p=0.5, q=2` are treated as fixed constants for a given wire family, while
`C0` and `Bc20` vary batch-to-batch (matching `C1`/`C2` varying here) and
`Tc0` is roughly constant for a given Nb3Sn stoichiometry (matching `C3=16`
constant here). This gives high confidence in the mapping:

```
C1 = C0        (prefactor, A/m^2 or similar — units TBD, verify like c1*c6
                in the existing Bottura code path)
C2 = Bc20      (T)
C3 = Tc0       (K)
C4 = alpha     (exponent, dimensionless)
C5 = v (nu)    (exponent, dimensionless)
C6 = p         (exponent, dimensionless)
C7 = q         (exponent, dimensionless)
```

**Verify this mapping independently before coding** — re-derive/cross-check
against the published Bordini et al. Nb3Sn fit (IEEE Trans. Appl.
Supercond., the standard CERN HL-LHC/MQXF Nb3Sn parametrization) if you have
access to it, or at minimum confirm the formula is dimensionally and
physically sane (correct asymptotic behavior: `Jc -> 0` as `B -> Bc2(T)`,
`Jc -> 0` as `T -> Tc0`, `Jc` finite and positive over the CTH operating
range ~0-20T, ~1.9K) before trusting it for live validation.

## Goal

1. Add a `Type11FitCoefficients` (or equivalent) dataclass to
   `src/dot/conductors/cadata.py`, parsed from REMFIT rows with
   `fit_type == 11`, using the column mapping above.
2. Add a `critical_current_density_nb3sn` (or equivalent) function
   implementing the type-11 formula, alongside the existing
   `critical_current_density` (Bottura) in
   `src/dot/conductors/critical_surface.py` — do not modify the existing
   Bottura implementation.
3. Make `resolve_conductor` in `cadata.py` return a **resolved**
   `ConductorResolution` for type-11 REMFIT rows (not
   `unsupported_fit_type`), carrying whichever coefficient type applies.
   This likely means `ConductorResolution.remfit` becomes
   `Type1FitCoefficients | Type11FitCoefficients | None`, and downstream
   code (`load_line_margin_objective` in `objectives.py`,
   `solve_short_sample_current`/`_bc2`/`_equation` in `loadline.py`) needs
   to dispatch on the coefficient type to call the right `Jc(B,T)` and
   `Bc2(T)` formula. Design this dispatch cleanly (e.g. `isinstance` checks
   or a small shared protocol with `.jc(b, t)` / `.bc2(t)` methods) — your
   call which is cleaner, but don't special-case type 11 by string-matching
   REMFIT names.
4. Other REMFIT types (2-10, all unused by CTH) stay unsupported — do not
   attempt to implement them. `UnsupportedFitTypeError` / `"unsupported_fit_type"`
   should still be the correct outcome for those.
5. Hand-derive the expected `Jc` for at least one known `(B,T)` point using
   the `HFM1` coefficients before writing the implementation, and check
   your code reproduces it.
6. **Live ROXIE validation — the real point of this task.** With CTH_HF
   margin now computable, extend the CTH_LF-only design generator pattern
   (see `tests/physics/test_roxie_parity_live.py`'s
   `_cth_lf_margin_cases`/`_cth_lf_design` helpers) to also cover CTH_HF —
   at least one CTH_HF-only case and one mixed CTH_HF+CTH_LF multi-layer
   case (matching how real CTH designs actually alternate cable types per
   layer). Validate peak field AND load-line margin against live ROXIE,
   same 2% / 2 percentage point bar as tasks 0018/0019.

## Scope (files/modules Codex may touch)

- `src/dot/conductors/cadata.py`
- `src/dot/conductors/critical_surface.py`
- `src/dot/conductors/loadline.py`
- `src/dot/optimize/objectives.py` (only the type annotation/dispatch for
  `LayerConductorData.remfit` and `load_line_margin_objective`'s use of it
  — do not touch the peak-field geometry logic from tasks 0018/0019)
- `tests/conductors/test_cadata.py`
- `tests/conductors/test_critical_surface.py` (or wherever the Bottura fit
  tests live — check the actual filename)
- `tests/conductors/test_loadline.py` (if it exists — check)
- `tests/physics/test_roxie_parity_live.py`

## Explicit non-goals

- No implementation of REMFIT types 2-10.
- No change to `src/dot/optimize/objectives.py`'s peak-field geometry
  sampling logic (tasks 0018/0019, already validated) — only the
  conductor-data type it passes through.
- No change to `src/dot/geometry/*` — this task is purely about the
  critical-current physics, not geometry.
- Do not weaken any tolerance to force a pass, per binding precedent from
  every prior task in this project.

## Acceptance criteria

- [ ] Hand-derivation shown in the summary: `Jc(B,T)` computed by hand for
      at least one `(B,T)` point using `HFM1`'s coefficients, matching the
      implementation's output.
- [ ] `resolve_conductor(text, "CTH_HF")` now returns
      `status="resolved"` (verify with the real `roxie_CTH_cables.cadata`
      file, not just a synthetic fixture).
- [ ] **Live ROXIE re-validation**: at least 1 CTH_HF-only margin/peak-field
      case and at least 1 mixed CTH_HF+CTH_LF multi-layer case, both within
      2% (peak field) / 2 percentage points (margin). Report actual
      numbers; if not achieved, report honestly with diagnosis, do not
      weaken the tolerance.
- [ ] No regression: re-run tasks 0018/0019's existing live-ROXIE margin
      cases (CTH_LF-only) and confirm they still pass with unchanged
      numbers — this task must not alter Bottura (type-1) behavior at all.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material

- `C:\Users\elisei\Desktop\DOT\critical_current_density_fits.png` — the
  authoritative ROXIE REMFIT type documentation (all 11 types); read this
  directly, it is the primary source for this task's formula.
- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — real
  REMFIT rows `PIT192`/`MQXFS5`/`HFM1` (type 11) and the `CTH_HF`
  CONDUCTOR row and its `QXF89H_HF` FILAMENT indirection.
- `src/dot/conductors/critical_surface.py` and
  `src/dot/conductors/cadata.py`'s existing type-1 (Bottura) implementation
  — follow the same code style and validation rigor
  (`_require_finite_positive` etc.), do not weaken input validation.
- `roxieapi` REST service is live at `http://127.0.0.1:8080`; system Python
  has `roxieapi` installed (`python -c "import roxieapi"` to confirm).
