# Changelog

## 1.1.0 - 2026-07-29

- Added an optional radial-block preference for winding-friendly layouts.
- Added a persistent, bounded archive for target-met radial elites. Electromagnetic
  dominance does not remove a retained elite, and the normal electromagnetic Pareto front
  remains separate.
- Once the archive has been available for three reproduction cycles, 5% of offspring become
  gradual radial trials seeded from its elites. Each trial adapts one free block's `phi` and
  `alpha`, preserves turns/topology, and must improve radial RMS after the complete geometry
  repair and feasibility checks.
- Final selection first requires every electromagnetic and geometric target, then compares
  radial alignment before surplus harmonic or margin improvement.
- Added central-cable radial-alignment measurements to candidate JSON files, summary
  images, shortlist manifests, and the final GUI result.
- Preserved the complete audited 1.0.0 release as local tag `v1.0.0`.

## 1.0.0 - 2026-07-29

- Promoted the independently audited codebase to the first stable release.
- Consolidated optimization into one constrained NSGA-II Pareto loop.
- Removed the unused annealed-admission subsystem and all public quality switches.
- Made topology preservation and feasibility-aware offspring regeneration standard.
- Required supported critical-current data for every layer.
- Added exact evaluation reuse, JIT kernels, optional process evaluation, and dense live
  diagnostics without changing the certified physics path.
- Added current ranges/fixed current, signed harmonic targets, layer-specific clearances,
  conservative two-edge nesting, gap-derived first-block anchors, and topology-diverse outputs.
- Added the concise user guide and refreshed the detailed technical manual.
- Added a ready-to-run campaign, a validated conductor catalogue, and a reproducible
  1,000-case DOT-ROXIE no-iron physics parity dataset.
- Removed the redundant launcher alias and superseded benchmark fixture tree.
- Removed historical task scaffolding, duplicate result artifacts, build products, and local
  campaign/reference data from the publication tree.

## 0.1.1 - 2026-07-19

- Renamed the desktop application to **DOT - Dipole Optimization Tool**.
- Moved Load/Save Configuration into the upper toolbar.
- Replaced solver-branded designer-facing labels with neutral DOT terminology.
- Made continuous block numbering explicit in result exports.

## 0.1.0 - 2026-07-18

- Added typed `.cadata` conductor, cable, insulation, and critical-current resolution.
- Added 2D coil-only fields, multipoles, load-line margins, geometric constraints, mixed-variable
  NSGA-II, independent final verification, GUI/CLI progress, and blind benchmark inputs.
- Documented `worst_harmonic_units` as the intentional backward-compatible alias of
  `worst_harmonic_residual_units` in serialized campaign results.
