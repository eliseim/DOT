# DOT versus ROXIE publication parity report

**Date:** 18 July 2026
**Scope:** two-dimensional, coil-only/no-iron field, peak-field, critical-surface, and load-line
calculations
**ROXIE execution:** licensed local ROXIE REST service in the `roxie:fixed` container
**DOT revision:** publication worktree before final commit

## Method

The live suite generated no-iron ROXIE inputs from a local licensed `.data` template, inserted the
same native ROXIE `R`, `phi`, `alpha`, turns, current, and conductor assignments used by DOT, ran
ROXIE through `roxieapi`, downloaded each `.output`, and compared parsed ROXIE results with fresh
DOT calculations. The redistributable benchmark CTH cadata catalogue was used; the proprietary
ROXIE template was not copied into the repository.

```powershell
$env:ROXIE_SERVICE_URL = "http://127.0.0.1:8080"
$env:DOT_ROXIE_TEMPLATE = "C:\local\licensed\template.data"
python -m pytest tests/physics/test_roxie_parity_live.py -m live_roxie -q -s
```

Result: **11 passed in 22.16 s**. The stored CTH-14T harmonic-vector regression suite also passed
**5/5** at certification fidelity.

## Bore-field parity

| Case | DOT [T] | ROXIE [T] | Relative error |
|---|---:|---:|---:|
| CTH-14T complete four-layer coil | 12.38987027 | 12.41909100 | 0.23529% |
| Six-turn block, `alpha=0` | 5.00000000 | 5.02418000 | 0.48127% |
| Three-turn pole block, `phi=75`, `alpha=75` | 5.00000000 | 5.00800000 | 0.15974% |
| Single turn, `R=35`, `phi=40` | 5.00000000 | 4.99548300 | 0.09042% |
| Single turn, `R=40`, `phi=30` | 5.00000000 | 5.00325600 | 0.06508% |
| Single turn, `R=45`, `phi=50` | 5.00000000 | 4.98932700 | 0.21392% |

These cases cover the midplane-to-pole ROXIE phi convention, zero and large positive absolute
alpha, one and multiple turns, keystoned cable placement, and the full CTH-14T cross-section. The
largest bore-field difference is **0.4813%**, comfortably inside the declared 2% live-parity bound.

## Peak-field and load-line parity

| Case | DOT peak [T] | ROXIE peak [T] | Peak error | DOT margin | ROXIE margin | Margin error |
|---|---:|---:|---:|---:|---:|---:|
| CTH-LF single turn A | 3.311751 | 3.336500 | 0.7418% | 16.6782% | 16.4012% | 0.2770 pp |
| CTH-LF two-layer B | 2.770214 | 2.756700 | 0.4902% | 36.0934% | 36.2378% | 0.1444 pp |
| CTH-LF `R=34`, `phi=36` | 3.297130 | 3.311800 | 0.4430% | 17.0999% | 16.9352% | 0.1647 pp |
| CTH-LF two turns | 2.680505 | 2.678800 | 0.0636% | 46.9541% | 46.9711% | 0.0170 pp |
| CTH-LF three turns | 3.026713 | 3.062900 | 1.1815% | 45.5440% | 45.2096% | 0.3344 pp |
| CTH-LF four turns | 2.875700 | 2.907000 | 1.0767% | 52.2662% | 51.9879% | 0.2783 pp |
| CTH-LF two-layer single turns | 2.343217 | 2.335300 | 0.3390% | 45.5196% | 45.6044% | 0.0848 pp |
| CTH-LF three-layer single turns | 2.143849 | 2.133900 | 0.4662% | 54.3457% | 54.4466% | 0.1009 pp |
| CTH-HF single turn | 3.156071 | 3.177400 | 0.6713% | 46.0803% | 45.8965% | 0.1838 pp |
| Mixed CTH-HF/CTH-LF two layer | 2.256639 | 2.253000 | 0.1615% | 46.8648% | 46.6682% | 0.1966 pp |

The largest peak-field difference is **1.1815%** and the largest load-line-margin difference is
**0.3344 percentage points**, both inside the suite limits of 2% and 2 percentage points. The set
exercises the type-11 Nb3Sn and type-1 NbTi critical-current fits, cadata Cu/non-Cu conversion,
cable degradation, one/multiple layers, and a mixed-conductor design.

## Harmonic regression

The CTH-14T certification-fidelity test compares DOT's normal harmonic vector at
`Rref=16.6667 mm` with values parsed from a real no-iron ROXIE output:

`b3=-4.20941`, `b5=1.74497`, `b7=2.10137`, `b9=0.79814`, `b11=1.42473` units.

All requested terms pass the documented 1.5-unit absolute tolerance. This is a stored immutable
regression rather than a new ROXIE run because the public repository cannot contain or distribute
the licensed source template. The live main-field cases independently exercise the angle/sign and
turn-placement conventions used by the harmonic calculation.

## Publication assessment

The fresh evidence supports publication for DOT's declared **2D, coil-only/no-iron pre-design**
boundary. It does not validate iron saturation, coil ends, persistent-current magnetization,
mechanics, quench/protection, or construction readiness. Those remain explicitly out of scope.

For repeatability, the live test now reads the template location from `DOT_ROXIE_TEMPLATE` and the
optional catalogue location from `DOT_ROXIE_CADATA`, avoiding a mandatory developer-specific path.
The proprietary template and licensed `roxieapi` remain external prerequisites by design.
