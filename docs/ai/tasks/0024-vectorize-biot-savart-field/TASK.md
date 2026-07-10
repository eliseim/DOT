# TASK: Vectorize Biot-Savart field evaluation (urgent, blocks optimization campaigns)

- **ID**: 0024-vectorize-biot-savart-field
- **Status**: draft
- **Priority**: URGENT — blocks all real optimization campaign work.
- **Model/effort**: Highest effort. This touches `src/dot/physics/field.py`,
  used by both the bore-field (already validated to <2% against ROXIE
  across 200+ cases) and the margin objective (also validated). This is a
  **pure performance optimization** — the physics/math must not change at
  all. Validation is: full existing test suite passes unchanged, existing
  live-ROXIE tests still produce the same (or numerically indistinguishable)
  results, and a measured wall-clock speedup.

## Background

Profiling a realistic 4-layer CTH-style design (`operating_point` solved
to 10T, alternating CTH_HF/CTH_LF cable, 3 turns/block) found:

- `field_quality_objective` (bore-field harmonics): **5.25 ms**
- `load_line_margin_objective`: **24,402 ms** (24.4 seconds)

A single margin-objective evaluation taking 24 seconds makes any real
NSGA-II campaign completely impractical — even a small campaign
(`pop_size=40`, `n_gen=15`, roughly 640 evaluations) would take over 4
hours. This must be fixed before any real optimization campaign can run
in reasonable time.

Two distinct, stackable causes were identified by reading
`src/dot/optimize/objectives.py` and `src/dot/physics/field.py`:

1. **Redundant per-layer full-design rebuild.**
   `load_line_margin_objective` loops `for layer_index in evaluated_layers:`
   and calls `_peak_field_on_own_turns(design, evaluated_layers=(layer_index,))`
   once per layer. Internally, `_peak_field_on_own_turns` calls
   `_near_field_sources(indexed_turns)`, which discretizes **every turn in
   the entire design** (not just the current layer) into
   `PEAK_FIELD_FILAMENTS_PER_AXIS x PEAK_FIELD_FILAMENTS_PER_AXIS` (80x80
   = 6400) filaments per turn, from scratch, on every one of the `N`
   layer-loop iterations. For an `N`-layer design this is an `N`x
   redundant rebuild of the same ~tens-of-thousands-of-filament source
   list.
2. **Unvectorized, pure-Python Biot-Savart summation, with mirroring
   redone on every call.** `field_at` (`src/dot/physics/field.py`) expands
   every source into its 4 dipole-mirror images via a Python generator
   expression, then `field_at_explicit_sources` loops over every
   (already-expanded) source in pure Python, computing the Biot-Savart
   contribution one source at a time and accumulating into two Python
   lists before calling `math.fsum`. For the profiled case this amounts
   to roughly 7+ million individual scalar Python operations for a single
   margin-objective call (4 layers x ~24 boundary-sample points/layer x
   ~76,800 mirrored sources/point).

## Goal

1. **Eliminate the redundant rebuild.** Compute the near-field source list
   for the whole design once per `load_line_margin_objective` call (or
   once per `_peak_field_on_own_turns` call site, whichever is cleaner),
   and reuse it across the per-layer loop instead of rebuilding it `N`
   times.
2. **Vectorize the Biot-Savart summation.** Rewrite the core field
   computation (`field_at`, `field_at_explicit_sources`, and/or their call
   sites) to use NumPy array operations instead of per-source Python
   loops: build `(x, y, current)` arrays once for a source set (including
   pre-expanding the 4 dipole-mirror images into flat arrays, computed
   once rather than regenerated on every call), then compute the field at
   one or many query points via broadcasted vector math. If a query
   pattern evaluates many points against the same fixed source list (as
   the margin objective's boundary-sample-point loop does), vectorize
   across query points too, not just across sources.
3. Investigate whether Numba JIT (already a reasonable dependency to add
   given the project's numeric nature — check if it's already installed;
   if not, evaluate whether it's worth adding) meaningfully improves on
   plain NumPy vectorization for this specific workload, and use it if it
   gives a material additional speedup with acceptable complexity cost.
   If NumPy vectorization alone gets the margin objective to a
   practical speed (sub-100ms, ideally much less), Numba may not be
   necessary — make the call based on the actual measured numbers, don't
   add complexity that isn't earning its keep.
4. **The physics must not change.** This is a pure speed optimization.
   Do not change `PEAK_FIELD_FILAMENTS_PER_AXIS`, the boundary-sampling
   locations, the dipole mirror construction, or any other
   already-validated behavior. Every existing test (including the live
   ROXIE parity tests) must produce the same feasibility/objective
   conclusions as before — numerical results should match to floating
   point precision or an extremely tight tolerance (document exactly how
   tight, and why any difference exists if it's not bit-exact — e.g.
   summation order changing with vectorization is an acceptable source of
   tiny floating-point differences, but must be quantified, not assumed).

## Scope (files/modules Codex may touch)

- `src/dot/physics/field.py`
- `src/dot/physics/sources.py` (only if a data-structure change is needed
  to support vectorization — e.g. a batch/array-based source
  representation alongside or instead of the current one-dataclass-per-
  filament representation; if you change the public shape of
  `LineCurrentSource`/`place_line_current_sources`, update every call
  site, don't leave a partially-migrated API)
- `src/dot/optimize/objectives.py` (only the redundant-rebuild fix and
  whatever call-site changes are needed to use the new vectorized API —
  do not change the peak-field/margin methodology itself, that's
  already-validated task 0018/0019/0020 territory)
- `pyproject.toml`/dependency files (only if adding `numba` — justify with
  measured numbers per Goal 3)
- `tests/physics/test_field.py`, `tests/physics/test_sources.py`,
  `tests/optimize/test_objectives.py`

## Explicit non-goals

- No change to any physics/geometry logic — this is speed only.
- No change to `PEAK_FIELD_FILAMENTS_PER_AXIS` or the boundary-sampling
  approach (tasks 0018/0019/0020's validated methodology).
- No change to `src/dot/geometry/*`.
- Do not weaken any existing test's tolerance to force a pass — if
  vectorization introduces a tiny floating-point difference, the existing
  `pytest.approx` tolerances should already accommodate it; if they
  don't, that's a signal to investigate the vectorization for a real bug,
  not to loosen the test.

## Acceptance criteria

- [ ] Measured before/after wall-clock time for the exact profiled case
      (4-layer CTH_HF/CTH_LF alternating design, 3 turns/block, 10T
      target — reconstruct it from this TASK.md's Background section, or
      use an equivalent realistic multi-layer design) — report the actual
      before and after numbers, and the speedup factor.
- [ ] `field_quality_objective` (bore-field) also benchmarked before/after
      — it's already fast (5ms) but uses the same `field_at` function, so
      confirm it doesn't regress and ideally also speeds up.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] Existing live-ROXIE parity tests
      (`tests/physics/test_roxie_parity_live.py`,
      `tests/physics/test_roxie_parity_cth14t.py`) re-run live against
      ROXIE and produce the same pass/fail outcome and materially the same
      numbers as before this change (report actual before/after numbers
      for at least 2-3 cases) — this is the check that catches a subtle
      vectorization bug that unit tests might miss.
- [ ] No files outside declared scope modified.

## Reference material

- `src/dot/physics/field.py`, `src/dot/physics/sources.py`,
  `src/dot/optimize/objectives.py` — read fully before changing anything.
- `roxieapi` REST service is live at `http://127.0.0.1:8080`; system Python
  has `roxieapi` installed (`python -c "import roxieapi"` to confirm) —
  needed for the live-ROXIE re-validation in the acceptance criteria.
