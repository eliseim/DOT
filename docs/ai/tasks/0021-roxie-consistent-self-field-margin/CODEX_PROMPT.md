# Codex worker prompt — TASK 0021-roxie-consistent-self-field-margin

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0021-roxie-consistent-self-field-margin/TASK.md` in this
worktree fully before writing any code. It documents a real, previously
undiscovered gap: DOT's peak-field-for-margin calculation (task 0018) uses
a fundamentally different methodology than ROXIE's own documented
algorithm. Read the two CERN ROXIE documentation URLs in TASK.md's
Reference material yourself (fetch them directly) — do not just trust the
summary, confirm it against the source.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. **Fix the comparison/validation methodology first**, per Goal 1, before
   changing any production code. Get a clean, per-conductor baseline
   reading with the *existing* (pre-0021) implementation first, so you can
   tell how much this task's changes actually improve things.
3. Do not touch `src/dot/geometry/*` — turn geometry (corners, stacking)
   is correct and twice-validated; this task only changes what points are
   sampled for near-field peak evaluation and how self-field is handled.
4. Do not touch the bore-field code path.
5. **The real bar for this task is live ROXIE re-validation, per
   conductor** — not an aggregated worst-case number. You have access to
   the live ROXIE REST service at `http://127.0.0.1:8080` via `roxieapi`
   (installed on system Python; check `python -c "import roxieapi"`
   first).
6. If you cannot close the gap after genuine investigation, report the
   honest numbers and your diagnosis — do not weaken any tolerance to
   force a pass. This mirrors binding precedent from every prior task in
   this project.
7. Run `pytest` and `ruff check` yourself, report actual output.
8. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Confirmation you read the CERN ROXIE documentation URLs directly.
- The corrected, per-conductor baseline reading (existing implementation)
  vs. your new implementation's per-conductor numbers, for the same cases
  — a clear before/after.
- Your hand-derivation for a simple case.
- Live ROXIE per-conductor validation numbers for at least 3 cases (see
  TASK.md Goal 4).
- Confirmation the aggregated worst-case numbers from tasks 0018/0019/0020
  don't regress.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- All live ROXIE validation numbers explicitly, per-conductor
