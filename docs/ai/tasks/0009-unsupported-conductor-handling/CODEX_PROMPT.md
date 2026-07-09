# Codex worker prompt — TASK 0009-unsupported-conductor-handling

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0009-unsupported-conductor-handling/TASK.md` in this
worktree fully before writing any code. This closes a real correctness gap
found while preparing to run a real multi-conductor campaign — read the
"Background" section carefully, it explains exactly what's missing and why.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Read the actual current implementations of `src/dot/conductors/cadata.py`,
   `src/dot/optimize/objectives.py`, `src/dot/optimize/problem.py`,
   `src/dot/optimize/runner.py`, and `src/dot/gui/target_synthesis_gui.py`
   before changing anything — do not guess signatures.
3. An unsupported conductor must produce a clear, catchable, typed outcome
   at every layer of the stack (parser -> objectives -> problem/runner ->
   GUI) — never an uncaught crash, and never a silent wrong substitution
   (e.g. falling back to a different, unrelated conductor's data without
   saying so).
4. Still do not implement Nb3Sn/non-type-1 Jc physics. The fix is entirely
   about correctly identifying and gracefully handling what's unsupported.
5. Write the tests specified in TASK.md's acceptance criteria against the
   real `roxie_CTH_cables.cadata` file where specified, run `pytest` and
   `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the
`ConductorRecord`/`resolve_conductor` shape you chose, how "unsupported"
propagates through `objectives.py` -> `problem.py`/`runner.py` -> the GUI
without crashing, and full test output including the real-file CONDUCTOR
section test.

## Task-specific instructions

Follow TASK.md's "Goal" and "Scope" sections precisely. In particular:

1. `cadata.py`: parse `CONDUCTOR` section rows (no, name, type, cable_name,
   strand_name, insul_name, transient_name, remfit_name, temperature_k,
   comment — verify this exact column order against the real file first).
   Add `resolve_conductor(text, name)` returning a result that clearly
   distinguishes: resolved (with strand/cable/remfit/temperature), name
   not found, or fit type unsupported (include the fit type number and
   remfit name in the unsupported case, matching the spirit of the
   existing `UnsupportedFitTypeError`).
2. `objectives.py`: allow the per-layer conductor data to be `None`;
   `_peak_field_on_own_turns` (or a renamed equivalent) must accept a way
   to know which layers have `None` data and exclude their turns from the
   search entirely, not just skip them post-hoc after already finding them
   as "best".
3. `problem.py`/`runner.py`: thread `LayerConductorData | None` through;
   surface which layers were excluded from margin evaluation in whatever
   result type `run_campaign` returns (add a field if needed — keep it
   simple, e.g. a tuple of excluded layer indices with reasons).
4. `target_synthesis_gui.py`: add the per-layer conductor-name field
   (empty = old fallback behavior), wire to `resolve_conductor`, store
   `None` + log a clear message for unsupported layers instead of raising.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite)
