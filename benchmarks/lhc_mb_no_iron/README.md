# Blind LHC MB target-synthesis benchmark

This benchmark gives DOT only the requested coil-only electromagnetic targets,
two layers, the linked `YELLONIN`/`YELLONOU` conductors, and broad geometric
bounds. It contains no published LHC block angles or turn allocation.

`certified_blind_result.json` is generated output and a regression fixture.
The optimizer and sampler never read it. Keeping the target and certificate in
separate files makes accidental reference-layout seeding testable.

The committed designer-facing result is available directly in this folder:

- `best_candidate_cross_section.png`: full mirrored cable-turn geometry;
- `best_candidate.json`: field, current, every harmonic, per-layer margin, and blocks;
- `best_candidate_geometry.csv`: `R`, turns, conductor, `phi`, and `alpha`;
- `pareto_candidates.json`: the certified result in the normal user-facing archive format.

The 28 mm input is the radius of the LHC's 56 mm clear bore. Cable identities
and strand data are cross-checked against the *LHC Design Report*, volume I,
section 7.2: the inner cable has 28 strands of 1.065 mm and the outer cable has
36 strands of 0.825 mm. The conductor names are those used by the cable catalogue supplied for
this benchmark.

The 7 T target is intentionally a no-iron target. It is not the LHC's nominal
8.33 T iron-assisted operating point.

Run after installing DOT's optimization dependencies:

```powershell
dot optimize benchmarks/lhc_mb_no_iron/blind_target.json --output results/lhc_mb
```

The full campaign is deliberately substantial. Use `--quick` only to verify
the pipeline; a quick run is not evidence that the benchmark is solved.
