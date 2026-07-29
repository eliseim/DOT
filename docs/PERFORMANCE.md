# DOT performance and acceleration

## Implementation

Profiling a representative CTH campaign showed that geometry repair, especially millions of
convex-polygon overlap and closest-distance tests, dominated runtime. DOT therefore applies
Numba's serial nopython JIT to those kernels and to the many-point Biot-Savart calculation. The
field kernel loops directly over probes and sources, avoiding large temporary NumPy matrices.
The analytic four-image dipole symmetry is also used to cancel even/skew multipoles without
constructing mirror-source objects.

Repeated geometry is reused with an exact, bounded cache on immutable block values. A second exact
cache recognizes byte-identical repaired genomes but leaves every individual in the NSGA-II
population, so selection pressure and topology representation are unchanged. Axis-aligned bounding
boxes reject polygon pairs that provably cannot overlap before the exact collision/distance kernel
runs.

Candidate repair and evaluation can additionally use one persistent `ProcessPoolExecutor`. This is
an explicit GUI checkbox, off by default. The automatic worker count leaves one logical CPU free
and is capped at four based on the measured Windows crossover. The JIT kernels themselves are
deliberately serial to avoid nested thread/process pools.
If Numba is absent or `DOT_DISABLE_JIT=1`, the same APIs use portable Python/NumPy fallbacks.

## Controlled benchmark (2026-07-17)

Command: `python tools/benchmark_campaign.py --population 24 --generations 4
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
That historical result motivated keeping parallel execution optional and disabled by default.

For the representative feasible CTH candidate used during kernel profiling, one combined
harmonic/load-line evaluation fell from 62.575 ms to 5.856 ms: 90.64% less time, or 10.69x
throughput. Final Pareto objective vectors were unchanged apart from floating-point roundoff below
`3e-13`.

Results depend on topology, valid-candidate fraction, population size, CPU, memory bandwidth, and
security/virtualization policy. Re-run the script on target hardware before selecting the parallel
checkbox for long production campaigns.

## Controlled benchmark after exact reuse and parallel repair (2026-07-27)

The same command, seed, hardware class, Python environment, search settings, and final
verification path were repeated after the exact caches, broad phase, and process-pool
repair were added.

| Current implementation | Workers | Elapsed | Exact search-front objectives |
|---|---:|---:|---|
| Portable fallback (`DOT_DISABLE_JIT=1`) | 1 | 19.503 s | reference |
| JIT + exact caches | 1 | 10.895 s | equal within `2.4e-13` |
| JIT + exact caches + parallel repair/evaluation | 4 | 8.777 s | bit-for-bit equal to JIT serial |

Against the original 131.457-second serial measurement, the current four-worker path is
**14.98x as fast**: a **93.32% campaign-time reduction**, or a **1,397.7% throughput increase**.
Against the previous 30.060-second accelerated implementation, it is 3.42x as fast (70.80% less
time). Four workers now reduce time by 19.43% even for this small 24-candidate benchmark because
repair as well as physics evaluation is dispatched; larger 96-candidate trials measured a 35.4%
reduction relative to current serial execution.

Search-quality validation used the blind two-layer LHC-like benchmark with population 96, 80
generations, seed 7, and four workers. The complete search took 79 seconds before final artifact
writing, retained all 16 admissible active-block-count families, and returned certified 3+1 and
2+2 block layouts. The best achieved 7.000 T, 27.171% minimum margin, and a
3.524-unit worst normal harmonic residual. This is a convergence demonstration, not proof that
every seed or target set will converge.

## Remaining measured optimization targets

Further speedups are possible, but they should be qualified against electromagnetic parity and
search convergence before becoming defaults:

1. **Batched structural repair.** The repair chain performs ordering, nesting, and up to three
   coupled ground-truth passes. A future array-oriented representation could reduce Python object
   overhead, but it must reproduce every exact feasibility decision.
2. **Adaptive hardware calibration.** A short optional startup benchmark could recommend serial or
   process execution for the current CPU and security policy. DOT currently leaves this decision
   explicit because process startup behavior varies markedly across GitHub users' systems.
3. **Lower-overhead process payloads.** Very large populations may benefit from compact shared
   arrays on Windows. The current ordered chunked map is intentionally simple and deterministic.

DOT deliberately does not combine process-level campaign parallelism with Numba's parallel mode:
that would oversubscribe many user systems. Any new accelerator should keep the portable serial
fallback, remain optional when hardware-sensitive, and reproduce the same certified Pareto set to
floating-point tolerance.
