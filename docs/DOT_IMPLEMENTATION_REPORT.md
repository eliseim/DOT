# DOT 0.1 implementation and validation report

**Date:** 18 July 2026
**Model boundary:** two-dimensional, air-core/coil-only superconducting dipoles

## Outcome

The P0 correctness defects identified in the technical review have been implemented and covered by
tests. DOT now has one authoritative cadata model, physically explicit geometry and harmonic
conventions, a reproducible headless workflow, honest Pareto/certification separation, and a blind
LHC-style synthesis result that passes fixed high-fidelity certification.

DOT remains a pre-design tool. “Certified” means certified against the declared 2D no-iron model,
not approved for construction.

## Blind LHC MB-style synthesis

The input imposed 7 T, 25% minimum margin at 1.9 K, a 28 mm aperture radius, a 0.15 mm one-sided
midplane clearance, a 0.5 mm radial layer spacer, and `|b3|` through `|b11|` no greater than five
units. Layer 1 uses YELLONIN and layer 2 uses YELLONOU. The fixed first-block anchors were derived
from aperture, cable dimensions, and the requested midplane/radial gaps; the remaining blocks were
left to DOT.

No published LHC wedge-block position or turn allocation was included. Generic seeds use only
the classical sector-coil neighborhood. The committed geometry is retained as an immutable physics
regression certificate from the development history and is re-certified by the current kernel. The
experimental local-refinement implementation used during that historical search has been removed
from the release; current campaigns return the certified NSGA-II Pareto archive directly.

| Certified quantity | Result |
|---|---:|
| Bore field | 7.000 T |
| Operating current | 10,825.44 A |
| Layer 1 margin | 27.745% |
| Layer 2 margin | 29.493% |
| `b3` | −3.853 units |
| `b5` | −4.965 units |
| `b7` | −4.005 units |
| `b9` | +0.894 units |
| `b11` | +0.123 units |
| Layer 1 pole-turn closest distance | 5.107 mm |

The generated geometry differs from the published LHC layout and therefore demonstrates target
synthesis rather than layout fitting. The exact regression certificate is
[`benchmarks/lhc_mb_no_iron/certified_blind_result.json`](../benchmarks/lhc_mb_no_iron/certified_blind_result.json).

## Implemented corrections

### Electromagnetics and conductor data

- Harmonics are carried and compared once in CERN/European units (`10⁻⁴` of the main field).
- `aperture_radius_mm` and `reference_radius_mm` are independent campaign fields.
- Normal allowed harmonics are explicit and default through `b11` in the designer workflow.
- Search and certification source discretizations are named, immutable fidelity objects.
- Per-turn keystone frames are preserved when insulated turns are converted to bare conductor for
  peak-field evaluation.
- Cadata selection follows `CONDUCTOR → CABLE/STRAND → FILAMENT → REMFIT` and insulation links.
  Unsupported fits are preserved and reported rather than corrupting a mixed catalog.
- Current advice uses only the Layer-1 fit. ROXIE `cu/sc` is treated as Cu/non-Cu, separately from
  the type-11 fit exponent also named alpha, and the fitted non-copper `Jc` is converted with
  `N*pi*d^2/[4*(1+Cu/nonCu)]` plus the cadata cable-degradation factor.
- Actual operating current remains correct when an already-scaled candidate is certified again.

### Geometry

- Midplane, pole, aperture, inter-block, inter-layer, collision, pole-turn-radius, and nesting rules have
  named violations and engineering tolerances.
- Physical azimuthal gaps and the N-1 inter-layer radial gaps are user inputs. Layer 1 has no radial
  gap because its R is exactly the aperture radius. DOT derives each immutable first-block
  R/phi anchor from the aperture, preceding insulated cable envelope, and requested gaps; alpha is
  zero. DOT chooses that block's turns and every degree of freedom of subsequent optional blocks.
- The former maximum pole-angle input has been replaced by an exact Layer-1 closest-point distance
  to the pole axis. In the straight-block model this is explicitly reported as a bend-radius proxy.
- Inter-block clearance is an exact insulated-polygon closest-point calculation. It can be set
  independently per layer, is used by both feasibility and geometry repair, and is serialized for
  every block pair in live-generation and final candidate results.
- Radial layer spacing follows the nominal mandrel/cable/spacer definition used by ROXIE layouts.
- Nesting checks both the conventional prolonged pole-side edge and the conservative prolonged
  lower side of the inner layer's pole turn.
- The exact CTH table is feasible at its documented aperture/gaps without turn deletion.
- Optional block slots share the full physical azimuth range; slot identity no longer confines a
  two-block winding to an artificial quarter-window.
- Repairs use the true poleward turn-stacking direction, midward block footprint, physical
  midplane anchor, contiguous active topology, and coupled nesting/collision checks.

### Optimization integrity

- Geometry and turn budgets are hard search constraints with dimensionless named violations.
- Performance can use annealed constraints or Pareto-search/strict-certification mode. The latter
  preserves high-margin and low-harmonic branches until they can recombine.
- Every geometrically valid individual receives both real harmonic and margin objectives;
  unevaluated margins are never represented as satisfied.
