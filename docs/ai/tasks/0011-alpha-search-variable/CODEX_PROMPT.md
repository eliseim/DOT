# Codex worker prompt — TASK 0011-alpha-search-variable

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0011-alpha-search-variable/TASK.md` in this worktree fully
before writing any code. This changes the genome encoding shape — read
`src/dot/optimize/genome.py`'s current `encode`/`decode`/`genome_bounds`
fully first (do not guess), since every downstream user of the genome
array depends on getting the indexing exactly right.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md.
2. Block index 0 in each layer NEVER gets a genome slot for alpha — it is
   always exactly `0.0`, hardcoded, not searched. Blocks at index 1+ each
   get 3 genome slots (phi, n_turns, alpha) instead of 2.
3. `encode`, `decode`, and `genome_bounds` must all agree on the exact same
   variable-width layout — a mismatch between any two of them would
   silently corrupt every campaign. Write the round-trip test yourself and
   actually run it, don't just reason about it.
4. Update existing tests that hardcode the old fixed `n_var` formula
   (`1 + 2*n_blocks` per layer) to the new formula — this is expected and
   required, not something to work around.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact new
genome layout (with a worked example for a 2-layer topology showing which
index holds what), confirmation the round-trip test passes, and full test
output.

## Task-specific instructions

Follow TASK.md's "Goal", "Scope", and acceptance criteria precisely. Add
`alpha_bounds_deg: tuple[float, float]` to `LayerTopology` (validate
ordering like the existing bounds fields do — reuse
`_require_ordered_float_bounds` if applicable). Update `Topology.n_var`,
`encode`, `decode`, `genome_bounds` together, consistently.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite)
