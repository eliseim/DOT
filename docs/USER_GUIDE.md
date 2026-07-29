# DOT 1.1.0 concise user guide

## 1. Scope

DOT creates feasible 2D, straight-section, coil-only dipole layouts from engineering targets.
It searches the block positions and turn allocation; it does not copy a known magnet layout.

Use DOT for electromagnetic pre-design and trade-off studies. A certified DOT candidate still
needs iron, ends, mechanics, protection, tolerances, and 3D engineering before it can become a
magnet design.

## 2. Launch

On Windows, double-click `launch_dot_gui.cmd`. Python is the only prerequisite. Use 64-bit
Python 3.11, 3.12, or 3.13 and include Tcl/Tk when installing Python. On first launch, DOT shows
the exact dependency list and waits for approval before creating `.venv` and installing it.

From an activated environment, run either command:

```powershell
dot gui
dot-gui
```

## 3. Configure a campaign

Enter a campaign name and output directory, then set:

- target bore field, aperture radius, temperature, and reference radius;
- number of layers;
- one `.cadata` file and one supported conductor for every layer;
- minimum/maximum blocks and turns for every layer;
- azimuthal gap for every layer and radial gap after Layer 1;
- minimum inter-block clearance, Layer-1 pole-turn distance, numerical tolerance, and nesting;
- maximum harmonic residual, minimum margin, and optional current bounds;
- search-effort preset and random seed.
- optional radial-block preference after the electromagnetic targets are reached.

The conductor name must exactly match a `CONDUCTOR` record in its `.cadata` file. The GUI lists
only complete conductors using supported critical-current fits: REMFIT type 1 (Nb-Ti) and type 11
(Nb3Sn).

Layer 1 starts at the aperture radius. DOT computes its first-block angle from
`atan(azimuthal gap / radius)`. Each later layer starts at the outer radial coordinate of the
previous layer's first insulated turn plus the requested radial gap. The first block's
`alpha` is fixed to zero. DOT chooses its turns and all later blocks.

If minimum and maximum current are equal, the current is fixed and the geometry must reproduce
the requested bore field within the documented numerical tolerance. Otherwise DOT scales every
candidate to the target bore field and enforces the current interval.

The Advanced harmonics tab accepts a signed target for each normal harmonic. For example, a
target `b3 = -3` is useful when a separately calculated yoke is expected to add `+3` units.

## 4. The complete optimization loop

DOT uses one constrained, mixed-variable NSGA-II search.

### Candidate representation

The layer count, cables, aperture, bounds, and first-block anchors are fixed campaign inputs.
The genome contains:

- the number of turns in every active block;
- `phi` and `alpha` for non-midplane blocks;
- an active/inactive variable for optional block slots.

`phi = 0` is the midplane and increases toward `90 degrees` at the pole. `alpha` is the absolute
cable-frame angle. Active blocks form a contiguous sequence from midplane to pole.

### One generation

1. **Create candidates.** Generation 1 mixes generic sector-coil seeds with broad random
   samples. Later generations use NSGA-II parent selection, crossover, and mutation.
2. **Repair winding structure.** DOT enforces contiguous/minimum block counts, compacts radial
   placement, applies turn budgets, orders blocks with their real turn footprints, and projects
   adjacent layers toward a nested layout.
3. **Check exact geometry.** DOT builds every insulated turn polygon. Remaining invalid layouts
   are simplified by reducing turns or optional blocks; unrepaired layouts receive a constraint
   violation and cannot outrank feasible ones.
4. **Solve electromagnetics.** DOT finds the series current for the requested bore field (or
   evaluates the fixed current), computes normal/skew multipoles at the reference radius, samples
   peak field on conductor boundaries, and solves each conductor load line.
5. **Assign two objective values.** DOT minimizes the worst requested harmonic residual and
   minimizes the negative minimum layer margin, which is equivalent to maximizing margin.
6. **Select survivors.** Feasible candidates are sorted into non-dominated fronts. Crowding
   distance preserves a spread along the harmonic-margin trade-off. A small family quota prevents
   one active-block topology from eliminating all alternatives too early.
7. **Apply the optional radial preference.** Only after target-met candidates persist for three
   consecutive generations, DOT uses 5% of later offspring as radial trials. It changes only
   the free `alpha` angles, reapplies the complete geometry repair, and retains at most one
   radial exemplar from the best available Pareto rank. Fixed midplane blocks are unchanged.

Geometry, current, and optional turn budgets are hard constraints during every generation.
Harmonic and margin targets remain objectives during the search, so promising trade-offs are not
discarded before they mature.

No objective weights are required. A candidate dominates another only when it is no worse in
both objectives and better in at least one.

### Geometry rules

Every evaluated layout is checked for:

- aperture and midplane clearance;
- turn-to-turn and block-to-block non-intersection;
- the requested closest-point inter-block clearance in each layer;
- the requested radial separation between adjacent layers;
- the Layer-1 pole-turn minimum-distance proxy;
- layer nesting.

