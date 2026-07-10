# Codex worker prompt — TASK 0017-keystone-cable-cross-section

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0017-keystone-cable-cross-section/TASK.md` in this worktree
fully before writing any code. This continues directly from task 0015
(already merged) — read the current `src/dot/geometry/primitives.py` and
`src/dot/geometry/cable.py` fully first, do not guess their structure.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Do not change the absolute-alpha or arc-stacking logic from task 0015
   — only the cross-section shape (trapezoid vs rectangle) and which
   width value (inner vs averaged) is used for the stacking step.
3. **The real bar for this task is live ROXIE re-validation** of the
   specific cases in TASK.md's acceptance criteria — you have access to
   the live ROXIE REST service at `http://127.0.0.1:8080` via `roxieapi`
   (already installed on this machine's system Python; check
   `python -c "import roxieapi"` — you may need to run your validation
   script with that Python rather than a fresh venv). Actually run these
   validations and report real numbers.
4. If any case doesn't reach 2% after your fix, report the honest number
   and your diagnosis — do not weaken any tolerance to force a pass. This
   mirrors binding precedent from tasks 0008 and 0015.
5. You may read `dipole_designer`'s `geometry_helpers.py` for
   understanding only — do not copy code.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the new
`CableSpec` shape, confirmation the trapezoid corner test produces a
genuinely non-rectangular shape, live ROXIE numbers for all 5 validation
cases (3 new single-turn cases + 2 regression cases from task 0015), and
confirmation the GUI's insulation-thickness bug is fixed with a real-file
test.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. The
3 new single-turn test cases to validate live: CTH_HF cable,
`alpha_deg=0`, `n_turns=1`, aperture=25mm, scaled to 5T target field, at:
- `inner_radius_mm=35.0, phi_deg=40.0`
- `inner_radius_mm=40.0, phi_deg=30.0`
- `inner_radius_mm=45.0, phi_deg=50.0`

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- All 5 live ROXIE validation numbers explicitly
