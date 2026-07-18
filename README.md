# DOT — Dipole Optimization Tool

DOT autonomously synthesizes and certifies two-dimensional, coil-only superconducting dipole
cross-sections. It combines exact no-iron current scaling, cable-level Biot–Savart fields,
ROXIE `.cadata` conductor resolution, critical-surface/load-line calculations, manufacturability
constraints, and NSGA-II Pareto search.

DOT is a pre-design engine, not a general replacement for every ROXIE capability. Version 0.1
does not model iron/saturation, coil ends, persistent-current magnetization, stress, quench
protection, or three-dimensional fields.

## Validated result

The repository includes a blind LHC MB-style benchmark. Its search input contains the
requirements, two layer cables, and user-fixed first-block anchors derived from the requested
gaps—no published wedge-block positions or turn allocation. DOT generated and certified a
different feasible cross-section at 7 T:

| Quantity | Certified result | Requirement |
|---|---:|---:|
| Bore field | 7.000 T | 7.000 T |
| Minimum load-line margin | 27.74% | ≥25% |
| Operating current | 10.825 kA | reported, not constrained |
| `b3`, `b5`, `b7`, `b9`, `b11` | −3.85, −4.97, −4.01, 0.89, 0.12 units | each ≤5 units |
| Aperture radius | 28 mm | 28 mm |
| Midplane / inter-layer gap | 0.15 / 0.50 mm | 0.15 / 0.50 mm |
| Minimum inter-block closest-point clearance | 0.190 mm (Layer 2) | 0.10 mm per layer |
| Layer 1 pole-turn closest-point distance | 5.107 mm | ≥0.10 mm benchmark setting |

The target is [blind_target.json](benchmarks/lhc_mb_no_iron/blind_target.json), and the immutable
output certificate is
[certified_blind_result.json](benchmarks/lhc_mb_no_iron/certified_blind_result.json). The latter
is regression data only and is never read by the optimizer. It records its historical generation
provenance, including the experimental local stage that was later removed; the current release
re-certifies the geometry but exposes only the NSGA-II search path for new campaigns.

Additional blind, layout-free qualification campaigns are provided for
[CTH-14T](benchmarks/cth14t_no_iron/blind_target.json) and
[FalconD](benchmarks/falcond_no_iron/blind_target.json). They use report-derived conductor chains
and clearance-derived first anchors, but intentionally contain no reference wedge-block positions
or turn allocations.

## Install and run

### Windows designer install (recommended)

Double-click [`launch_dot_gui.cmd`](launch_dot_gui.cmd). On its first run the launcher creates a
private `.venv`, installs DOT and every required package, installs Numba acceleration when the
platform supports it, and opens the GUI. Later runs reuse that environment. The legacy
`launch_gui.bat` name invokes the same installer/launcher.

