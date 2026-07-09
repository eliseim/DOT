# TASK: GUI parity pass (geometry gap fields, campaign fields)

- **ID**: 0012-gui-parity-and-launcher
- **Status**: draft
- **Model/effort**: Medium-high effort. Mostly GUI wiring, but the gap-field
  defaults are physically load-bearing (they gate feasibility) so treat
  the default-value change with the same care as a physics parameter.

## Goal

The user wants DOT's GUI to closely resemble `dipole_designer`'s
`target_synthesis_gui`, with cadata handling as the intentional
difference. Two concrete gaps found by the coordinator:

1. **Midplane gap (`min_gap_mm`) and inter-layer radial gap
   (`min_layer_clearance_mm`) exist in `DEFAULT_STATE`/feasibility
   plumbing but are not exposed as editable GUI fields** — they're
   hardcoded at `0.1`/`0.1` with no way for the user to see or change
   them. The real CTH dipole (and the user's explicit requirement) needs
   `0.15` mm midplane gap and `0.5` mm radial gap. These must become
   visible, editable fields with those as the new defaults (not `0.1`).
2. **No campaign name / output directory fields**, unlike
   `dipole_designer`'s GUI which has this as its first section. Add a
   small "Campaign" section (name, output directory with a folder picker)
   at the top of the form. Wire "Save Config" to default its suggested
   filename/location into that output directory (a light touch — do not
   build a new results-file-management system, just improve the default
   save location).

## Scope (files/modules Codex may touch)

- `src/dot/gui/target_synthesis_gui.py`
- `src/dot/gui/config_io.py` (only if the campaign name/output-dir fields
  need new keys in the saved config schema — extend, do not break
  existing saved-config round-trip compatibility for files that predate
  these fields; missing keys must default sensibly on load, not crash).
- `tests/gui/test_target_synthesis_gui.py`, `tests/gui/test_config_io.py`

## Explicit non-goals

- No iron-configuration section (DOT is no-iron by design, already
  decided in task 0006).
- No topology-search-specific sections (turn-density controls, adaptive
  admission, staged refinement) — still out of scope, DOT's optimizer
  doesn't do topology search.
- No ROXIE execution-mode/backend section — not applicable to DOT.
- No change to the actual campaign execution architecture (still an
  in-process background thread, not dipole_designer's subprocess+polling
  design) — that was an intentional, already-reviewed simplification.
- No visual/styling overhaul — plain ttk widgets matching the existing
  style are fine.

## Acceptance criteria

- [ ] Midplane gap and radial (inter-layer) gap are visible, editable GUI
      entry fields (a natural home: a new "Geometry / Manufacturability"
      `LabelFrame`, alongside the existing per-layer max-pole-angle field
      from task 0010).
- [ ] `DEFAULT_STATE`'s feasibility defaults change from `0.1`/`0.1` to
      `0.15` (midplane) / `0.5` (radial) — verify this doesn't silently
      break any existing test that hardcoded the old `0.1` default; update
      those tests deliberately if so (not accidentally).
- [ ] Campaign name and output-directory fields exist at the top of the
      form; output directory has a folder-picker button
      (`filedialog.askdirectory`, matching the existing file-picker
      pattern used for `.cadata` selection).
- [ ] Config save/load round-trips the new fields; loading an **old**
      saved config file that predates these fields does not crash — it
      falls back to sensible defaults for the missing keys (test this
      explicitly with a config dict that omits the new keys).
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken; no
      files outside declared scope modified.

## Notes / open questions

- Keep the new "Geometry / Manufacturability" section's field count small
  — just the two gap values (DOT only implements 5 feasibility
  constraints per task 0003's deliberate scope, not the full C1-C19 set
  `dipole_designer` has, so there's nothing else meaningful to expose
  here yet).
