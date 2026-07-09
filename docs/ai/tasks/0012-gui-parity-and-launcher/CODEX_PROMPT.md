# Codex worker prompt — TASK 0012-gui-parity-and-launcher

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0012-gui-parity-and-launcher/TASK.md` in this worktree fully
before writing any code. Read the current `src/dot/gui/target_synthesis_gui.py`
and `src/dot/gui/config_io.py` fully first — do not guess the existing
field/state structure.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Changing `min_gap_mm`/`min_layer_clearance_mm` defaults from `0.1` to
   `0.15`/`0.5` is a deliberate, load-bearing change (matches the real CTH
   dipole's actual gaps) — do it explicitly in `DEFAULT_STATE`, not just in
   a GUI placeholder.
3. Backward compatibility: loading an old saved config JSON that lacks the
   new campaign-name/output-dir keys must not crash — fall back to
   sensible defaults. Write a test proving this.
4. No iron/topology-search/ROXIE-backend sections — still explicitly out
   of scope per DOT's existing design decisions.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: where the new
"Geometry / Manufacturability" section was added, the new default values,
and confirmation the backward-compatibility test passes.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. Reuse
the existing `_entry(frame, label, var, row)` helper pattern already used
elsewhere in the file for consistency. Reuse the existing file-picker
pattern (used for `.cadata` selection) for the output-directory picker,
adapted to `filedialog.askdirectory`.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite)
