# TASK: target_synthesis GUI (DOT's user-facing application)

- **ID**: 0006-target-synthesis-gui
- **Status**: draft
- **Model/effort**: High effort for Codex (a lot of integration surface,
  threading, and a real UI a human will actually click through); high
  effort for Antigravity (must actually launch the app, not just read
  code). This is the first task where the coordinator will also manually
  launch and drive the app before declaring it done, per project policy on
  UI changes.

## Goal

A working Tkinter desktop application, `target_synthesis_gui.py`, that lets
a magnet designer: enter a target bore field, aperture radius, a fixed coil
topology (number of layers, blocks per layer, a `.cadata` cable file per
layer), acceptance targets (max allowed harmonic, minimum load-line
margin), and NSGA-II search parameters; click "Run Campaign"; watch
progress; and see the best feasible candidate's results (achieved field,
max harmonic, margin, operating current) plus a 2D cross-section plot of
its coil geometry (mirrored to the full circle, not just one quadrant).

This mirrors `dipole_designer`'s `target_synthesis_gui.py` in spirit and
section layout (per the user's requirement that DOT's GUI be recognizable
to someone who's used that tool), but is **scoped down to match what DOT's
optimizer (task 0005) actually does today**: fixed topology, no ROXIE, no
subprocess/polling architecture (DOT's campaign is fast pure-Python, so it
runs in a background thread within the same process, not a spawned
subprocess with a JSON status file). Do not attempt to replicate
topology-search-specific sections (turn-density controls, adaptive
admission, staged refinement, iron configuration) — none of that exists in
DOT yet; adding UI for it now would be pure overengineering.

## Scope (files/modules Codex may touch)

- `pyproject.toml` — add `matplotlib` under `[project.optional-dependencies.gui]` (Tkinter itself is stdlib, no new dependency needed for the widgets).
- `src/dot/gui/__init__.py`
- `src/dot/gui/target_synthesis_gui.py` — the Tkinter application.
- `src/dot/gui/campaign_runner.py` — a thin background-thread wrapper
  around `src/dot/optimize/runner.py::run_campaign`, exposing progress
  callbacks/queue for the GUI to poll (no subprocess, no JSON polling
  files — this runs in-process since DOT has no ROXIE dependency to
  isolate).
- `src/dot/gui/cross_section_plot.py` — renders a `DipoleDesign` (mirrored
  into all four quadrants) as a matplotlib figure of filled turn polygons.
- `src/dot/gui/config_io.py` — save/load the GUI's form state to/from a
  JSON file.
- `tests/gui/test_campaign_runner.py`
- `tests/gui/test_cross_section_plot.py`
- `tests/gui/test_config_io.py`

## GUI sections (mirroring target_synthesis_gui's structure, scoped to what DOT supports today)

1. **Magnet Physics**: target bore field (T), aperture radius (mm), number
   of layers (1-4, dynamically shows a per-layer row when changed).
2. **Per-Layer Topology**: for each layer — `.cadata` file picker (parsed
   via task 0004's `cadata.py`), number of blocks, per-block turn-count
   bounds (min/max, used as genome integer bounds), operating temperature
   (K, shared or per-layer, keep it simple: one global value).
3. **Acceptance Targets**: max |harmonic| (units of 1e-4), minimum required
   load-line margin (%). These are used to color/flag the result as
   "meets targets" or not — DOT's optimizer treats them as Pareto
   objectives to minimize/maximize (per task 0005), not hard constraints,
   so the GUI's job is to report where the best candidate(s) land relative
   to these targets, not to force the search to stop early.
4. **NSGA-II Parameters**: population size, generations, seed.
5. **Run controls**: "Run Campaign" / "Stop" buttons, a progress
   indicator (generation count / population evaluated), a scrollable log.
6. **Results**: best balanced candidate's achieved bore field, max
   |harmonic|, load-line margin %, operating current (A), whether it meets
   the acceptance targets, and the cross-section plot.
7. **Save/Load Config**: JSON round-trip of the form state (not results).

## Explicit non-goals

- No topology search UI (turn-density controls, adaptive admission, staged
  refinement) — task 0005's optimizer doesn't support this yet.
- No iron configuration section — DOT is no-iron by design.
- No subprocess/multi-process campaign execution, no JSON status-file
  polling — run in a background `threading.Thread` within the same
  process and communicate via a thread-safe queue, since there is no
  ROXIE process to isolate from.
- No ROXIE code, no ROXIE dependency anywhere.
- No PySide6/Qt — Tkinter only (stdlib, no new heavy GUI dependency).
- No packaging/installer work (that's a separate future concern).

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\examples\target_synthesis\target_synthesis_gui.py`
  (retrievable via `git show HEAD:examples/target_synthesis/target_synthesis_gui.py`
  from within that repo if not present on disk — see coordinator's earlier
  research notes) and `campaign_config.py` — read for section layout,
  field grouping, and the general shape of a launch-readiness gate
  (disabling "Run" until mandatory fields are filled). Do not copy code —
  that GUI is PySide-adjacent/Tkinter with a subprocess-based campaign
  architecture DOT deliberately does not replicate (see non-goals).
- `C:\Users\elisei\Desktop\dipole-optimization-tool\src\dipole_opt\gui\target_synthesis_window.py`
  — a PySide6 port of the same GUI; useful for cross-checking which fields
  matter most, but DOT uses Tkinter, not PySide6, so structure will differ
  substantially. Do not copy.

## Acceptance criteria

- [ ] `python -m dot.gui.target_synthesis_gui` (or equivalent entry point)
      launches without error and shows all sections listed above.
- [ ] `campaign_runner.py`'s background-thread wrapper is tested
      independently of Tkinter (no GUI event loop needed in the test):
      starting a campaign with tiny pop/gen returns progress updates via
      the queue and a final result matching what calling
      `run_campaign` directly would produce for the same seed/inputs.
- [ ] `cross_section_plot.py` is tested independently of the GUI: given a
      small hand-built one-quadrant `DipoleDesign`, the mirrored full-circle
      plot data (before rendering) contains turns in all four quadrants
      with correctly mirrored coordinates (reuse/verify against the same
      mirroring convention as `physics/field.py`'s `dipole_mirror_sources`
      for consistency — check this explicitly, a mismatched mirror
      convention between the physics engine and the display would silently
      show a misleading cross-section).
- [ ] `config_io.py` save/load round-trips a form-state dict exactly.
- [ ] `ruff check` clean; `pytest` passes (GUI logic tests only — do not
      attempt to unit-test raw Tkinter widget rendering, that's what the
      coordinator's manual launch-and-click pass is for); no existing
      tests broken; no files outside declared scope modified.
- [ ] **Coordinator will manually launch the app and run a real, tiny
      campaign through the UI before this task is considered done** — this
      is not optional and not satisfied by automated tests alone.

## Notes / open questions

- Keep the mirroring convention for the cross-section plot consistent with
  `physics/field.py`'s dipole mirror images (same 4-quadrant sign/position
  rule) — this is the one place a subtle inconsistency would be visually
  confusing but easy to miss in code review, flag it explicitly in the
  summary.
- Threading model: Tkinter is not thread-safe for widget updates from a
  background thread. Use a queue + `root.after(...)` polling pattern (the
  standard safe approach), not direct widget mutation from the worker
  thread. State this explicitly in the summary so it can be checked.
