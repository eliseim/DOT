# Codex worker prompt — TASK 0018-peak-field-and-loadline-margin-parity

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0018-peak-field-and-loadline-margin-parity/TASK.md` in this
worktree fully before writing any code — it contains the full diagnostic
history (what's broken, what was already tried, what converged and what
didn't) and you must not re-derive it from scratch or ignore it.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Do not touch the bore-field/harmonics code path
   (`multipole_coefficients`, or how `field_at`/sources are used for total
   field superposition) — this task is scoped to the near-field
   peak-on-own-conductor evaluation used by `load_line_margin_objective`
   only.
3. **The real bar for this task is live ROXIE re-validation.** You have
   access to the live ROXIE REST service at `http://127.0.0.1:8080` via
   `roxieapi` (installed on system Python; run your validation script with
   that Python rather than a fresh venv — check
   `python -c "import roxieapi"` first).
4. TASK.md's diagnostic already shows the dominant bug (3x3 filament
   discretization is far too coarse) is fixable, but a genuine ~3.5-4.4%
   residual remains after fixing it. Your job is not just "raise the
   resolution and stop" — you must investigate and either close the
   residual gap or prove, with a hand derivation, why it's a genuine limit
   of the current line-current model. If you cannot close it to 2% and
   determine it's a real, understood limitation, report the honest number
   and your derivation — do not weaken any tolerance to force a pass. This
   mirrors binding precedent from tasks 0008, 0015, and 0017.
5. You may read `dipole_designer`'s `roxie/parser.py` for understanding
   only (see TASK.md's Reference material) — note that it does NOT contain
   an independently-derived peak-field formula to copy; it just parses
   ROXIE's own output. This is genuinely new physics work.
6. Run `pytest` and `ruff check` yourself, report actual output.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Your hand-derivation for at least one simple single-turn case (show the
  math, not just a description).
- What the root cause of the residual gap turned out to be, and what you
  changed (or, if genuinely irreducible, why).
- Live ROXIE numbers for peak field AND load-line margin on at least 5
  cases (reuse the CTH_LF-only pattern from TASK.md's background, or your
  own designs — include at least 1 single-turn and 1 multi-layer case).
- Confirmation the existing bore-field live-ROXIE tests still pass
  unchanged (no regression).
- Explicit statement of whether 2% (peak field) / 2 percentage points
  (margin) was actually achieved, with the honest final numbers either way.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. Start
by reproducing the two diagnostic cases in TASK.md's background yourself
(don't just trust the reported numbers) — confirm you get the same ~4.36%
and ~3.46% residuals at converged discretization before trying to fix
anything, so you know your baseline is real.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- All live ROXIE validation numbers explicitly (peak field diff % and
  margin diff in percentage points, per case)
