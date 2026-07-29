# DOT–ROXIE 1,000-case parity study

Date: 29 July 2026  
DOT version: 1.0.0  
ROXIE endpoint: `http://127.0.0.1:8080`  
ROXIE runtime banner: 23.6, git commit `26.1.0.b3`

## Scope

This study compares the DOT and ROXIE forward physics engines for 1,000
two-dimensional, coil-only, no-iron dipole layouts:

- 500 layouts with two layers;
- 500 layouts with four layers;
- aperture radii from 20.004 to 39.968 mm;
- currents from 3.008 to 12.455 kA;
- 2–12 blocks and 5–44 turns;
- eight Nb-Ti, Nb3Sn, and mixed-conductor layer patterns.

The deterministic generator uses seed `20260729`. Every layout passes DOT's
aperture, midplane, pole-boundary, inter-layer, turn-intersection, and
inter-block checks before either engine is evaluated. Layouts are not selected
for good field quality or load-line margin.

Both engines receive the same block radii, turn counts, `phi`, `alpha`, current,
conductor assignments, dipole symmetry, and reference radius. DOT uses its
published final settings: 12×12 bore-field quadrature and 80×80
peak-field sources per turn. ROXIE uses its standard block subdivisions
specified in the generated input. The study therefore measures the difference
between production outputs, including each engine's normal numerical
discretization.

## Error definitions

- Field error: `100 × (DOT − ROXIE) / |ROXIE|`.
- Margin error: `DOT margin − ROXIE margin`, in percentage points.
- Harmonic error: `DOT b_n − ROXIE b_n`, in accelerator units.

Absolute statistics below use the magnitude of those signed errors. Relative
harmonic error is intentionally not used because a valid harmonic may be zero.

## Overall results

| Quantity | Mean absolute | Median absolute | 95th percentile | Maximum absolute | Signed mean |
|---|---:|---:|---:|---:|---:|
| Bore field | 0.0197% | 0.0156% | 0.0525% | 0.0988% | +0.0181% |
| Peak field | 0.6709% | 0.6727% | 1.1866% | 2.1149% | +0.6235% |
| Load-line margin | 0.1140 pp | 0.1019 pp | 0.2785 pp | 0.6035 pp | −0.0243 pp |
| b3 | 1.2146 units | 1.1119 units | 2.7980 units | 4.8190 units | +0.8080 units |
| b5 | 0.6507 units | 0.5738 units | 1.5252 units | 2.4238 units | −0.0132 units |
| b7 | 0.2725 units | 0.2314 units | 0.7011 units | 1.7254 units | −0.0502 units |
| b9 | 0.1035 units | 0.0837 units | 0.2610 units | 0.5854 units | −0.0033 units |
| b11 | 0.0406 units | 0.0351 units | 0.1011 units | 0.2547 units | +0.0053 units |

The 95th-percentile absolute errors separated by topology were:

| Quantity | Two layers | Four layers |
|---|---:|---:|
| Bore field | 0.0567% | 0.0504% |
| Peak field | 1.2381% | 0.9657% |
| Load-line margin | 0.3118 pp | 0.2519 pp |
| b3 | 3.1772 units | 2.1912 units |
| b5 | 1.7768 units | 1.1235 units |
| b7 | 0.7634 units | 0.5251 units |
| b9 | 0.3015 units | 0.1978 units |
| b11 | 0.1208 units | 0.0786 units |

## Interpretation

The bore-field calculation has excellent parity throughout the sampled design
space. Peak field is also close, although DOT's denser conductor
discretization gives a mean positive bias of 0.62%; this is conservative on
average but not a guaranteed bound for every layout. The load-line margin has
no material systematic bias and remained within 0.61 percentage points in all
1,000 cases.

Low-order harmonics are the most sensitive output. The b3 difference remained
below 4.82 units but its 95th percentile was 2.80 units. A design sitting
exactly on a 5-unit limit therefore has insufficient numerical reserve for a
cross-tool handoff. For demanding work, prefer a DOT residual near 2 units or
less and independently verify candidates close to the acceptance boundary.

These statistics validate the implemented 2D coil-only forward model over the
sampled domain. They do not validate iron, ends, persistent-current effects,
mechanics, protection, tolerances, or arbitrary geometries outside that domain.

## Reproducibility

- [`roxie_parity_1000_results.csv`](roxie_parity_1000_results.csv) contains all
  raw DOT and ROXIE values and signed errors.
- [`roxie_parity_1000_summary.json`](roxie_parity_1000_summary.json) contains
  machine-readable coverage, numerical settings, hashes, and statistics.
- [`tools/roxie_parity_study.py`](../../tools/roxie_parity_study.py) is the
  deterministic, resumable runner.
- [`tools/roxie_no_iron_template.data`](../../tools/roxie_no_iron_template.data)
  is the layout-free ROXIE template used for every simulation.

With a licensed local ROXIE service:

```powershell
python tools/roxie_parity_study.py `
  --template tools/roxie_no_iron_template.data `
  --cases-per-topology 500 `
  --workers 8 `
  --checkpoint parity_checkpoint.jsonl `
  --output-csv roxie_parity_1000_results.csv `
  --output-summary roxie_parity_1000_summary.json
```
