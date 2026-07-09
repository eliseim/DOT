# Antigravity independent review prompt — TASK 0006-target-synthesis-gui

You are reviewing a diff produced by another AI worker (Codex) for DOT's
user-facing GUI. You did not see the worker's reasoning — judge only the
diff, the repository, and the task spec. This is the deliverable the user
will actually click through, so correctness of the non-GUI logic (threading
safety, cross-section mirroring, config round-trip) matters as much as ever,
even though full UI rendering verification is the coordinator's manual job,
not yours.

## Inputs

- `docs/ai/tasks/0006-target-synthesis-gui/TASK.md`
- The diff/commit on branch `task/0006-target-synthesis-gui`.
- `src/dot/physics/field.py`'s `dipole_mirror_sources` (already merged) —
  the ground truth mirroring convention to check the plot code against.

## What to check

1. **Thread safety.** Does `campaign_runner.py` ever mutate a Tk widget or
   call a Tk method directly from the background thread, or does it
   strictly communicate via the queue, with the Tk main thread doing all
   widget updates via `root.after(...)` polling? A direct cross-thread
   widget call is a real (if sometimes intermittent) crash/corruption bug
   in Tkinter — flag it if found, even if it "seems to work" in casual
   testing.
2. **Cross-section mirror convention consistency.** Compare
   `cross_section_plot.py`'s quadrant-mirroring logic line-by-line against
   `physics/field.py`'s `dipole_mirror_sources`: same sign flips for the
   same quadrants? If the plot uses a different (even if individually
   "valid-looking") mirroring rule than the physics engine, the displayed
   cross-section could visually contradict the actual field computation —
   this is a user-facing correctness issue, not a cosmetic one.
3. **Campaign runner correctness.** Does the background thread wrapper
   actually call `run_campaign` with the same arguments the GUI form
   collected (spot-check a couple of fields end to end from form-state dict
   to `run_campaign` call)? Does the "stop" mechanism (if implemented)
   actually stop, or is it a no-op button that misleads the user into
   thinking a long campaign was cancelled when it's still running?
4. **Config round-trip fidelity.** Does `load_config(save_config(state))`
   reproduce `state` exactly, including nested per-layer structures? Any
   field silently dropped or defaulted incorrectly?
5. **Launch-readiness / mandatory fields.** Does the GUI prevent starting a
   campaign with missing/invalid required fields (e.g. no cadata file
   selected, zero layers), or could a malformed form state reach
   `run_campaign` and crash mid-run instead of failing fast with a clear
   message?
6. **Scope discipline.** Only declared files + the `matplotlib` gui-extras
   addition touched? No topology-search UI, no iron config section, no
   PySide6, no subprocess/ROXIE architecture introduced despite being
   explicitly out of scope?
7. **Test quality.** Are `campaign_runner`/`cross_section_plot`/`config_io`
   tested without requiring a real Tk event loop (i.e., can they run in a
   headless CI-like environment)?

## What NOT to do

Do not attempt to actually render/screenshot the Tkinter window yourself —
that is the coordinator's manual verification step, separate from this
review. Focus on the logic that determines whether the app, once launched,
behaves correctly and safely.

## Output format

Findings ranked most-severe first (thread-safety and mirror-convention
mismatches are the most severe class here — they'd corrupt the UI or
mislead the user silently). For each: file, line, what's wrong, concrete
failure scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
