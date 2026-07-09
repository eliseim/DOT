# TASK: Named-conductor resolution + graceful unsupported-conductor handling

- **ID**: 0009-unsupported-conductor-handling
- **Status**: draft
- **Model/effort**: High effort. This closes a real correctness gap found
  while preparing to run the user's requested CTH campaign (4 layers:
  CTH_HF, CTH_HF, CTH_LF, CTH_LF): DOT's `.cadata` parser currently has no
  way to select a *named* conductor's self-consistent strand+cable+REMFIT
  triple — it grabs the first row of each section independently, which can
  silently mismatch components in any file defining more than one
  conductor (which `roxie_CTH_cables.cadata`, a completely normal
  real-world file, does — it defines 28). This is a real bug, not a
  hypothetical: without this fix DOT cannot correctly represent "layer 1
  uses CTH_HF, layer 3 uses CTH_LF" at all.

## Background

`.cadata` files have a `CONDUCTOR` section linking a name (e.g. `CTH_HF`)
to a specific `CABLE` name, `STRAND` name, `INSUL` name, `TRANSIENT` name,
`REMFIT` name, and operating temperature — e.g. (from
`roxie_CTH_cables.cadata:115-116`):
```
27 CTH_HF 1 CXF150HT5 STRXF09 QXF89H_HF INSXF145 OSTA NB3SNMP 1.9 'CTH_HF...'
28 CTH_LF 1 CTH_CERN  STR01_12 NBTII    ALLPOLYIL TRANS1 NBTILHC 1.9 'CTH_LF...'
```
Columns (in order): no, name, type(unused/always 1 here), cable_name,
strand_name, insul_name, transient_name, remfit_name, temperature_k,
comment.

DOT's `src/dot/conductors/cadata.py` currently parses `STRAND`, `CABLE`,
and `REMFIT` sections but never parses `CONDUCTOR`, so there is no way to
ask "give me the strand+cable+remfit for the conductor named CTH_HF" — the
GUI currently just takes the first row of each section independently
(`_first_conductor_data` in `target_synthesis_gui.py`), which happens to
work by accident for single-conductor files but is wrong in general.

Separately: `CTH_HF`'s REMFIT (`NB3SNMP`) is type 3 (Nb3Sn) — unsupported
by DOT (deliberately, per task 0004; unvalidated even in the reference
tool). `CTH_LF`'s REMFIT (`NBTILHC`) is type 1 (Nb-Ti) — supported. A
correct campaign for the user's CTH topology must let layers 1-2 (CTH_HF)
proceed geometrically (field/harmonics don't need conductor data) while
gracefully excluding them from load-line margin evaluation (which does),
rather than crashing the whole campaign or silently mismatching a
different conductor's data onto them.

## Goal

1. Parse the `CONDUCTOR` section and add named-conductor resolution that
   returns a correctly-linked `(StrandRecord, CableRecord,
   Type1FitCoefficients, temperature_k)` for a given conductor name — or a
   clear, typed "unsupported" result (not an unhandled crash) if that
   conductor's REMFIT type isn't type 1.
2. Let the GUI select a conductor **by name** per layer (a new field,
   alongside the existing file path), instead of "first supported record
   in the file" (which stays as a fallback default for
   backward-compatibility, not removed).
3. Let a layer proceed in a campaign with geometry-only (no load-line
   margin evaluated) if its named conductor is unsupported, rather than
   crashing. The margin objective/proxy must skip turns belonging to such
   layers when searching for the field-limiting turn, and the campaign
   result must clearly flag which layers' margin wasn't evaluated.

## Scope (files/modules Codex may touch)

- `src/dot/conductors/cadata.py` — add `ConductorRecord` dataclass and
  CONDUCTOR-section parsing; add
  `resolve_conductor(text, name) -> ConductorResolution` (a result type
  distinguishing "resolved" vs "unsupported fit type" vs "conductor name
  not found" — pick a clean shape, e.g. a small union/Result type or a
  dataclass with an optional `unsupported_reason` field; state your choice).
- `src/dot/optimize/objectives.py` — `LayerConductorData` becomes optional
  per layer conceptually (the type stored per layer can be `None` to mean
  "not evaluated"); `_peak_field_on_own_turns` and
  `load_line_margin_objective` must skip layers with `None` conductor data
  when searching for the margin-limiting turn, falling back to the next
  highest-field turn in a layer that does have data. If literally every
  layer lacks conductor data, raise a clear error (there is no margin to
  report at all).
- `src/dot/optimize/problem.py`, `src/dot/optimize/runner.py` — update
  `cadata_by_layer` typing/plumbing to carry `LayerConductorData | None`
  per layer, and surface (in whatever result type `run_campaign` returns)
  which layers were excluded from margin evaluation and why.
- `src/dot/gui/target_synthesis_gui.py` — add a per-layer "Conductor name"
  text field (default empty = fall back to `first_supported_remfit`
  behavior for backward compatibility); wire it to
  `resolve_conductor`; if unsupported, store `None` for that layer's
  conductor data instead of raising, and show the reason in the results
  panel/log rather than crashing the campaign.
- `tests/conductors/test_cadata.py`, `tests/optimize/test_objectives.py`,
  `tests/optimize/test_problem.py`, `tests/optimize/test_runner.py`,
  `tests/gui/test_target_synthesis_gui.py` — extend as needed.

## Explicit non-goals

- Still no Nb3Sn/type-3/type-11 Jc computation. This task makes the
  *absence* of that support a clean, informative, non-crashing outcome —
  it does not add the physics.
- No change to how margin is computed for conductors that ARE supported —
  only how unsupported ones are handled (skip + flag, not crash or
  mismatch).
- No UI polish beyond a plain text field for conductor name.

## Reference material

- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — real
  file with the `CONDUCTOR` section format and the exact `CTH_HF`/`CTH_LF`
  records referenced above. Read-only.

## Acceptance criteria

- [ ] A test parses the real `roxie_CTH_cables.cadata` CONDUCTOR section
      and correctly resolves `CTH_LF` to its linked strand/cable/remfit
      (matching the values already used in task 0008's parity test:
      strand diameter 1.065mm... actually verify against the real STRAND
      `STR01_12` row and CABLE `CTH_CERN` row directly, don't assume) and
      confirms `CTH_HF` resolves with an "unsupported fit type" result
      (not an exception escaping uncaught, not a silently wrong
      substitution).
- [ ] A campaign built with a 4-layer topology where layers 1-2 have
      unsupported conductors and layers 3-4 have supported ones completes
      without crashing, produces feasible candidates, and its result
      clearly indicates layers 1-2's margin was not evaluated (not just
      silently omitted with no trace).
- [ ] The margin proxy correctly falls back to the highest-field turn
      *among layers with conductor data* when the true highest-field turn
      overall belongs to an unsupported-conductor layer — test this
      explicitly with a constructed case where you can predict which turn
      should be selected.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken; no
      files outside declared scope modified.

## Notes / open questions

- If a cleaner design emerges for the "optional per-layer conductor data"
  plumbing than a bare `None`, use it, but keep it simple — a
  `LayerConductorData | None` tuple element is probably sufficient; don't
  build a bigger result-wrapper abstraction than needed.
