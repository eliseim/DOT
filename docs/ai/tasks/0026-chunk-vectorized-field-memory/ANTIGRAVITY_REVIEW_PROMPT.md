# Antigravity independent review prompt — TASK 0026-chunk-vectorized-field-memory

You are reviewing a diff produced by another AI worker (Codex) that fixes
a real memory-scaling crash in DOT's core Biot-Savart field computation
(`src/dot/physics/field.py`), introduced by task 0024's vectorization. The
crash is real and reproducible: a design with ~7.7 million total sources
triggered a 10.1 GiB allocation failure. This touches physics code used
by both the already-validated bore-field and margin pipelines — your job
is to verify the fix genuinely bounds memory while producing identical
numerical results.

## Inputs

- `docs/ai/tasks/0026-chunk-vectorized-field-memory/TASK.md` — read fully.
- The diff/commit on branch `task/0026-chunk-vectorized-field-memory`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Reproduce the original crash yourself** against `main` (before this
   diff) to confirm it's real, then confirm the same case no longer
   crashes with the diff applied.
2. **Numerical equivalence — the most severe check.** Pick at least one
   case and compute the field/margin both with and without the diff
   applied (same inputs), confirm outputs match to a tight, justified
   tolerance. Any numerical drift beyond floating-point noise is the most
   severe possible finding here.
3. **Memory actually bounded.** Verify peak memory for the large-design
   case is genuinely bounded (not just "smaller but still huge") — test
   with an even larger source count than the original crash case if
   feasible, and confirm it still doesn't blow up.
4. **Performance regression check.** Confirm chunking doesn't reintroduce
   near-pre-task-0024 slowness for the common (small/medium) case that
   task 0024 was built to speed up — reproduce task 0024's original
   benchmark yourself and compare.
5. **Live ROXIE re-validation — run it yourself** for at least 2-3 cases,
   confirm unchanged results from what tasks 0018/0019/0020/0024 already
   established.
6. **Scope discipline.** No changes to `PEAK_FIELD_FILAMENTS_PER_AXIS`, no
   reduction in discretization/fidelity to sidestep the memory problem
   instead of actually fixing memory management. No changes to
   `src/dot/optimize/*`.

## Output format

Findings ranked most-severe first — a numerical regression, or a "fix"
that reduces fidelity instead of managing memory properly, are the most
severe possible findings here. For each: file, line, what's wrong,
concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — reproduce the crash
yourself, verify the fix, run your own live ROXIE checks, and confirm no
performance regression on the common case before approving.
