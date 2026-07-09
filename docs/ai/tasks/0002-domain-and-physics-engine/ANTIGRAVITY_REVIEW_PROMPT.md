# Antigravity independent review prompt — TASK 0002-domain-and-physics-engine

You are reviewing a diff produced by another AI worker (Codex) for the DOT
(Dipole Optimization Tool) project's core physics engine. You did not see
the worker's reasoning — judge only the diff, the repository, and the task
spec. This is the highest-stakes review so far: wrong physics here silently
corrupts every downstream design DOT ever produces.

## Inputs

- `docs/ai/tasks/0002-domain-and-physics-engine/TASK.md` — scope and
  acceptance criteria.
- The diff/commit on branch `task/0002-domain-and-physics-engine` in
  `.worktrees/0002-domain-and-physics-engine`.

## What to check — be rigorous, this is physics correctness review

1. **Biot-Savart law correctness.** Is `mu0/(2*pi) * I / rho` applied
   correctly, with the right direction (perpendicular to the line from
   source to field point, right-hand rule)? Check sign conventions produce
   physically sensible field direction, not just correct magnitude.
2. **Independently re-derive at least 2 of the test cases yourself** (don't
   just check that a test exists — recompute the expected number by hand or
   with your own calculation) and confirm the code's test assertions match
   true closed-form physics, not a self-consistent-but-wrong value.
3. **Mirror-symmetry construction.** Does the 2D no-iron dipole symmetry
   (typically: field antisymmetric under y -> -y with sign flip appropriate
   to dipole geometry, and how left-right symmetry is handled) actually
   hold given how mirror images are constructed? Trace through the logic,
   don't just trust a passing test — construct a case in your head (or by
   running one) that would catch a subtly wrong mirror sign and check the
   code against it.
4. **Multipole convention.** Is the normalization (1e-4 relative units at
   reference radius, normal `b_n` vs skew `a_n` separation) internally
   consistent and clearly documented? Would a `b_1` dipole term reported by
   this code correspond to the expected physical dipole strength, or is
   there an off-by-one in harmonic order (`n=1` vs `n=0` indexing is a
   classic bug source here)?
5. **Units consistency.** Trace units through geometry (mm) -> field (T) ->
   current (A) end to end. A missing mm-to-m conversion is the single most
   likely silent bug in this kind of code — check every place `mu0` is used
   against the actual units of `rho`/distance passed in.
6. **Scope discipline & provenance.** Only declared files touched? No
   verbatim copying from the reference tool (structure/naming should differ
   even if the underlying method is the same well-known physics)? Any
   ROXIE dependency or ROXIE fixture used as a test oracle (forbidden — all
   oracles must be closed-form, self-contained analytic computations)?
7. **Test quality.** Are the "expected" values in tests computed
   independently of the code under test (e.g. plain closed-form formula
   inline in the test), or do they suspiciously mirror the implementation's
   internal formula (which would make the test tautological and unable to
   catch a real bug)?

## Output format

Report findings ranked most-severe first — physics/units/sign bugs first,
then scope/provenance, then style. For each: file, line, what's wrong, and a
concrete failure scenario (what wrong design DOT would produce as a result).
End with one of:

- **APPROVE** — safe to merge as-is.
- **APPROVE WITH NITS** — mergeable, minor non-blocking issues listed.
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve on the basis of "tests pass" alone — verify the tests
themselves test the right thing.
