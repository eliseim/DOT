# TASK: NSGA-II optimizer core (topology-fixed turn/angle search)

- **ID**: 0005-optimizer-core
- **Status**: draft
- **Model/effort**: High effort for both Codex and Antigravity — this task
  wires together every previously-verified module (geometry, physics,
  constraints, load-line) into the actual search loop; an integration bug
  here (e.g. wrong current scaling, constraints not actually enforced)
  silently invalidates everything built so far even if each module is
  individually correct.
- **Worktree**: .worktrees/0005-optimizer-core (branch task/0005-optimizer-core)

## Goal

Given a **fixed coil topology** (number of layers, number of blocks per
layer, cable per layer — user-provided, not searched) and design targets
(target bore field in T, a maximum allowed |harmonic| in units of 1e-4, a
minimum required load-line margin in %, operating temperature), search over
each block's azimuthal position (`phi_deg`) and turn count (`n_turns`), and
each layer's inner radius, for the Pareto-optimal set of **feasible**
designs trading off field quality (lower max |harmonic| is better) against
load-line margin (higher margin is better).

**Key simplification enabled by no-iron 2D physics**: because there is no
iron, the field is *exactly linear* in current (superposition, no
saturation). So for any candidate geometry, the operating current that
hits the target bore field is not searched — it is computed in one shot:
evaluate the field at the bore center for the geometry at 1 A per turn,
then scale current by `target_field_T / field_at_1A_T`. This is exact, not
an approximation, and removes an entire objective/search dimension that
the ROXIE-based reference tool needed multiple simulation calls to
resolve (because iron saturation made it nonlinear there).

Two remaining objectives, minimized:
1. **Field quality**: `max(|b_n|, |a_n|)` over harmonics 2..N (dipole term
   itself, n=1, is excluded — it's fixed by construction via the current
   scaling above).
2. **Negative load-line margin**: `-margin_percent` (so minimizing this
   maximizes margin), computed at the scaled operating current using task
   0004's solver, for the layer/block combination(s) actually carrying
   current at the field-limiting location. Keep this proxy simple: compute
   margin using the **peak field magnitude found anywhere on the coil's own
   turns** (a direct, honest overestimate-of-risk proxy — do not attempt
   the full per-conductor multi-point analysis the ROXIE-based tool used;
   that is deliberately out of scope here).

Constraint (feasibility gate, not an objective): task 0003's
`check_feasibility` must pass. Infeasible candidates get a large penalty in
both objectives (pymoo constraint `G`) rather than being evaluated further.

## Scope (files/modules Codex may touch)

- `pyproject.toml` — add `pymoo` under a new `[project.optional-dependencies.optimization]` group. Do not add anything else (no PySide6/matplotlib/shapely — GUI is a later task).
- `src/dot/optimize/__init__.py`
- `src/dot/optimize/genome.py` — genome <-> `DipoleDesign` encode/decode for
  the fixed-topology case described above.
- `src/dot/optimize/operating_point.py` — the linear current-scaling
  function described above.
- `src/dot/optimize/objectives.py` — field-quality and load-line-margin
  objective computation from a decoded `DipoleDesign` + solved current.
- `src/dot/optimize/problem.py` — the pymoo `Problem` subclass wiring
  genome -> decode -> feasibility -> operating point -> objectives.
- `src/dot/optimize/runner.py` — a thin function
  `run_campaign(topology, targets, nsga2_params) -> ParetoResult` that
  constructs the `Problem`, runs `pymoo.optimize.minimize` with NSGA2, and
  returns the Pareto set (feasible candidates + their objective values).
- `tests/optimize/test_genome.py`
- `tests/optimize/test_operating_point.py`
- `tests/optimize/test_objectives.py`
- `tests/optimize/test_problem.py`
- `tests/optimize/test_runner.py`

## Explicit non-goals

- No topology search (number of layers/blocks is fixed input, not part of
  the genome) — keep the search space small and the task scope bounded.
- No multi-point/multi-conductor load-line analysis — the single
  peak-field proxy described above is the entire scope for margin in this
  task.
- No GUI. No CLI entry point beyond what's needed for tests to call
  `run_campaign` directly.
- No ROXIE code, no ROXIE parity checks (that's a separate, optional,
  non-blocking task already tracked elsewhere).
- Do not add SciPy, shapely, or any dependency beyond `pymoo` in this task.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole_designer\dipole_optimizer\optimization\target_synthesis_problem.py`
  and `objectives.py` — read for the general shape of "genome -> decode ->
  constraints -> objectives -> pymoo Problem" wiring. DOT's version is
  deliberately much simpler (fixed topology, no ROXIE calls, exact linear
  current solve) — do not copy structure or code, the shapes differ
  significantly.
- `C:\Users\elisei\Desktop\dipole-optimization-tool\src\dipole_opt\native_backend\optimization.py`
  — read for one example of wiring a native (non-ROXIE) physics backend
  into a pymoo `Problem`. Do not copy.

## Acceptance criteria

- [ ] Genome encode/decode round-trips: encoding a hand-built valid
      `DipoleDesign` (fixed topology) into a genome and decoding it back
      reproduces the same `phi_deg`/`n_turns`/layer-radius values.
- [ ] `operating_point` current-scaling is tested against a hand-computed
      case: for a simple one-block design, compute the expected scaled
      current independently (using task 0002's `field_at`/`multipoles`
      functions directly in the test at 1 A, then hand-derive the scale
      factor) and confirm it matches.
- [ ] Objectives: a hand-constructed asymmetric design's field-quality
      objective is tested against an independently-computed max-harmonic
      value; the margin objective is tested against task 0004's solver
      called directly in the test with the same inputs the objective
      function would derive.
- [ ] `problem.py`: an infeasible genome (decodes to overlapping turns)
      produces a constraint violation (`G > 0`) and does not crash;
      feasible genomes produce `G <= 0`.
- [ ] `runner.py`: `run_campaign` on a small fixed topology (e.g. 1 layer,
      2 blocks) with a small population/generation count completes and
      returns at least one feasible candidate whose harmonics and margin
      are internally consistent with directly calling `objectives.py` on
      the same decoded design.
- [ ] `ruff check` clean; `pytest` passes (including a fast, small
      end-to-end run of `run_campaign` — keep population/generations tiny
      so the test suite stays fast, e.g. pop=8, gen=3); no existing tests
      broken; no files outside declared scope modified.

## Notes / open questions

- Keep NSGA-II default parameters (population, generations) as function
  arguments with small sensible defaults — do not hardcode large values
  that would make the test suite slow. Performance/speed tuning is
  explicitly a later phase per the user's stated roadmap; this task is
  about correctness of the wiring, not speed.
- If pymoo's mixed integer/continuous variable handling turns out to need
  a specific `Problem` variable-type setup (integer `n_turns`, continuous
  `phi_deg`/radius), document the choice made and why.
