# TASK: Chunk vectorized field computation to fix memory-scaling crash

- **ID**: 0026-chunk-vectorized-field-memory
- **Status**: draft
- **Model/effort**: High effort. Touches `src/dot/physics/field.py`, the
  same core physics file task 0024 vectorized (already merged, validated
  to <2% against ROXIE, no numerical change intended). This task fixes a
  scaling regression introduced by that vectorization — the physics/output
  values must not change at all, only how memory is used to compute them.

## Background

A real CTH design campaign (6 layers, 3 blocks/layer, up to 22 turns per
block) crashed with:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 10.1 GiB
for an array with shape (176, 7705600) and data type float64
```

Traceback: `field_at_many_explicit_sources` in `src/dot/physics/field.py`
(added by task 0024) builds the full dense `dx_m`/`dy_m`/`rho2_m2`/`scale`
matrices with shape `(n_probe_points, n_sources)` **in one allocation**.
For a design with many turns, `n_sources` is
`n_turns_total * PEAK_FIELD_FILAMENTS_PER_AXIS^2 * 4` (the 80x80 near-field
discretization from task 0018, times 4 for dipole mirror images) — for
~300 total turns this reaches ~7.7 million sources, and with even a
modest number of probe points (176, matching the boundary-sample-point
count from the margin objective), the resulting dense matrix requires
10+ GB, which fails to allocate.

**This is a real regression introduced by task 0024's vectorization.** The
old (pre-0024) unvectorized implementation never had this problem — it
accumulated the field contribution from each source one at a time via
`math.fsum`, using O(1) memory regardless of source count (just much
slower, which is exactly what task 0024 fixed for the *common* case).
Task 0024's own acceptance criteria only benchmarked a moderate design
(4 layers, 3 turns/block); it was never tested against a design large
enough to expose this memory ceiling. This is not a hypothetical edge
case — any real campaign exploring higher turn counts (which task 0025 is
expected to make more common, since it removes the artificial early
current-cap cutoff that was keeping designs small) will hit this.

## Goal

1. Rewrite `field_at_many_explicit_sources` (and/or
   `field_at_many`/`field_at_explicit_sources`/`field_at` as needed) to
   process sources and/or probe points in **bounded-size chunks** rather
   than materializing the full `(n_probe_points, n_sources)` dense matrix
   in one allocation. Pick a chunking strategy (chunk over sources,
   accumulating partial sums into the output arrays; or over probe points;
   or both) that keeps peak memory bounded regardless of how large
   `n_sources`/`n_probe_points` get, while still being meaningfully
   vectorized within each chunk (don't regress back to a pure per-source
   Python loop — the chunk size should be large enough that NumPy
   vectorization still gives a real speedup within each chunk).
2. Choose a chunk size (fixed constant, or computed from available memory,
   or configurable — your call, justify it) such that peak additional
   memory for the dense intermediate arrays stays under some reasonable
   bound (propose a number, e.g. a few hundred MB, and justify it against
   typical available system memory) regardless of total source count.
3. **The physics must not change.** This is a pure memory-management fix.
   Every existing test (including live ROXIE parity) must produce the
   same numerical results as the current (already-merged) task 0024
   implementation, to floating-point precision or an extremely tight,
   justified tolerance.
4. Reproduce the crash from the Background section (or an equivalent
   large-design case) before your fix, confirm it no longer crashes after,
   and report actual peak memory usage before/after if you can measure it
   (e.g. via `tracemalloc` or `resource`/`psutil`), plus wall-clock timing
   before/after (chunking will likely be somewhat slower than the
   unbounded dense version for cases that previously fit in memory, but
   should still be dramatically faster than the pre-task-0024 unvectorized
   version — report both comparisons).

## Scope (files/modules Codex may touch)

- `src/dot/physics/field.py`
- `tests/physics/test_field.py`

## Explicit non-goals

- No change to the physics/geometry/margin methodology itself (tasks
  0018/0019/0020, already validated) — only how the field computation
  manages memory.
- No change to `src/dot/optimize/*` — if the objectives code needs to
  call the field functions differently to benefit from chunking, that's
  fine, but the chunking itself belongs in `field.py`; don't move the
  chunking logic into `objectives.py`.
- Do not weaken any existing test's tolerance to force a pass.
- Do not reduce `PEAK_FIELD_FILAMENTS_PER_AXIS` or any other
  already-validated accuracy parameter to sidestep the memory problem —
  fix the memory management, don't reduce fidelity.

## Acceptance criteria

- [ ] Reproduce the exact crash scenario from Background (or an
      equivalent large-source-count case) and confirm it no longer raises
      `MemoryError`/`ArrayMemoryError` after your fix.
- [ ] Numerical equivalence: for at least 2-3 cases (including at least
      one of the sizes already validated by task 0024), confirm outputs
      match the current merged implementation to floating-point precision
      or a tight, explicitly justified tolerance.
- [ ] Peak memory usage measured and reported for the large-design case,
      before (crash) and after (bounded, report the actual number).
- [ ] Wall-clock timing reported for at least one small/medium case
      (comparable to task 0024's original benchmark) and the new large
      case, confirming chunking doesn't reintroduce the original
      pre-task-0024 slowness for the common case.
- [ ] Live ROXIE re-validation: re-run at least 2-3 of the existing live
      ROXIE parity tests and confirm unchanged results.
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] No files outside declared scope modified.

## Reference material

- `src/dot/physics/field.py` — read fully, this is task 0024's already-
  merged vectorization; understand it completely before modifying it.
- The crash traceback in this TASK.md's Background section — the exact
  shape `(176, 7705600)` and the 10.1 GiB figure are real, reproducible
  numbers from an actual crash, not estimates.
- `roxieapi` REST service is live at `http://127.0.0.1:8080`; system Python
  has `roxieapi` installed (`python -c "import roxieapi"` to confirm) —
  needed for the live-ROXIE re-validation in the acceptance criteria.
