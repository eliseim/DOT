# Codex worker prompt — TASK 0013-per-block-phi-windows

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0013-per-block-phi-windows/TASK.md` in this worktree fully
before writing any code. This fixes a real, empirically-diagnosed
search-space defect (not a hypothetical) — TASK.md's "Background" section
has the coordinator's actual diagnosis data, read it carefully.

## Hard rules

1. Only touch `src/dot/optimize/genome.py`'s `genome_bounds` function and
   `tests/optimize/test_genome.py`.
2. Do not change `encode`/`decode` — a genome value at a block's phi slot
   is still that block's absolute `phi_deg` directly. Only the *bounds*
   `genome_bounds` offers per block change.
3. `n_blocks=1` layers must be unaffected (bounds equal the full
   `phi_bounds_deg`, exactly as today) — this is a hard backward-
   compatibility requirement.
4. Write the empirical test specified in TASK.md's acceptance
   criteria — comparing feasible-fraction under old vs new bounds for a
   multi-block layer — this is the test that actually proves the fix
   matters, not just that the bounds have the right shape.
5. Run `pytest` and `ruff check` yourself, report actual output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope. A summary covering: the exact
partition formula used, confirmation of the `n_blocks=1` no-op case, and
the empirical before/after feasible-fraction numbers from your test.

## Task-specific instructions

In `genome_bounds`, for each layer, compute
`window_width = (phi_bounds_deg[1] - phi_bounds_deg[0]) / n_blocks`, and
for block index `i`, use bounds
`(phi_bounds_deg[0] + i * window_width, phi_bounds_deg[0] + (i+1) * window_width)`
instead of the layer's full `phi_bounds_deg` for every block.

After implementation, run and report:
- `ruff check .`
- `pytest -q` (full suite)
