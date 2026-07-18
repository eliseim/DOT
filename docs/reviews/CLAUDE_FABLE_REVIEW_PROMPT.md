# Independent pre-publication review request for DOT

Act as an independent senior reviewer of the entire repository in the current working directory.
This is DOT, an autonomous 2D, air-core/no-iron superconducting dipole cross-section optimizer
intended to replace ROXIE for the scoped electromagnetic calculations and to synthesize layouts
with NSGA-II. We are close to publishing it on GitHub. The standard is therefore not a prototype
demo: the project must be physically defensible within its declared 2D/no-iron boundary,
resilient, reproducible, maintainable, installable by a new user, and free of known release-blocking
bugs.

Important current product decisions:

- Layer 1 radius is exactly the aperture radius; there is no Layer-1 radial-gap input. Radial gaps
  exist only between adjacent layers.
- The post-NSGA-II refinement feature has deliberately been removed because it is not trusted.
- Normal harmonics may have signed targets; the objective and acceptance limit are based on the
  worst residual `abs(b_n - target_n)`.
- The physics scope is 2D, coil-only/no iron. Do not criticize the absence of 3D ends or iron as
  bugs, but do verify that limitations are disclosed and that claims do not exceed that scope.

Review independently; do not assume existing reports or tests are correct. Inspect source, tests,
benchmarks, launchers, packaging, CI, documentation, and Git hygiene. You may run read-only
diagnostics and tests, but DO NOT edit files, create commits, or alter the worktree.

At minimum, investigate:

1. Electromagnetic correctness: Biot-Savart sources, current/bore-field scaling, multipole
   normalization and ROXIE angle/sign conventions, reference radius, peak-field sampling,
   critical-current fits, Cu/non-Cu conversion, cable degradation, operating current, short-sample
   current, and load-line margin.
2. Geometry/manufacturability: keystoned cable placement, insulation, collision/clearance,
   inter-layer anchors, extended nesting constraints, pole-turn proxy, optional blocks, turn bounds,
   repairs, and numerical tolerances.
3. Optimization integrity: constraint scaling/admission, NSGA-II mixed variables, topology
   preservation, elitism, Pareto archive, certification, complexity tie-breaks, deterministic seeds,
   multiprocessing/JIT behavior, cancellation, and failure handling.
4. User experience and outputs: GUI state migrations, progress/ETA, signed harmonic targets,
   ROXIE-ready block tables, alternative topologies, saved generations, and honest certified versus
   near-feasible labeling.
5. Release engineering: fresh install, dependencies, package data, launchers, CI coverage,
   platform compatibility, licenses/citations, README accuracy, ignored/generated/proprietary files,
   public API stability, security, and exception resilience.
6. Verification evidence: assess existing DOT-versus-ROXIE parity tests and identify any missing
   independent parity cases or tolerances that could hide a convention/physics error.

Return a concise but deep Markdown report with:

- an executive publication verdict: `READY`, `READY AFTER FIXES`, or `NOT READY`;
- release blockers first, then high/medium/low findings, each with exact file and line references,
  evidence, user/physics impact, and a specific correction;
- explicit checks that passed and strengths worth preserving;
- a prioritized verification matrix for publication, especially fresh ROXIE parity;
- a final list of suggestions that are safe and justified to implement now versus ideas that should
  be deferred.

Avoid speculative style opinions. Prefer reproducible correctness, physics, and release risks.
