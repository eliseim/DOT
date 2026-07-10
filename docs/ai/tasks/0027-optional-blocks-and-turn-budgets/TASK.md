# TASK: Optional (searchable-count) blocks per layer + turn-count budgets

- **ID**: 0027-optional-blocks-and-turn-budgets
- **Status**: draft
- **Model/effort**: Highest effort. This is a real genome/architecture
  change, not a parameter tweak — `LayerTopology.n_blocks` changes meaning
  from "exact block count" to "maximum block count," and a new kind of
  gene (block active/inactive) is introduced. Touches
  `src/dot/optimize/genome.py`, `problem.py`, `runner.py`. No live-ROXIE
  requirement (optimizer/genome behavior, not physics) — validation is
  unit tests plus empirical campaign behavior, same as tasks 0022/0023/0025.

## Background

`dipole_designer` supports specifying a *maximum* number of blocks per
layer (the search decides how many are actually used, from 0/1 up to that
max) and turn-count *budgets* (a ceiling the search allocates freely
under, not a fixed per-block range) — the user wants this replicated in
DOT, having confirmed DOT should match this capability rather than only
supporting fixed block counts with independent per-block ranges.

DOT's current genome (`src/dot/optimize/genome.py`) hard-encodes an exact
`n_blocks` per layer — every layer decodes to precisely that many
`Block`s, always active, with block 0's `alpha_deg` fixed at 0 (the
midplane-block convention) and blocks 1..n_blocks-1 getting their own
continuous `alpha_deg` gene. There's no way to search "how many blocks"
or to cap total/per-layer turn count as a budget — only fixed per-block
`n_turns_bounds` ranges.

A comparative note from earlier work in this project (survey of
`dipole_designer`'s optimizer,
`C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\target_synthesis_genome.py`/
`topology_genome.py`): `dipole_designer` implements this via boolean
"active block" genes gating whether a block-slot's other genes are used
when decoding. That pattern is the reference for this task (read for the
*concept*, DOT's genome is much simpler — do not port
`dipole_designer`'s repair/regeneration machinery, topology-family
survival niching, or other complexity explicitly ruled out in earlier
tasks 0022/0023 — this task is scoped narrowly to optional blocks and
turn budgets, nothing else).

## Goal

1. **Reinterpret `LayerTopology.n_blocks` as a maximum.** For each layer,
   block slot 0 is always active (anchors the midplane `alpha_deg=0`
   convention, unchanged). Block slots 1..n_blocks-1 each get a new
   **active** gene (boolean-valued — use pymoo's `Binary` variable type if
   available in the installed pymoo version, or an `Integer(bounds=(0,1))`
   if not — check what's idiomatic, consistent with how task 0022 already
   uses `Integer` for `n_turns`). When a block slot's active gene is 0
   (inactive), that block does not appear in the decoded `DipoleDesign` at
   all — its other genes (phi, n_turns, alpha) still exist in the genome
   (fixed-length genome, standard practice for this kind of optional-gene
   encoding) but are ignored during decode.
2. **Decode must handle variable active-block counts correctly.**
   `decode()` should build each `Layer` from only the active blocks
   (block 0 always included, plus whichever of blocks 1..n_blocks-1 have
   active=1), preserving their relative phi ordering. A layer must always
   have at least one block (block 0), so `n_blocks=1` layers are
   unaffected by this change (no active gene needed when there's only one
   possible block — don't add a meaningless always-active gene for
   `n_blocks=1` layers).
