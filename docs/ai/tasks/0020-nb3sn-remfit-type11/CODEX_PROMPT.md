# Codex worker prompt — TASK 0020-nb3sn-remfit-type11

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0020-nb3sn-remfit-type11/TASK.md` in this worktree fully
before writing any code. It contains the authoritative formula (from a
ROXIE documentation screenshot at the repo root,
`critical_current_density_fits.png` — read the image directly) and a
verified column-mapping derivation from real cadata rows. Read the image
yourself and confirm you agree with the formula transcription in TASK.md
before proceeding — don't just trust the markdown transcription blindly,
the image is the primary source.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Do not modify the existing Bottura (type-1) implementation in
   `critical_surface.py` or `Type1FitCoefficients` in `cadata.py` — add
   alongside it, don't refactor it.
3. **The real bar for this task is live ROXIE re-validation** — you have
   access to the live ROXIE REST service at `http://127.0.0.1:8080` via
   `roxieapi` (installed on system Python; check
   `python -c "import roxieapi"` first). This is the first time CTH_HF
   margin can be validated at all, so there is no prior baseline to compare
   against — your live numbers are the ground truth check.
4. If you cannot reach 2% / 2 percentage points for CTH_HF cases after
   genuine investigation, report the honest number and your diagnosis —
   do not weaken any tolerance to force a pass. This mirrors binding
   precedent from every prior task in this project (0008, 0015, 0017,
   0018, 0019).
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering:
- Your independent confirmation of the formula (re-read the image
  yourself) and the column mapping.
- Hand-derivation of `Jc(B,T)` for at least one point using `HFM1`'s
  coefficients, matching your implementation's output.
- Live ROXIE numbers for at least 1 CTH_HF-only case and 1 mixed
  CTH_HF+CTH_LF case (peak field diff %, margin diff pp).
- Confirmation the existing CTH_LF-only margin tests (tasks 0018/0019)
  still pass unchanged.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, must be 100% passing)
- All live ROXIE validation numbers explicitly
