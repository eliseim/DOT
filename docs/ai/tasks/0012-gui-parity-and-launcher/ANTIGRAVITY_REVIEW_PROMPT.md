# Antigravity independent review prompt — TASK 0012-gui-parity-and-launcher

You are reviewing a diff produced by another AI worker (Codex) for DOT's
GUI: exposing previously-hidden geometry gap fields (with new, physically
load-bearing default values) and adding campaign name/output-dir fields.
You did not see the worker's reasoning — judge only the diff, the
repository, and the task spec.

## Inputs

- `docs/ai/tasks/0012-gui-parity-and-launcher/TASK.md`
- The diff/commit on branch `task/0012-gui-parity-and-launcher`.

## What to check

1. **Default value correctness.** Confirm `DEFAULT_STATE`'s
   `min_gap_mm`/`min_layer_clearance_mm` are actually `0.15`/`0.5` now
   (not left at `0.1`, not swapped with each other — midplane gap is
   `0.15`, radial/inter-layer gap is `0.5`, check they're not
   transposed).
2. **Field wiring.** Confirm the new GUI entry fields actually feed into
   `_campaign_inputs()`'s `FeasibilitySettings` construction (not just
   displayed but disconnected from the actual campaign run — a field that
   looks editable but doesn't affect the search would be worse than not
   having it, since it would mislead the user).
3. **Backward compatibility.** Find and run/inspect the test loading an
   old-format config dict missing the new keys — confirm it doesn't raise,
   and confirm the fallback values are sensible (the new defaults, not
   `0`/`None`/crash).
4. **Scope discipline.** Only declared files touched? No iron/topology-
   search/ROXIE-backend sections added?

## Output format

Findings ranked most-severe first (a wrong/transposed default value is the
most severe class here, since it would silently apply the wrong
feasibility gap). For each: file, line, what's wrong, concrete failure
scenario. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.
