# TASK: Per-layer pole-angle limit + operating current cap

- **ID**: 0010-per-layer-angle-and-current-cap
- **Status**: draft
- **Model/effort**: High effort. Feasibility-gate correctness; a bug here
  either lets an unbuildable/unsafe design through (bad) or wrongly
  rejects valid designs (blocks the campaign from ever succeeding).

## Goal

The user requires DOT's feasibility checks to match the real CTH dipole's
actual geometric constraints:
- Aperture radius 25 mm (already a per-run input, no change needed).
- Radial gap between layers: 0.5 mm (already supported via
  `min_layer_clearance_mm`, no change needed — just confirm it's honored).
- Azimuthal/midplane gap: 0.15 mm for each layer (already supported via
  `min_gap_mm`, applied uniformly to all layers — confirm this matches
  "for each layer" intent; it does, since it's a single required minimum
  gap applied per-turn regardless of layer).
- **Pole-angle limit must be settable per layer**, not just one global
  value: the real CTH design uses layer 1 max angle = 80°, and looser
  limits for outer layers (the reference `cth_14t_reference.yaml` fixture
  documents layer_1=80°, layer_2=85°, layer_3=87° for a 3-layer design).
  DOT's `check_pole_angle_limit`/`check_feasibility` currently accept only
  one global `max_angle_deg` for all layers — this must become per-layer.
- **Operating current must be capped at 13000 A.** DOT currently computes
  the operating current via exact linear scaling to hit the target bore
  field (task 0005), with no upper bound. A candidate whose required
  operating current exceeds the cap must be treated as infeasible (the
  same way a geometric violation is), not silently accepted.

## Scope (files/modules Codex may touch)

- `src/dot/geometry/constraints.py` — `check_pole_angle_limit` and
  `check_feasibility` gain per-layer `max_angle_deg` support.
- `src/dot/optimize/problem.py` — `FeasibilitySettings.max_angle_deg`
  becomes per-layer capable; add `OptimizationTargets.max_current_a`
  (optional, `None` = no cap) and reject candidates whose
  `operating_point(...).operating_current_a` exceeds it (mark infeasible,
  same penalty pattern as a geometric violation — do not silently clip the
  current).
- `src/dot/gui/target_synthesis_gui.py` — expose a "Max current [A]" field
  and per-layer "Max pole angle [deg]" field (default sensible values, see
  below), wire through to the new targets/feasibility fields.
- Corresponding test files under `tests/geometry/`, `tests/optimize/`,
  `tests/gui/`.

## API design guidance

- `check_pole_angle_limit(design, max_angle_deg: float | Sequence[float])`:
  if a single `float`, apply to all layers (backward compatible with
  existing callers/tests); if a sequence, its length must equal
  `len(design.layers)`, applying layer-by-layer. Raise `ValueError` on a
  length mismatch — do not silently truncate/pad or fall back to the
  first value.
- `check_feasibility`'s `max_angle_deg` parameter follows the same
  `float | Sequence[float]` shape.
- `FeasibilitySettings.max_angle_deg` follows the same shape (so it can be
  passed straight through to `check_feasibility`).
- Default per-layer angle values to use throughout (for the GUI defaults
  and the coordinator's next CTH campaign — do not hardcode these as
  magic constants, expose them as configurable fields with these as
  defaults): layer 1 = 80°, all other layers = 85° (sourced from the real
  CTH reference fixture's layer_2 value, documented as the default for any
  layer beyond the first since no more specific reference value was
  available for a 4-layer topology).
- `max_current_a: float | None` on `OptimizationTargets`, `None` meaning
  "no cap" (backward compatible default for existing tests/campaigns).

## Explicit non-goals

- No change to `min_gap_mm`/`min_layer_clearance_mm` semantics — these are
  already correctly global-per-run values matching the user's "0.5mm
  radial gap, 0.15mm midplane gap for each layer" requirement (a single
  required minimum applies uniformly; that already means "for each
  layer").
- No alpha/genome changes — that's a separate task (0011).
- No GUI section redesign beyond adding the two new fields — a broader
  GUI parity pass is a separate task (0012).

## Acceptance criteria

- [ ] `check_pole_angle_limit` with a per-layer sequence correctly applies
      a tighter limit to layer 1 and a looser one to other layers — test
      with a design where layer 1's turn would violate 80° but pass at
      85°, confirming it's flagged when checking against the per-layer
      sequence `[80, 85, ...]` but would NOT be flagged if checking
      against a uniform 85°. This proves per-layer application actually
      differs from the old uniform behavior, not just that the API
      accepts a sequence.
- [ ] A length-mismatched sequence raises `ValueError` with a clear
      message.
- [ ] A campaign candidate whose decoded design requires an operating
      current above `max_current_a` is correctly marked infeasible
      (`G > 0`) with penalty objectives, not silently accepted or
      silently clipped. Test with a constructed case where the same
      topology decodes to different currents depending on genome values,
      confirming the cap boundary is respected.
- [ ] Existing single-`float` callers of `check_pole_angle_limit`/
      `check_feasibility` (from tasks 0003/0005/0008's existing tests)
      continue to work unmodified — backward compatibility confirmed by
      the existing test suite passing without changes to those tests.
- [ ] `ruff check` clean; `pytest` passes; no files outside declared scope
      modified.

## Notes / open questions

- If per-layer max angle interacts awkwardly with how
  `check_pole_angle_limit` currently iterates turns (it uses
  `_iter_indexed_turns` giving a `layer_index` per turn already — this
  should make per-layer lookup straightforward), flag any surprises in
  your summary.
