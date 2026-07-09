# Codex worker prompt — TASK 0004-conductor-critical-current

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0004-conductor-critical-current/TASK.md` in this worktree
fully before writing any code. Load-line margin is a core DOT objective —
the user has explicitly said the prior reference tool's correctness here is
unverified, so treat every formula skeptically and validate against the
published physics, not against that tool's behavior.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Implement the Bottura Nb-Ti `Jc(B,T)` fit exactly as given in TASK.md.
   **Only REMFIT type 1 is supported** — any other fit type must raise a
   clear typed exception, never be silently mis-handled.
3. You may read the reference files listed in TASK.md for format/algorithm
   understanding, but do not copy code, and do not treat the reference
   tool's numeric test fixtures as ground truth — it explicitly admits this
   area is unvalidated. Validate against the formula itself and physical
   sanity checks (monotonicity, boundary conditions).
4. No ROXIE dependency. No optimizer/GUI wiring. No geometry/field code —
   the load-line coefficient `k` (T/A) is a parameter, not computed here.
5. If you find the published Bottura formula's exact form ambiguous or
   different from what TASK.md states, say so explicitly in your summary
   rather than silently choosing a variant.
6. Write the tests specified in TASK.md's acceptance criteria, run `pytest`
   and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact
formula implemented (confirm it matches TASK.md or flag the discrepancy),
the strand/cable Ic composition formula used and why, the bisection
tolerance/convergence approach for the load-line solver, and full test
output.

## Task-specific instructions

Implement, in this order:

1. `src/dot/conductors/cadata.py`: dataclasses `StrandRecord` (diameter_mm,
   cu_to_sc_ratio), `CableRecord` (n_strands, degradation_percent), `Type1FitCoefficients` (c1..c7). A parser function that reads `.cadata`-format text and extracts `STRAND`, `CABLE`, and `REMFIT` sections (whitespace/column-delimited, matching the on-disk format from the reference file — inspect it for the exact column layout). For `REMFIT`, only fit-type `1` is supported; any other type raises `UnsupportedFitTypeError(fit_type, name)`.
2. `src/dot/conductors/critical_surface.py`: `critical_current_density(b_field_t, temperature_k, coeffs: Type1FitCoefficients) -> float` (A/m^2) implementing the formula from TASK.md exactly, with input validation (0 <= B < Bc2(T), 0 <= T < Tc0) raising `ValueError` on invalid physical inputs rather than returning NaN/negative.
3. `src/dot/conductors/critical_current.py`: `strand_critical_current(jc_a_per_m2, strand: StrandRecord) -> float` and `cable_critical_current(jc_a_per_m2, strand: StrandRecord, cable: CableRecord) -> float`, using the superconductor cross-section area derived from strand diameter and Cu:SC ratio (document the exact area formula in a docstring).
4. `src/dot/conductors/loadline.py`: `solve_short_sample_current(coeffs, strand, cable, temperature_k, k_field_per_current, i_lo=1.0, i_hi=..., tol=...) -> float` via bisection on `f(I) = cable_critical_current(critical_current_density(k*I, T, coeffs), strand, cable) - I`, and `load_line_margin_percent(i_operating, i_short_sample) -> float`.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + all previously merged tests must still pass)