3. **Add turn-count budget constraints to `OptimizationTargets` /
   `DipoleOptimizationProblem`.** Add `max_total_turns: int | None` (sum
   of `n_turns` across every active block in the whole design) and
   `max_turns_per_layer: int | None` (sum of `n_turns` across every active
   block within one layer — apply the same per-layer cap to all layers
   for now, a single int, not a per-layer sequence, unless you find a
   strong reason to make it per-layer; keep it simple unless the simple
   version doesn't work). These are graded constraints, in their own `G`
   columns, computed directly from the decoded genome (no `operating_point`
   or physics evaluation needed — this should be checked *before* the
   expensive parts of `_evaluate`, alongside or right after the geometry
   feasibility check, since it's cheap and structural, not a physics
   quantity). Do **not** anneal these — unlike current/harmonic/margin
   (continuous physics quantities where relaxation helps the search find
   a starting foothold), turn-count budgets are a discrete structural
   limit directly controllable by the genome's own bounds; a flat graded
   penalty (severity = amount over budget) is sufficient and simpler.
   Update `n_ieq_constr` accordingly.
4. **Update `genome_bounds`/`genome_variables`/`mixed_variable_spec`/
   `encode`/`flatten_mixed_genome`** to account for the new active genes.
   `encode()` (which converts an existing `DipoleDesign` back into a
   genome, used in tests) needs a sensible convention for designs with
   fewer than `n_blocks` blocks — check its existing callers/tests before
   deciding; document your choice.
5. **Update `runner.py`'s sampling/repair machinery** to handle the new
   active genes: the constructive sampler should sample active/inactive
   sensibly (not always-active, or the "maximum" framing is pointless —
   but also not so sparse that layers frequently collapse to just block
   0), and `PhiOrderingRepair` must only enforce ordering/gaps among
   *active* blocks (inactive blocks' phi values are irrelevant and
   shouldn't be repaired). Task 0022's default constructive sampler has a
   known, separate turn-count-spacing bug (logged, not fixed) — you don't
   need to fix that here, just make sure active/inactive handling doesn't
   make it worse or interact badly with it.

## Scope (files/modules Codex may touch)

- `src/dot/optimize/genome.py`
- `src/dot/optimize/problem.py`
- `src/dot/optimize/runner.py`
- `tests/optimize/test_genome.py`
- `tests/optimize/test_problem.py`
- `tests/optimize/test_runner.py`

## Explicit non-goals

- No topology-family survival niching, no staged refinement, no
  constructive-initializer complexity beyond what's needed for active
  genes — these were explicitly ruled out for DOT in tasks 0022/0023 and
  that decision stands; this task only adds *optional block count* and
  *turn budgets*, not the rest of `dipole_designer`'s topology-search
  machinery.
- No change to the physics/geometry/margin code
  (`src/dot/geometry/*`, `src/dot/physics/*`,
  `src/dot/optimize/objectives.py`).
- No change to the current-cap/harmonic/margin annealing logic itself
  (tasks 0023/0025, already correct) — only add the new, separate,
  non-annealed turn-budget constraints alongside them.
- Do not weaken any existing test's tolerance to force a pass.
- Backward compatibility: existing `Topology`/`LayerTopology` usages that
  don't need optional blocks (e.g. `n_blocks=1`, or campaigns that don't
  set `max_total_turns`/`max_turns_per_layer`) must behave exactly as
  before — this is an additive feature, not a breaking change to the
  existing fixed-block-count behavior when the new fields aren't used.

## Acceptance criteria

- [ ] A `LayerTopology` with `n_blocks=4` correctly decodes designs with
      1, 2, 3, or 4 active blocks depending on the active genes, verified
      by a direct unit test (construct a genome by hand with specific
      active values, decode it, assert the resulting `Layer.blocks` count
      and content).
- [ ] `n_blocks=1` layers are unaffected (no active gene added, decode
      behavior identical to before this task).
- [ ] `max_total_turns` and `max_turns_per_layer` produce graded (not
      flat) `G` constraint values, verified with a unit test showing two
      different over-budget designs get distinguishable values.
- [ ] Designs within budget get real objective values computed (not
      skipped) — verify with a test.
- [ ] Existing tests in `test_genome.py`/`test_problem.py`/`test_runner.py`
      that use fixed `n_blocks` without the new budget fields continue to
      pass unmodified (backward compatibility).
- [ ] `ruff check` clean; `pytest -q` passes with zero failures.
- [ ] Report a brief empirical check: run a small campaign with
      `n_blocks=4` (max), `max_turns_per_layer=30`, `max_total_turns=100`
      and confirm the final population contains designs using a genuinely
      *varying* number of active blocks per layer (not always exactly 4,
      not always exactly 1) — this confirms the search is actually
      exploring the block-count dimension, not just technically allowing
      it.
- [ ] No files outside declared scope modified.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\target_synthesis_genome.py`
  and `topology_genome.py` — the active-block-gene concept (read for
  understanding only; DOT's genome is much simpler, don't port the
  broader machinery).
- `src/dot/optimize/genome.py`, `problem.py`, `runner.py` — read fully
  before changing anything; this is the third time `problem.py` has been
  touched (after tasks 0023, 0025) and the second time `runner.py` has
  (after task 0022) — match existing conventions exactly.
