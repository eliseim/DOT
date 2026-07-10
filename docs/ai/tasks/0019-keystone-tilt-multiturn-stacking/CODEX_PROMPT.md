# Codex worker prompt — TASK 0019-keystone-tilt-multiturn-stacking

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0019-keystone-tilt-multiturn-stacking/TASK.md` in this
worktree fully before writing any code — it contains a precise diagnostic
(real ROXIE conductor coordinates, the exact wrong formula and where it
lives, and why earlier validation rounds missed this) from an independent
reviewer's own investigation. Do not re-derive this from scratch or ignore
it; build on it.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. This is the **third** time `src/dot/geometry/primitives.py` has been
   modified (after tasks 0015 and 0017, both independently re-validated
   live against ROXIE). Treat it with the same care: hand-derive before
   coding, and do not assume the existing bore-field validation still
   holds after your change — re-check it live.
3. **The real bar for this task is live ROXIE re-validation.** You have
   access to the live ROXIE REST service at `http://127.0.0.1:8080` via
   `roxieapi` (installed on system Python; check
   `python -c "import roxieapi"` first).
4. If you cannot reach 2% / 2 percentage points for the multi-turn case
   after genuine investigation, report the honest number and your
   diagnosis — do not weaken any tolerance to force a pass. This mirrors
   binding precedent from tasks 0008, 0015, 0017, and 0018.
5. **Regression is the most severe possible failure for this task.** Your
   fix touches shared turn-geometry code used by every bore-field and
   margin calculation in the codebase. Re-run the existing bore-field and
   margin live-ROXIE tests yourself after your change and report the
   actual before/after numbers, not just "tests pass."
6. You may read `dipole_designer`'s `geometry_helpers.py` for
   understanding only (see TASK.md's Reference material) — do not copy
   code.
7. Run `pytest` and `ruff check` yourself, report actual output.
8. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Your hand-derivation of the correct arc-tangent projection formula, with
  the numeric comparison against the current wrong formula for the known
  failing case.
- Whether a spacing-only fix was sufficient, or per-turn tilt rotation was
  also required to hit tolerance — and why.
- Live ROXIE numbers for the failing case + at least one new multi-turn
  case (peak field and margin, diff %).
- Live ROXIE regression numbers for at least 3 previously-validated cases
  (CTH-14T, an 0015/0017 single-block case, an 0018 single-turn case) —
  explicit before/after comparison.
- Explicit statement of whether the 2%/2pp bar was achieved for the
  multi-turn case, with honest numbers either way.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. Start
by reproducing the `cth_lf_custom_two_turns_block` case and confirming you
see the same ~9.25% peak-field error and the same wrong `3.316 deg` angular
spacing (vs. ROXIE's ~5.78-6.027 deg) that TASK.md reports, before changing
anything — confirm your baseline is real.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- All live ROXIE validation numbers explicitly, both new-case and
  regression-case
