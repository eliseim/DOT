# Changelog

## 0.1.1 — 2026-07-19

- Renamed the desktop application to **DOT - Dipole Optimization Tool**.
- Moved Load/Save Configuration into a fixed toolbar above the main workspace.
- Replaced solver-branded GUI, summary-image, geometry-CSV, and generated-JSON labels with neutral
  DOT terminology while preserving legacy configuration compatibility and validation tests.
- Renamed designer-facing block exports to `*_geometry.csv` and made continuous block numbering
  explicit through neutral `block` / `block_in_layer` fields.

## 0.1.0 — 2026-07-18

- Added linked, typed ROXIE cadata conductor/cable/insulation/REMFIT resolution.
- Corrected harmonic units, explicit reference radius, allowed harmonics through `b11`, and
  per-turn keystone frames.
- Added engineering-tolerance geometry constraints, layer spacing/nesting, pole/inter-block gaps,
  and exact polygon repair.
- Added normalized named constraints, Pareto-search mode, deterministic multi-seed merge, immutable
  high-fidelity certification and near-feasible diagnostics.
- Added a versioned headless campaign schema and `dot validate` / `dot optimize` CLI.
- Added the blind LHC MB no-iron benchmark and certified regression result.
- Added live GUI/CLI generation progress, elapsed time and ETA, target-balanced best-candidate
  tracking, cooperative cancellation, and persistent generation snapshots.
- Added final cross-section PNG, complete electromagnetic JSON, Pareto archive, and a CSV block
  table carrying both DOT and ROXIE angle conventions.
- Removed the experimental post-NSGA-II refinement stage; publication results now come directly
  from the certified NSGA-II Pareto archive.
- Removed the meaningless Layer-1 radial-gap input. Layer 1 is anchored exactly at the aperture;
  only the N-1 physical gaps between layers are user inputs.