- Final candidates are re-evaluated at fixed certification fidelity, deduplicated, filtered, and
  nondominated again. Near-feasible designs form a separate diagnostic archive.
- Initialization and offspring use the same repair pipeline. Generic sector seeds contain no
  reference-layout knowledge.
- Electromagnetically equivalent designs are ordered by total turns and then active blocks; complexity
  remains a secondary tie-breaker rather than a third Pareto objective.

## Reproducible workflow

```powershell
dot validate benchmarks/lhc_mb_no_iron/blind_target.json
dot optimize benchmarks/lhc_mb_no_iron/blind_target.json --output results/lhc
dot gui
```

Installed users may also run `dot-gui`; Windows source-tree users can double-click
`launch_dot_gui.cmd` after the one-time environment setup.

The result records the campaign path, reference radius, harmonic convention, fidelity names,
certified candidates, individual harmonics, layer and ROXIE-numbered block load-line records, and
near-feasible violations.
Multiple deterministic seeds are re-certified and merged into one nondominated archive.

Final export includes a designer shortlist of up to 10 alternatives. Active block counts per layer
define the topology family; one target-ranked representative per family is emitted before any family
is repeated. Each entry has an independent cross-section PNG, full electromagnetic/geometry JSON,
and ROXIE-ready block CSV. Search-front shortlists are allowed only when explicitly marked uncertified.

The interactive `dot-gui` workflow reports a real progress bar, elapsed time, moving-window ETA,
best target-balanced candidate, live turn-by-turn cross-section, geometry table, and convergence
history after every generation. Each generation is archived as PNG plus JSON. At completion the
selected certified Pareto representative is written as a high-resolution cross-section, complete
electromagnetic JSON, Pareto archive, and CSV block table. The CSV carries `R`, turns, conductor,
current, and native ROXIE/CTH `phi/alpha`: `phi=0` at the midplane and increases toward the pole;
`alpha` is the absolute ROXIE cable-frame angle. Live and final result tables also show the
measured closest-point clearance for each same-layer block pair and the Layer-1 pole-turn distance.
The current-advice helper uses the Layer-1 critical fit and requested margin with `Bpeak=Bbore` to
report a non-binding upper current estimate. Search effort is available as three named presets or
custom population/generation values. The complete final search Pareto frontier remains harmonic
versus margin colored by total turns even when no point passes immutable certification.

Blind campaign definitions are also included for CTH-14T and FalconD. Their cadata files preserve
the exact linked conductor chains and their target files exclude every published block angle and
turn allocation. These campaigns are runnable qualification targets; unlike the LHC case, they are
not yet accompanied by committed multi-seed convergence certificates.

The `dot.analysis` API provides seeded Gaussian tolerance Monte Carlo, geometry/specification
yield, harmonic P95/CVaR95, margin P05, and finite-difference block-angle sensitivities. These are
post-processing results and do not silently change nominal Pareto rank.

## Verification completed

- `python -m pytest -q`: 232 passed and 13 optional/live fixtures skipped after removal of the
  untrusted refinement stage.
- Live ROXIE service: 11 passed. Bore-field errors were 0.065-0.481% for the single/multi-turn
  angle cases and 0.235% for CTH-14T; peak-field errors were 0.064-1.182% and load-line-margin
  errors were 0.017-0.334 percentage points across Nb3Sn, NbTi, and mixed-layer cases.
- `python -m ruff check src tests`: passed.
- `git diff --check`: passed.
- `dot validate`: passed for LHC MB, CTH-14T, and FalconD blind campaigns.
- `dot optimize ... --quick`: completed end to end and wrote an honest diagnostic archive; the
  quick mode is intentionally too small to claim convergence.

## Guidelines for a new magnet

1. Put each permitted layer conductor in a redistributable cadata file and select the exact
   `CONDUCTOR` name. Never enter unrelated strand/cable/fit rows independently.
2. Declare physical aperture and harmonic reference radii separately.
3. Enter physical azimuthal gaps and inter-layer radial gaps; verify the derived R/phi anchors in
   the output table, then give DOT a realistic maximum block count and turn bounds.
4. Set a Layer-1 pole-turn radius proxy consistent with cable windability, and independent
   per-layer inter-block clearances consistent with insulation/wedge needs.
5. Start with Pareto search for a new topology. Use annealed constraints only after demonstrating a
   feasible basin.
6. Keep global search inexpensive, but use the fixed, converged certification fidelity for pass/fail.
7. Run several deterministic seeds. One stochastic success is evidence, not convergence proof.
8. Independently compare selected candidates with ROXIE before engineering use.

## Remaining work before engineering sign-off

- signed minimum-slack and robustness-summary serialization in the CLI result archive;
- force, stored-energy, inductance, and conductor-cost metrics;
- first-class wedge polygons and CAD/SVG export;
- blind convergence certificates for CTH-14T and FalconD in addition to physics parity cases;
- critical-surface strain and uncertainty propagation, especially for Nb3Sn;
- independent review of the certification source model against more ROXIE cross-sections;
- iron, ends, mechanics, and quench interfaces, which are outside the 0.1 model boundary.

The repository is prepared for release under the MIT License, copyright 2026 Mattia Elisei,
INFN Milan and University of Rome La Sapienza.
