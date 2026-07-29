# DOT - Dipole Optimization Tool

Current release: **DOT 1.0.0**.

DOT synthesizes two-dimensional, coil-only superconducting dipole cross-sections. It combines
cable geometry, Biot-Savart fields, multipoles, critical-current/load-line calculations,
manufacturability checks, and one constrained NSGA-II Pareto search.

DOT is a pre-design tool. It does not model iron, coil ends, stress, quench protection,
magnetization, or three-dimensional effects.

## Start here

On Windows, double-click [`launch_dot_gui.cmd`](launch_dot_gui.cmd). The first launch:

1. checks for 64-bit Python 3.11, 3.12, or 3.13 with Tcl/Tk;
2. lists every package that will be installed;
3. asks for approval;
4. creates a private `.venv`; and
5. opens the GUI.

For a command-line or developer installation:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[acceleration,dev]"
dot gui
```

The concise [DOT user guide](docs/USER_GUIDE.md) explains the inputs, optimization loop,
constraints, progress display, certification, and output files. The detailed
[technical manual](docs/manual/DOT_TECHNICAL_AND_USER_MANUAL.md) documents the physics and
geometry conventions.

The printable [DOT concise guide](DOT_CONCISE_GUIDE.pdf) combines the workflow, operating
instructions, and 1,000-case physics comparison in one document.

## What the optimizer does

Every generation follows the same loop:

1. create or breed candidate block layouts;
2. repair their discrete winding structure and packing;
3. reject layouts that violate geometric, turn-budget, or powering constraints;
4. compute the current needed for the requested bore field, harmonics, and load-line margins;
5. rank candidates by two objectives: lower worst harmonic residual and higher minimum margin;
6. preserve non-dominated candidates, objective-space diversity, and distinct block topologies.

After the final generation, DOT independently recalculates the non-dominated search archive
with fixed final numerical settings. A candidate is certified only if it then meets every requested
harmonic, margin, current, turn, and geometry limit. Electromagnetically equivalent candidates
are tie-broken in favor of fewer turns and then fewer blocks.

There is no hidden weighted sum, local-refinement stage, annealed target mode, or reference-magnet
layout in the optimization loop.

## Included campaign and qualification data

[`campaign/dot_cables.cadata`](campaign/dot_cables.cadata) is the validated example conductor
catalogue. [`campaign/7T_NbTi_noiron_sample.json`](campaign/7T_NbTi_noiron_sample.json) is a
ready-to-run two-layer input containing electromagnetic targets and manufacturability limits,
but no reference block layout.

The [1,000-case DOT–ROXIE parity study](docs/validation/README.md) compares 500 two-layer and
500 four-layer layouts. Its raw table and machine-readable summary are included. Across the
study, the maximum bore-field deviation was 0.099%, the maximum peak-field deviation was 2.115%,
and the maximum load-line-margin deviation was 0.604 percentage points. See the study for
harmonic statistics and interpretation.

Validate or smoke-test a headless campaign with:

```powershell
dot validate campaign/7T_NbTi_noiron_sample.json
dot optimize campaign/7T_NbTi_noiron_sample.json --quick --output results/smoke
```

`--quick` verifies the pipeline; it is not a convergence campaign.

## Development checks

```powershell
python -m pytest -q
python -m ruff check .
python -m build
```

DOT is released under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) before contributing or reporting a vulnerability.
