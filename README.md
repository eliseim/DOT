# DOT - Dipole Optimization Tool

DOT 1.1.1 designs two-dimensional, coil-only cosine-theta superconducting dipole cross-sections from
electromagnetic targets, cable data, and manufacturing constraints. It does not use a reference
magnet layout.

DOT does not model iron, coil ends, stress, protection, magnetization, or three-dimensional
effects.

## Install and start

Requirements: 64-bit Python 3.11, 3.12, or 3.13 with Tcl/Tk, and an internet connection for the
first installation.

On Windows, double-click [`launch_dot_gui.cmd`](launch_dot_gui.cmd). Before creating its private
`.venv`, the launcher lists the packages it will install and asks for approval.

Manual installation:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[acceleration]"
dot gui
```

## Start from a template

In the GUI, select Load Configuration and open one of the following templates:

campaign/7T_NbTi_template.json
campaign/11T_Nb3Sn_template.json

Both templates use campaign/dot_cables.cadata, contain no reference block coordinates, and have successfully produced certified layouts. To design a new magnet, modify the targets, conductor assignments, number of layers, and design bounds.

Each layer requires a .cadata file and a supported conductor selected from that file. DOT currently supports two critical-current-density models:

Nb-Ti: Bottura fit
Nb3Sn: HFM fit

The provided .cadata file includes the LHC MB and MQXF cables. Additional conductors can be added by editing the .cadata file.

## Start a new project

Enter a name for the campaign and select an output folder.

Next, specify the main design requirements:

Desired bore field
Aperture radius
Maximum harmonic order
Number of layers
Operating temperature

For each layer, select a .cadata file. A default cable database is available in the campaign folder. You can then define the minimum and maximum number of blocks per layer, as well as the minimum and maximum number of turns per block.

The block clearance parameter defines the minimum separation between adjacent blocks and helps prevent overlaps.

Specify the minimum distance between the y-axis and the closest cable in the first layer. When Enforce Layer Nesting is enabled, DOT automatically constructs the cross-section so that each subsequent layer remains below the previous layer.

Finally, specify the harmonic targets and the minimum required load-line margin.

Press Refresh Current Advice to obtain DOT's recommendation for the maximum operating current.

After defining the design requirements, select the desired search effort. Larger population sizes and a greater number of generations increase the probability of finding a high-quality layout, but also increase the required computation time.

## How DOT works

DOT exploits the NSGA2 optimization algorithm.

The genome contains:

- continuous `phi` and `alpha` angles for non-midplane blocks;
- integer turns per block;
- active/inactive variables for optional blocks.

`phi = 0°` is the midplane and `phi = 90°` is the pole. Layer 1 starts at the aperture; each
outer layer starts after the requested radial gap. The azimuthal gap fixes each first-block
`phi`, its `alpha` is zero, and DOT optimizes its turn count.

For every generation DOT:

1. creates candidates by sampling, crossover, and mutation;
2. repairs block ordering, active-block continuity, turn budgets, layer radii, and nesting;
3. constructs every insulated turn polygon and rejects collisions or insufficient clearances;
4. solves the series current for the requested bore field;
5. calculates harmonics, peak field, short-sample current, and load-line margin;
6. minimizes the worst requested harmonic residual and maximizes the minimum margin with
   constrained NSGA-II;
7. preserves a spread of non-dominated solutions and distinct active-block topologies.

The enforced geometry includes aperture and midplane clearance, turn non-intersection,
layer separation, per-layer inter-block clearance, the Layer-1 pole-turn distance, and
two-edge layer nesting.

Radial preference and parallel evaluation are enabled by default. Once a target-met layout is
found, DOT retains target-met radial elites even if they are electromagnetically dominated.
Later trials gradually adjust `phi` and `alpha` without changing turns or topology. Every trial
must pass the same geometry checks.

After the last generation, DOT recalculates retained candidates with the final numerical
settings. A candidate is certified only if it satisfies the declared harmonic, margin, current,
turn, and geometry limits. Final selection compares radial alignment only after all targets are
met.

## Read the result

Each campaign creates a timestamped result folder containing:

- `best_candidate_summary.png`: cross-section, electromagnetic results, and block table;
- `best_candidate.json`: complete certified result;
- `best_candidate_geometry.csv`: per-block `R`, turns, `phi`, and `alpha`;
- `final_pareto_frontier.png`: harmonic residual versus minimum margin, colored by turns;
- `best_topology_designs/`: certified alternatives with different block counts;
- `campaign.json`, `run_manifest.json`, and `inputs/`: reproducibility data.

If no candidate certifies, inspect `pareto_candidates.json` before increasing the search size.
Geometry or current failures require a different design space; small harmonic or margin misses
may require more population, generations, or blocks.

## Validation and development

The included 1,000-case comparison covers 500 two-layer and 500 four-layer air-core layouts.
Maximum deviations were 0.099% for bore field, 2.115% for peak field, and 0.604 percentage
points for load-line margin. Harmonic statistics and raw data are in
[`docs/validation`](docs/validation).

```powershell
python -m pytest -q
python -m ruff check .
python -m build
```

DOT is released under the [MIT License](LICENSE). Author: Mattia Elisei, INFN Milan and
University of Rome La Sapienza.
