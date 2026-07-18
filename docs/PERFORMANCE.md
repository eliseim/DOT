# DOT performance and acceleration

## Implementation

Profiling a representative CTH campaign showed that geometry repair, especially millions of
convex-polygon overlap and closest-distance tests, dominated runtime. DOT therefore applies
Numba's serial nopython JIT to those kernels and to the many-point Biot-Savart calculation. The
field kernel loops directly over probes and sources, avoiding large temporary NumPy matrices.
The analytic four-image dipole symmetry is also used to cancel even/skew multipoles without
constructing mirror-source objects.

Candidate evaluation can additionally use a persistent `ProcessPoolExecutor`. This is an explicit
GUI checkbox, off by default. The automatic worker count leaves one logical CPU free and is capped
at four based on the measured serialization crossover. The JIT kernels themselves are deliberately
serial to avoid nested thread/process pools.
If Numba is absent or `DOT_DISABLE_JIT=1`, the same APIs use portable Python/NumPy fallbacks.

## Controlled benchmark (2026-07-17)

Command: `python benchmarks/performance/benchmark_campaign.py --population 24 --generations 4
--seed 17 --workers N`. This short workload covers sampling, repair, geometry, physics, NSGA-II,
and final certification; it is not a convergence claim. Each timing below is one end-to-end run
after JIT cache warm-up.

Hardware/software: AMD Ryzen 5 5600G, 12 logical CPUs, Windows 10 build 26200, Python 3.11.8,
NumPy 2.4.6, Numba 0.66.0.

| Implementation | Workers | Elapsed | Versus original serial |
|---|---:|---:|---:|
| Original | 1 | 131.457 s | baseline |
| Original process evaluation | 4 | 121.764 s | 7.37% less time |
| JIT geometry + optimized physics | 1 | 30.591 s | 76.73% less time; 4.30x throughput |
| JIT geometry + optimized physics | 4 | 30.060 s | 77.13% less time; 4.37x throughput |
| JIT geometry + optimized physics | 8 | 30.688 s | 76.66% less time; 4.28x throughput |

The final four-worker result is a **337.3% throughput increase** over the original serial run
(`4.373x` as fast), equivalently a **77.13% campaign-time reduction**. With the JIT kernels active,
four processes improve this deliberately small workload by only 1.74% in elapsed time, and eight
are slightly slower because repair remains serial and inter-process serialization is fixed cost.
That measured crossover is why parallel evaluation is optional and disabled by default.

For the representative feasible CTH candidate used during kernel profiling, one combined
harmonic/load-line evaluation fell from 62.575 ms to 5.856 ms: 90.64% less time, or 10.69x
throughput. Final Pareto objective vectors were unchanged apart from floating-point roundoff below
`3e-13`.

Results depend on topology, valid-candidate fraction, population size, CPU, memory bandwidth, and
security/virtualization policy. Re-run the script on target hardware before selecting the parallel
checkbox for long production campaigns.
