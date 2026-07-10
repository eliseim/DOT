# Codex worker prompt — TASK 0015-absolute-alpha-and-chord-stacking

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0015-absolute-alpha-and-chord-stacking/TASK.md` in this
worktree fully before writing any code — it contains a verified derivation
with exact formulas and numbers, use them directly rather than re-deriving
from scratch. Read the current `src/dot/geometry/primitives.py` fully
first — do not guess its structure.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Implement the exact phi-independent `height_axis`/`width_axis` formulas
   given in TASK.md's "Background" section:
   `height_axis(alpha_dot) = (cos(alpha_dot), -sin(alpha_dot))`,
   `width_axis(alpha_dot) = (sin(alpha_dot), cos(alpha_dot))` — these
   replace the current phi-dependent rotation. Do not change the
   `phi_deg`/anchor-point computation, which is already correct.
3. Implement straight-chord turn stacking in `Block.turns()`: turn `k`'s
   anchor is `turn_0_anchor + k * cable.insulated_width_mm * width_axis`,
   not the current polar-arc stepping.
4. **The real bar for this task is the live ROXIE re-validation** described
   in TASK.md's acceptance criteria — you have access to a live ROXIE REST
   service at `http://127.0.0.1:8080` via the `roxieapi` package (already
   installed on this machine's Python — NOT necessarily in a venv you
   create, so you may need to either install `roxieapi` into your test
   venv or invoke your validation script with the system Python that
   already has it; check `python -c "import roxieapi"` first). Actually
   run this validation and report the real numbers. Do not skip it and
   claim success based on unit tests alone.
5. If, after implementing both fixes, live ROXIE comparison still doesn't
   reach 2%, report the honest number and your diagnosis — do not weaken
   any test tolerance to force a pass. This mirrors the same instruction
   from task 0008, which you should treat as binding precedent.
6. You may read `dipole_designer`'s `geometry_helpers.py` for
   understanding only — do not copy code, DOT's implementation must be
   independently written using the already-converted formulas given in
   TASK.md.
7. Run `pytest` and `ruff check` yourself, report actual output.
8. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: confirmation the
unit tests reproduce the coordinator's exact derived numbers, the
live-ROXIE validation results for both the real CTH-14T design and the
alpha=0 single-block case (reported separately, per TASK.md), and full
test output including how you verified the live-ROXIE test skips cleanly
without a reachable service.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely, using
the exact formulas already derived there — your job is correct
implementation and rigorous validation, not re-deriving the physics.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite, including the new live-ROXIE test if the
  service is reachable in your environment — check first)
- The live ROXIE validation numbers explicitly, even if you also captured
  them via the test.