Layer nesting is a conservative windability envelope. DOT prolongs the pole-side and lower long
edges of the inner layer's pole-most turn and requires the adjacent outer layer to remain on the
aperture side of both boundary lines.

The numerical tolerance classifies round-off/contact. It is not a physical clearance and should
not replace an engineering gap.

### Final certification

Search calculations use a validated, economical field discretization. After the last generation,
DOT deduplicates the hard-feasible non-dominated archive and independently recalculates each
candidate with fixed final numerical settings. Only candidates meeting every target are certified.

If two layouts are electromagnetically equivalent within tight numerical tolerances, DOT prefers
fewer total turns, then fewer blocks. These are tie-breaks only; they do not override a meaningful
harmonic or margin improvement.

## 5. Follow progress

Press **Start Campaign**. DOT snapshots the current form values, clears the previous plots, and
uses the new acceptance lines immediately. The inputs remain editable after completion, so a new
campaign can be started without restarting the GUI.

During the run, the GUI shows:

- generation progress, elapsed time, and ETA;
- a selected best candidate, recalculated before display;
- its real mirrored turn cross-section;
- every requested harmonic and every block margin;
- trends of minimum margin, worst harmonic residual, and total turns.

Parallel candidate evaluation is optional and off by default for compatibility. It uses separate
processes and does not change the calculations. Enable it for medium or large campaigns after a
short hardware check.

The radial-block option is also off by default. Enable it when winding-friendly radial blocks are
desirable and the campaign is expected to reach its electromagnetic targets before the final
generation. Candidate JSON files and summary images report the RMS and maximum central-cable
alignment deviation for the free-angle blocks.

## 6. Read the results

Each run creates a new timestamped directory. The most useful files are:

| Path | Meaning |
|---|---|
| `campaign.json` | Exact GUI settings |
| `run_manifest.json` | Software versions and hashes of conductor inputs |
| `inputs/` | Immutable conductor-file snapshots |
| `generations/` | Per-generation representative images and data |
| `best_candidate_summary.png` | Cross-section, electromagnetic results, and geometry table |
| `best_candidate.json` | Complete machine-readable representative |
| `best_candidate_geometry.csv` | Per-block `R`, turns, `phi`, and `alpha` |
| `final_pareto_frontier.png` | Harmonic-margin trade-off, colored by total turns |
| `best_topology_designs/` | Up to ten strong designs with distinct block topologies |
| `pareto_candidates.json` | Certified front, search front, and near-feasible diagnostics |

No certified candidate means that no final archived point passed every target during the final
verification. Inspect the near-feasible violations before increasing population or generations:
geometry or search-space bounds must be corrected before more search effort can help.

## 7. Practical sequence

1. Validate conductor links and broad geometric bounds.
2. Run Quick exploration to catch input mistakes.
3. Inspect near-feasible violations and whether multiple topologies survive.
4. Use Design search for normal synthesis.
5. Use Intensive or multiple seeds for demanding qualification.
6. Prefer a certified region with reserve, not a point exactly on every limit.

## 8. Physics reliability

DOT 1.0.0 was compared with a licensed ROXIE service at `localhost:8080` in
1,000 deterministic 2D, coil-only, no-iron simulations: 500 two-layer and 500
four-layer layouts. The cases covered 20–40 mm aperture radii, 3.0–12.5 kA,
2–12 blocks, 5–44 turns, and Nb-Ti, Nb3Sn, and mixed conductor assignments.
Every layout passed physical non-overlap checks before comparison.

Both engines received identical geometry, current, conductors, dipole symmetry,
and reference radius. DOT values used the same final numerical settings applied
to campaign results. The deviations from ROXIE were:

| Quantity | Mean absolute | 95th percentile | Maximum absolute |
|---|---:|---:|---:|
| Bore field | 0.0197% | 0.0525% | 0.0988% |
| Peak field | 0.6709% | 1.1866% | 2.1149% |
| Load-line margin | 0.1140 pp | 0.2785 pp | 0.6035 pp |
| b3 | 1.2146 units | 2.7980 units | 4.8190 units |
| b5 | 0.6507 units | 1.5252 units | 2.4238 units |
| b7 | 0.2725 units | 0.7011 units | 1.7254 units |
| b9 | 0.1035 units | 0.2610 units | 0.5854 units |
| b11 | 0.0406 units | 0.1011 units | 0.2547 units |

Field errors are relative to ROXIE. Margin errors are percentage-point
differences. Harmonic errors are absolute accelerator units because a relative
error is undefined near a zero target.

The comparison supports DOT as a reliable 2D air-core pre-design engine within
the sampled domain. Bore field showed excellent parity, while b3 was the most
sensitive quantity. Do not treat a point exactly on a 5-unit limit as having
cross-tool reserve: for demanding work, prefer a DOT worst harmonic near
2 units or less and independently verify candidates close to acceptance.

The full methodology, topology-separated statistics, raw 1,000-row table, and
reproducible runner are in [`docs/validation`](validation/README.md). This study
does not validate iron, ends, persistent-current effects, mechanics, protection,
tolerances, or arbitrary layouts outside the sampled domain.
