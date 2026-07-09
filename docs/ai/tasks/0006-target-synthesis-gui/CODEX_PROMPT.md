# Codex worker prompt — TASK 0006-target-synthesis-gui

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0006-target-synthesis-gui/TASK.md` in this worktree fully
before writing any code. This is the user-facing deliverable — the
coordinator will manually launch and click through what you build, so it
must actually run, not just pass unit tests.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Tkinter only (stdlib) for widgets; `matplotlib` is the only new
   dependency, under `[project.optional-dependencies.gui]`.
3. Read the actual public APIs of `src/dot/optimize/runner.py` (`run_campaign`
   and whatever result type it returns), `src/dot/geometry/primitives.py`,
   `src/dot/conductors/cadata.py`, and `src/dot/physics/field.py`'s mirror
   convention (`dipole_mirror_sources`) before designing the GUI/plot code
   — do not guess signatures.
4. Background campaign execution must use a `threading.Thread` + a
   thread-safe queue, with the Tk main loop polling the queue via
   `root.after(...)`. Never mutate Tk widgets directly from the worker
   thread.
5. The cross-section plot's quadrant-mirroring must use the *same*
   sign/position convention as `physics/field.py`'s `dipole_mirror_sources`
   — verify this explicitly and state so in your summary.
6. No topology search UI, no iron config section, no subprocess/ROXIE
   architecture — see TASK.md's non-goals.
7. Write the tests specified in TASK.md's acceptance criteria (logic only,
   not raw Tkinter rendering), run `pytest` and `ruff check` yourself,
   report actual output.
8. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the threading/
queue architecture used for the background campaign, confirmation the
cross-section mirror convention matches `physics/field.py`, and full test
output. Also state exactly how to launch the app (the command) so the
coordinator can run it manually.

## Task-specific instructions

Implement, in this order:

1. `pyproject.toml`: add `gui = ["matplotlib>=3.7"]` under
   `[project.optional-dependencies]`.
2. `src/dot/gui/config_io.py`: `save_config(state: dict, path) -> None` /
   `load_config(path) -> dict` — plain JSON round-trip of the GUI's form
   state (target field, aperture radius, per-layer topology/cadata path/
   turn bounds, acceptance targets, NSGA-II params).
3. `src/dot/gui/cross_section_plot.py`: a function taking a `DipoleDesign`
   and returning a matplotlib `Figure` with every turn polygon drawn,
   mirrored into all four quadrants using the same sign convention as
   `dipole_mirror_sources` (reuse or reimplement identically — state which
   and why). Aperture circle drawn for reference.
4. `src/dot/gui/campaign_runner.py`: a class/function wrapping
   `run_campaign` in a `threading.Thread`, pushing progress messages (e.g.
   "generation N/M evaluated") and the final `ParetoResult` onto a
   `queue.Queue`, with a way to request a cooperative stop between
   generations if `run_campaign`/pymoo's callback mechanism supports it
   (if it doesn't cleanly support mid-run cancellation, let the thread run
   to completion and just don't block the UI — state this limitation
   explicitly rather than faking a stop button that doesn't actually
   stop).
5. `src/dot/gui/target_synthesis_gui.py`: the Tkinter `App`/`Tk` subclass
   assembling the sections from TASK.md, wiring "Run Campaign" to
   `campaign_runner`, polling its queue via `root.after(100, ...)`,
   displaying results and the cross-section plot (via
   `matplotlib.backends.backend_tkagg.FigureCanvasTkAgg`), and wiring
   Save/Load Config to `config_io`. Include a `if __name__ == "__main__":`
   block that launches the app, and note the exact run command in your
   summary.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + all previously merged tests must still pass)

Do not attempt to verify the Tkinter window renders correctly yourself —
that verification is the coordinator's manual pass. Focus your own testing
on the non-GUI logic (queue/thread wrapper, plot data mirroring, config
round-trip).
