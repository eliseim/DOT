# Antigravity independent review prompt — TASK 0024-vectorize-biot-savart-field

You are reviewing a diff produced by another AI worker (Codex) that
vectorizes DOT's core Biot-Savart field computation
(`src/dot/physics/field.py`) for performance — the existing
`load_line_margin_objective` was measured at 24.4 seconds per evaluation
on a realistic design, making it unusable inside an optimization loop.
This touches code used by the already-validated bore-field (200+ cases
within 2% of live ROXIE) and margin (tasks 0018/0019/0020) pipelines. The
stated intent is **pure speed, zero physics change** — your job is to
verify that promise held.

## Inputs

- `docs/ai/tasks/0024-vectorize-biot-savart-field/TASK.md` — read fully.
- The diff/commit on branch `task/0024-vectorize-biot-savart-field`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Numerical equivalence.** Pick at least one case and compute the
   field/margin both with the diff applied and with it reverted (e.g.
   `git stash`/`git show main:...` to get the old implementation
   temporarily), same inputs, and confirm the outputs match to a tight,
   justified tolerance. If they don't match near-exactly, that's the most
   severe possible finding for this task — it means the "pure speed, no
   physics change" premise is false.
2. **No redundant rebuild remains.** Confirm the per-layer loop in
   `load_line_margin_objective` (or wherever it ended up) builds the
   near-field source list once, not once per layer.
3. **Live ROXIE re-validation — run it yourself.** Reproduce at least 2
   of Codex's reported before/after cases independently, and confirm the
   numbers still match ROXIE within the same tolerances tasks
   0018/0019/0020 already established (not a regression).
4. **Real speedup, honestly measured.** Reproduce the wall-clock timing
   yourself for at least the main profiled case. Don't just trust a
   reported number — time it.
5. **Scope discipline.** No changes to `PEAK_FIELD_FILAMENTS_PER_AXIS`,
   boundary-sampling locations, dipole mirror construction, or anything
   in `src/dot/geometry/*`.
6. **Numba justification** (if added): confirm the reported numbers
   actually justify the added dependency/complexity, per TASK.md Goal 3 —
   if NumPy alone already gets to a practical speed, adding Numba on top
   should have a clear, quantified marginal benefit, not just be present
   because it was allowed.

## Output format

Findings ranked most-severe first — any numerical regression in the
field/margin values (even if fast) is the single most severe possible
finding here, more severe than a modest speedup shortfall. For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — run your own timing
measurement and your own live ROXIE checks before approving.
