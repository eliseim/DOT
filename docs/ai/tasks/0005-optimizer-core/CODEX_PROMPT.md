# Codex worker prompt — TASK 0005-optimizer-core

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0005-optimizer-core/TASK.md` in this worktree fully before
writing any code. This task integrates every previously-merged module
(`src/dot/geometry`, `src/dot/physics`, `src/dot/conductors`) — read those
modules' actual public APIs first (do not assume signatures from the task
prose; check the real code) before designing the genome/decoder.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md. `pyproject.toml` may
   only gain a `pymoo` optional dependency group — nothing else.
2. Topology (layer/block count, cable per layer) is fixed input, not part
   of the genome. Do not add topology search — explicitly out of scope.
3. Use the exact-linear-current-scaling approach described in TASK.md for
   hitting the target bore field — do not implement a multi-point/
   iterative field solve, it is unnecessary for no-iron physics and is
   explicitly forbidden as overengineering here.
4. Feasibility (task 0003's `check_feasibility`) gates every candidate via
   pymoo's constraint mechanism (`G`) — do not let an infeasible design
   receive a "good" objective score.
5. You may read the reference files listed in TASK.md for the general
   shape of genome->decode->constraints->objectives->Problem wiring only.
   Do not copy code.
6. No ROXIE dependency. No GUI, no CLI beyond what tests need.
7. Write the tests specified in TASK.md's acceptance criteria, run `pytest`
   and `ruff check` yourself, report actual output. Keep the end-to-end
   `run_campaign` test's population/generations small so the suite stays
   fast (seconds, not minutes).
8. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact genome
encoding chosen (which variables, integer vs continuous, bounds), how
`operating_point` computes the current-scaling factor and why it's exact
for no-iron physics, how the margin proxy is computed (which turn/location
is treated as the field-limiting one and why), how infeasibility is
translated into pymoo's `G`, and full test output.

## Task-specific instructions

Before writing code, actually read (do not guess):
- `src/dot/geometry/primitives.py` (`TurnPolygon`, `Block`, `Layer`,
  `DipoleDesign` — note blocks within a layer share one nominal inner
  radius; turns within a block stack radially outward)
- `src/dot/geometry/constraints.py` (`check_feasibility`,
  `FeasibilityResult`, `Violation`)
- `src/dot/geometry/cable.py` (`CableSpec`)
- `src/dot/physics/sources.py`, `field.py`, `multipoles.py`
- `src/dot/conductors/cadata.py`, `critical_surface.py`,
  `critical_current.py`, `loadline.py`

Then implement, in this order:

1. `pyproject.toml`: add `[project.optional-dependencies] optimization = ["pymoo>=0.6"]` (or `[dependency-groups]` equivalent, matching whatever style task 0001 used for `dev`).
2. `src/dot/optimize/genome.py`: a `Topology` description (per-layer: cable, n_blocks) and functions `encode(design_params) -> genome_array` / `decode(genome_array, topology, cable_map) -> DipoleDesign` for the fixed-topology case: genome variables are, per layer, one continuous inner-radius value, and per block, one continuous `phi_deg` and one integer `n_turns` (alpha_deg fixed at 0 for this task — document this as an intentional simplification). `current_a` in the decoded `DipoleDesign`'s blocks should be a placeholder (e.g. 1.0 A); the real operating current is applied by `operating_point.py`, not baked into the genome.
3. `src/dot/optimize/operating_point.py`: a function that takes a
   unit-current `DipoleDesign`, a target bore field (T), computes
   `field_at(design's sources at bore center)` at unit current, and
   returns the scale factor / scaled current needed to hit the target
   field, plus a helper to produce a new `DipoleDesign` with all currents
   scaled accordingly.
4. `src/dot/optimize/objectives.py`: `field_quality_objective(design, r_ref_mm, max_order) -> float` (max |b_n|/|a_n| for n>=2) and `load_line_margin_objective(design, cable_specs_by_layer, cadata_by_layer, temperature_k) -> float` (percent, using the peak-field-on-own-turns proxy described in TASK.md, via task 0004's `loadline.py`).
5. `src/dot/optimize/problem.py`: a `pymoo.core.problem.Problem` subclass wiring genome -> `decode` -> `check_feasibility` (infeasible -> constraint violated, large objective penalty, skip further evaluation) -> `operating_point` scaling -> `objectives.py` -> `(F, G)`.
6. `src/dot/optimize/runner.py`: `run_campaign(topology, targets, pop_size=8, n_gen=3, seed=None) -> ParetoResult` using `pymoo.algorithms.moo.nsga2.NSGA2` and `pymoo.optimize.minimize`, returning feasible Pareto candidates with their decoded designs and objective values.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (all new tests + all previously merged tests must still pass)