### Command-line/developer install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[acceleration,dev]"
dot validate benchmarks/lhc_mb_no_iron/blind_target.json
dot optimize benchmarks/lhc_mb_no_iron/blind_target.json --quick --output results/smoke
dot gui
dot-gui
```

Plain `python -m pip install -e .` remains supported on platforms where Numba is unavailable;
DOT then uses its portable Python geometry kernels. `dot gui`, `dot-gui`, and the launcher all
open the same application.

`--quick` is a pipeline smoke test, not a convergence claim. Remove it for the configured
multi-seed campaign. Only candidates that pass the fixed high-fidelity certification are emitted
as successful Pareto points; search-only near misses are stored separately with named normalized
violations.

## Interactive campaign progress

Launch `dot-gui` for the designer workflow. During every campaign it shows:

- a determinate generation progress bar, elapsed time, and moving-window ETA;
- the best target-balanced candidate in the current population;
- the real mirrored cable-turn cross-section and its evolving block table;
- every requested harmonic, every ROXIE-numbered block margin, operating current, and
  total-turn-count convergence.

The vertical handle between campaign parameters and results is a draggable horizontal splitter.
Press and drag it with the mouse to make the left parameter pane wider or narrower; its vertical
scrollbar remains available independently.

The **Parallel candidate evaluation** checkbox is deliberately off by default. When enabled, DOT
uses separate processes for independent candidate physics evaluations, leaves one logical CPU for
the operating system/GUI, and caps the automatic count at four workers (61 on Windows is the
absolute Python limit). This can help large populations, while smaller campaigns may see little
benefit because serialization and process startup have fixed costs. Numba's kernels stay serial,
so enabling both features does not create nested thread pools or CPU oversubscription. Set the
environment variable `DOT_DISABLE_JIT=1` before launch only when diagnosing a Numba/platform issue.

For each layer the user enters a physical **azimuthal gap** and, after Layer 1, a **radial gap**.
DOT fixes Layer 1 at the aperture radius, derives `phi=atan(azimuthal_gap/R)`, and fixes `alpha=0`.
Each later R is the outer x-coordinate of the preceding layer's first insulated turn plus the
requested radial gap. DOT chooses the first block's turn count and autonomously creates up to the
specified maximum number of later blocks by selecting their existence, turns, phi, and alpha.
Angles use the ROXIE/CTH convention directly: `phi=0` at the midplane and increases toward
`phi=90` at the pole; `alpha` is the absolute ROXIE cable-frame angle.

Each row in **Per-Layer Topology** has a **Min block clearance [mm]** field. This is an
engineering clearance, measured as the exact shortest Euclidean distance between the insulated
turn polygons of every pair of blocks in that layer. It can therefore be different in the inner
and outer layers. The separate **Numerical tolerance [mm]** field is only the geometry classifier's
small round-off/contact tolerance; it does not reserve physical space.

Headless campaign JSON uses the same gap-derived anchor contract and declares
`"geometry_angle_convention": "roxie"` at the top level. For example:

```json
"layers": [
  {
    "azimuthal_gap_mm": 0.15,
    "max_blocks": 4,
    "turn_bounds": [1, 18]
  },
  {
    "azimuthal_gap_mm": 0.15,
    "radial_gap_mm": 0.5,
    "max_blocks": 4,
    "turn_bounds": [1, 22]
  }
]
```

Layer 1 deliberately has no `radial_gap_mm`: its `R` is the aperture radius. Each later layer
declares the radial gap from the preceding layer's first insulated turn.

Inter-block clearance accepts either the legacy scalar or one value per layer:

```json
"geometry": {
  "inter_block_gap_mm": [0.1, 0.5]
}
```

This requires 0.1 mm in Layer 1 and 0.5 mm in Layer 2. Existing scalar configurations continue to
apply the same requirement to every layer.

Layer nesting enforces both the conventional prolonged pole-side turn edge and the more
conservative prolonged lower side of the inner layer's pole turn. The latter prevents an outer
layer from entering that winding envelope during windability screening.

`geometry.min_pole_turn_radius_mm` is specified once and applies only to Layer 1. It is the exact
minimum distance from the pole axis (`x=0` in DOT's quadrant) to any point of an insulated cable
polygon. Because DOT represents straight 2D blocks rather than a curved cable centerline, this is
a conservative pole-turn bend-radius proxy, not a literal curvature calculation. The former
maximum-pole-angle control is no longer part of user campaigns.

The **Advanced harmonics** tab accepts a signed no-iron target for each requested normal harmonic.
DOT optimizes and certifies the maximum residual `|b_n - target_n|`, while continuing to report the
physical harmonic, target, and signed residual separately. For example, set `b3 = -3` when a known
iron-yoke model is expected to add `+3` units at the operating point. Harmonics left at zero retain
the standard no-iron target. Headless configurations use the equivalent mapping:

```json
"acceptance": {
  "max_harmonic_units": 5.0,
  "harmonic_targets": {"b3": -3.0, "b5": 0.0}
}
```

The GUI calculates a non-binding maximum-current suggestion using only the Layer-1 conductor and
its linked critical-current fit, strand `Cu/non-Cu` ratio, strand count, cadata cable degradation,
temperature, target bore field, and desired margin. The fit `Jc` is interpreted as non-copper
current density and is multiplied by `N*pi*d^2/[4*(1+Cu/nonCu)]`. It assumes `Bpeak=Bbore`, so the
displayed value is an upper-bound recommendation; the editable current cap is never overwritten
because a real coil has `Bpeak>Bbore`.

Search effort is offered as **Quick exploration** (64 x 40), **Design search** (160 x 100), and
**Intensive search** (300 x 200), plus **Custom** population/generation inputs.

The Stop button now stops cooperatively after the active generation. A long generation is never
terminated halfway through a population evaluation.

Each GUI run creates `<output>/<campaign>-YYYYMMDD-HHMMSS/`. The folder contains:

| Artifact | Purpose |
|---|---|
| `campaign.json` | Exact GUI inputs used for the run |
| `generations/gen_NNNN.png` | Best cross-section visible at that generation |
| `generations/gen_NNNN.json` | Its metrics and ROXIE-ready block table |
| `best_candidate_cross_section.png` | Final certified representative geometry |
| `best_candidate_summary.png` | Cross-section, electromagnetic table, and ROXIE geometry table in one printable image |
| `best_candidate.json` | Final harmonics, margins, current, field, and blocks |
| `best_candidate_roxie_blocks.csv` | Per-block `R`, turns, native ROXIE `phi`, and native ROXIE `alpha` |
| `pareto_candidates.json` | Certified candidates, near-feasible diagnostics, and the complete final search-fidelity Pareto front |
| `final_pareto_frontier.png` | Worst harmonic versus minimum margin, colored by total turns, with acceptance lines |
| `best_topology_designs/` | One flat folder containing the best design from each of up to 10 distinct topologies |
| `best_topology_designs/design_NN_*_summary.png` | One-sheet cross-section, electromagnetic results, and ROXIE block geometry |
| `best_topology_designs/design_NN_*.json` | Complete machine-readable design record |
| `best_topology_designs/design_NN_*_roxie_blocks.csv` | ROXIE-ready block table |
| `best_topology_designs/manifest.json` | Ranking, topology, performance, and filenames for the folder |

The generation and final candidate JSON files contain every requested odd harmonic's physical
value, signed target, and residual,
`margins_by_block`/`per_block_margin` with continuous ROXIE block numbering,
`inter_block_clearances`, and `first_layer_pole_turn_clearance_mm`. The GUI shows the same
diagnostics while the campaign is running and for the selected final candidate.

DOT also exports up to 10 alternatives into one flat `best_topology_designs` folder. Exactly one
best target-balanced member is retained from each blocks-per-layer topology family, so duplicate
topologies do not occupy designer-facing slots. Each topology gets a composite summary PNG, JSON,
and ROXIE CSV with the same basename. If no candidate passes certification, the same output is
generated from the search frontier and explicitly labelled `uncertified_search_front`.

The live convergence dashboard has three aligned generation plots: minimum load-line margin,
worst requested harmonic-target residual, and total turns for the current best candidate.

When electromagnetic objective pairs are equal within numerical precision, archive and representative
selection prefer fewer total turns, then fewer active blocks. These are secondary tie-breakers, not
extra objectives, so they do not remove a physically distinct harmonic-margin trade-off.

The headless `dot optimize ... --output <folder>` workflow prints one progress/ETA line per
generation and writes the same final design artifacts directly into `<folder>`, with per-seed
generation snapshots below `seed_<seed>/generations/`.

## Engineering conventions

- `aperture_radius_mm` is a physical bore radius; `reference_radius_mm` is independently declared.
- Harmonics use the CERN/European convention in units of `10⁻⁴` of the main normal dipole.
- Margin is `100 × (1 − Iop/Iss)` and is evaluated for every linked conductor layer.
- Current is eliminated analytically from the genome because the 2D no-iron field is linear.
- Cable geometry and critical-current fits are resolved through the selected cadata `CONDUCTOR`
  chain; records are never mixed by “first row” selection.
- Search and certification fidelities are versioned separately.
- DOT uses the CTH-14T report/ROXIE convention directly: `phi=0` at the midplane, increasing toward
  `phi=90` at the pole. `alpha` is the absolute ROXIE cable-frame angle. No export conversion is
  required; the reported `R`, turns, `phi`, and `alpha` can be entered directly in ROXIE.

See the [implementation report](docs/DOT_IMPLEMENTATION_REPORT.md) and the detailed
[technical review](docs/DOT_TECHNICAL_REVIEW_AND_IMPLEMENTATION_GUIDE.md). Reproducible acceleration
methodology and measured timings are in [the performance report](docs/PERFORMANCE.md). Fresh live
field, peak-field, and load-line comparisons are recorded in the
[ROXIE parity report](docs/reviews/ROXIE_PARITY_2026-07-18.md).

## Project status and limitations

DOT 0.1 is suitable for reproducible research and 2D air-core electromagnetic pre-design. A
candidate is not a construction drawing or magnet sign-off. Independent ROXIE/measurement review,
tolerance analysis, mechanical design, protection analysis, and three-dimensional end design are
still required for an engineering magnet.

DOT is distributed under the [MIT License](LICENSE). Copyright 2026 Mattia Elisei, INFN Milan and
University of Rome La Sapienza.

## Development

```powershell
python -m pytest -q
python -m ruff check src tests
```

Optional live-ROXIE tests remain local and are skipped when the required installation/data are not
available. To run them, install `.[roxie]` plus CERN's licensed `roxieapi`, start the ROXIE REST
service, and point `DOT_ROXIE_TEMPLATE` at a local `.data` template. `DOT_ROXIE_CADATA` is optional;
the redistributable CTH benchmark catalogue is the default. Then run:

```powershell
$env:ROXIE_SERVICE_URL = "http://127.0.0.1:8080"
$env:DOT_ROXIE_TEMPLATE = "C:\path\to\template.data"
python -m pytest tests/physics/test_roxie_parity_live.py -m live_roxie -q -s
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
