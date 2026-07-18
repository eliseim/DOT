# Contributing

Contributions should preserve DOT's declared 2D, coil-only model boundary and distinguish search
approximations from certification physics.

1. Create a focused branch and add tests for every physics or geometry change.
2. State units and coordinate conventions in public APIs and serialized fields.
3. Do not weaken engineering constraints to make a benchmark pass.
4. Add a convergence or parity case when changing source discretization, critical surfaces,
   harmonic normalization, load-line logic, or repair operators.
5. Run `python -m pytest -q` and `python -m ruff check src tests` before opening a pull request.

Proprietary ROXIE inputs must not be committed. Minimal redistributable fixtures should contain
only the conductor records required to reproduce a public benchmark and must record provenance.
