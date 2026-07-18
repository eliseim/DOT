# DOT technical review and implementation guide

> **Implementation status (14 July 2026):** this document preserves the original
> audit and rationale. Its P0 findings have since been implemented and verified;
> see [DOT_IMPLEMENTATION_REPORT.md](DOT_IMPLEMENTATION_REPORT.md) for the current
> behavior, blind LHC certificate, and remaining model-boundary work.
> DOT now uses the CTH-14T report/ROXIE angles natively (`phi=0` at the
> midplane, increasing toward the pole, with absolute ROXIE `alpha`). Any
> complementary DOT-angle discussion below is retained only as audit history.
> The experimental refinement stage discussed in the historical audit was removed before public
> release; the current tool returns the certified NSGA-II Pareto archive directly.

**Review date:** 14 July 2026
**Scope:** two-dimensional, coil-only superconducting dipole cross-section design; no iron
**Reference design:** CTH-14T four-layer hybrid Nb3Sn/NbTi dipole
**Original verdict:** promising electromagnetic kernel, not yet trustworthy as an autonomous design tool

## 1. Executive assessment

DOT already contains a credible 2D coil-field and critical-current foundation. The strongest evidence is a blind-style comparison made from the published CTH-14T winding table: with iron disabled, live ROXIE gives a 12.4191 T bore field and a 25.1416% limiting load-line margin at 12,238 A; DOT gives a 25.1684% limiting margin. The 0.027 percentage-point difference is excellent for a pre-design tool. The implemented Bottura NbTi and CERN Nb3Sn type-11 critical-surface equations also agree with the equations supplied with the project.

The tool is nevertheless not ready for magnet-design decisions. The current GUI:

- converts harmonic units a second time, displaying 2 units as 20,000 units and applying the inverse error during candidate ranking;
- optimizes only through order 4, which in an ideal symmetric dipole means it effectively controls only `b3`, not `b5`, `b7`, `b9`, or `b11`;
- uses a reference radius of 0.625 times the aperture radius instead of the stated two-thirds convention;
- exposes angle bounds and applies an alpha repair that exclude blocks from the published CTH design;
- does not activate inter-block gap, pole gap, or layer-nesting constraints;
- rejects the exact CTH cross-section through an unsuitable global inter-layer clearance test and numerical contact tolerances.

Consequently, the tool can calculate the important electromagnetic quantities for a CTH-like coil, but its optimizer cannot yet be expected to discover that coil autonomously or identify it correctly when found.

DOT can realistically aim to replace ROXIE for **2D, air-core, coil-field electromagnetic pre-design** after the P0 validation work in this report. It should not be advertised as a general ROXIE replacement: ROXIE integrates iron and saturation, coil ends and 3D fields, persistent-current effects, forces, tolerances, drawings/CAD, and manufacturing data in addition to coil-field optimization [1].

## 2. What was reviewed

The review covered:

- domain geometry, keystoned-cable placement, collision and clearance checks;
- Biot-Savart source placement, bore-field scaling, and harmonic convention;
- `.cadata` parsing, conductor resolution, critical surfaces, and load-line margin;
- NSGA-II encoding, repair operators, constraints, objectives, refinement, and result selection;
- the target-synthesis GUI and configuration flow;
- the legacy `magnet_optimization.py` and `config.yaml` supplied with this review;
- the CTH-14T electromagnetic design report and Gupta lectures 3–7;
- primary literature on ROXIE, critical-current scaling, multiobjective optimization, tolerances, and integrated magnet optimization.

Automated checks at the review baseline:

| Check | Result |
|---|---:|
| Repository test suite | 194 passed, 5 skipped |
| Live ROXIE integration suite | 11 passed |
| Ruff | 5 findings in current working tree |
| `git diff --check` | Clean |

The existing working tree contained unrelated modified and untracked work before this review. No production source file was changed as part of this report.

## 3. CTH-14T reference benchmark

### 3.1 Published design

The CTH report defines a four-layer, 50 mm-aperture cos-theta dipole. Layers 1–2 use Nb3Sn and layers 3–4 use NbTi. Its nominal iron-assisted point is 14 T at 12,238 A, with reported load-line fractions of 82% and 81% for the two conductor grades. The exact block radii, angles, inclinations, and turn counts appear on report page 11. The report uses a reference radius of 16.667 mm, two-thirds of the 25 mm aperture radius. See the local [CTH electromagnetic design report](../HFM_KE6538___D1_1__CTH_14T_Electromagnetic_design_and_conductor_choice.pdf), especially pages 5, 7–9, 11, 15, and 17.

The user's target—approximately 12.4 T, at least 25% margin, and field quality within 5 units without iron—is consistent with a live ROXIE reconstruction of that table.

### 3.2 Coil-only comparison at 12,238 A

| Quantity | Live ROXIE, no iron | DOT | Difference |
|---|---:|---:|---:|
| Bore field | 12.419091 T | within 2% in the current reference test | certification still needed at fixed source fidelity |
| Peak field, limiting layer | 12.7997 T | 12.7938 T | -0.046% |
| Minimum margin | 25.1416% | 25.1684% | +0.0268 percentage points |
| `b3` at 16.667 mm | -4.2094 units | -1.8814 units | +2.3280 units |
| `b5` | +1.7450 units | +1.3403 units | -0.4047 units |
| `b7` | +2.1014 units | +2.0137 units | -0.0877 units |
| `b9` | +0.7981 units | +0.8122 units | +0.0141 units |
| `b11` | +1.4247 units | +1.2760 units | -0.1487 units |

The DOT harmonic values above use its current production 3-by-3 source discretization. All remain within the requested 5-unit envelope, but the `b3` discrepancy shows that a versioned source-model convergence study is required before claiming ROXIE parity. A separate source discretization moved `b3` by several units, while high orders were more stable.

Layer-by-layer DOT margins in the detailed near-field evaluation were 25.168%, 34.244%, 27.296%, and 26.872%. Correctly finding layer 1 as limiting is as important as matching the overall percentage.

### 3.3 Required permanent benchmark

Create a repository-owned `benchmarks/cth14t_no_iron/` case containing:

- conductor data or a legally redistributable minimal `.cadata` fixture;
- exact block table, cable dimensions, insulation, temperature, current, aperture radius, and reference radius;
- ROXIE version/build and input-deck provenance;
- golden values for `B0`, layer peak fields, layer margins, and `b3` through `b11`;
- both DOT search-fidelity and certification-fidelity results.

Initial acceptance bands should be explicit rather than hidden in generic tests:

- bore field: relative error no greater than 0.5%;
- limiting peak field: relative error no greater than 0.5%;
- minimum margin: absolute error no greater than 0.5 percentage points and same limiting layer;
- each normal harmonic through `b11`: absolute difference no greater than 1 unit after source-model convergence, or a justified order-specific tolerance;
- exact CTH geometry: feasible at the documented clearances, apart from explicitly classified numerical contact tolerances.

The tolerance should be tightened only after documenting ROXIE's cable-current representation and demonstrating DOT convergence.

## 4. Findings and corrective actions

Priority meanings: **P0** blocks trustworthy use or the CTH target; **P1** is required for an effective design tool; **P2** is required for a mature public project.

### P0-1 — Harmonic units are converted twice in the GUI

`field_quality_objective()` already returns accelerator units (`10^-4` of the main field). `target_synthesis_gui.py:634` multiplies the result by `1e4`, while `_best_candidate()` at line 1067 divides the user's unit limit by `1e4`.

**Impact:** correct designs are shown as failures and candidate ranking is distorted by four orders of magnitude.

**Fix:** make `HarmonicUnits` an explicit semantic type or, at minimum, adopt names ending in `_units` at every boundary. Remove both extra conversions. Keep conversion from normalized multipole coefficient to units in exactly one function.

**Acceptance tests:** a synthetic coefficient `b3/B1 = 5e-4` must be displayed, compared, serialized, and ranked as 5.0 units in the domain layer, GUI, campaign archive, and plots.

### P0-2 — The optimizer does not control the required harmonics

The GUI hard-codes `max_order=4` (`target_synthesis_gui.py:787`). The objective scans orders 2 through `max_order`; under the enforced dipole symmetries the relevant allowed terms are `b3`, `b5`, `b7`, `b9`, `b11`, and so on. The current GUI search therefore effectively optimizes only `b3`.

**Fix:** default to at least order 11 and expose the maximum order. Better, accept an explicit harmonic specification:

```text
normal: {3: [-5,+5], 5: [-5,+5], 7: [-5,+5], 9: [-5,+5], 11: [-5,+5]}
skew:   {2: [-tol,+tol], ...}
Rref:   16.667 mm
```

Support both a worst-normalized-violation constraint and reported individual harmonics. Do not hide all multipoles behind a single scalar in results.

**Acceptance test:** a candidate with `b3=0.1` and `b5=8` must be rejected for a 5-unit specification.

### P0-3 — Reference radius is wrong and implicit

The GUI computes `Rref = 0.625 * aperture_radius` (`target_synthesis_gui.py:1098`), although its guidance and the CTH report use two-thirds. Because an order-`n` normalized multipole scales as `Rref^(n-1)`, the error grows rapidly with order.

**Fix:** make `r_ref_mm` a required, visible engineering input, with “two-thirds of aperture radius” available only as a preset. Store it with every candidate and print it beside every harmonic table.

**Acceptance test:** the CTH preset must resolve to 16.6667 mm for a 25 mm aperture radius, and round-trip through configuration and results.

### P0-4 — The search space and alpha repair exclude valid ROXIE geometry

Default `phi` is limited to 10–70 degrees, while the CTH midplane blocks use approximately 89.65 degrees in DOT's convention. Default alpha bounds do not cover most CTH block inclinations. `AlphaAlignmentRepair` further clamps free alpha to `[phi-90, phi-75]`; verified CTH blocks lie outside this heuristic window.

**Impact:** valid, published designs are unreachable or altered before evaluation. A repair operator has become an undocumented design rule.

**Fix:**

1. Document the ROXIE-to-DOT angle transform with drawings and golden examples.
2. Set physically broad defaults that contain the reference design.
3. Remove the alpha-window clamp as a mandatory repair. Use it only as an optional sampling prior or correlated mutation.
4. Let exact polygon feasibility determine validity.
5. Seed the population with known feasible layouts and learn covariance/correlations from survivors instead of deleting unusual angles.

**Acceptance tests:** encode/decode every CTH block without clamping; repair must be idempotent on the reference genome; mutation must be able to reach a neighborhood on both sides of each reference angle.

### P0-5 — Current geometry rules reject the exact CTH coil

Running the exact report table against the true 25 mm aperture produced:

- an apparent 0.040 mm aperture intrusion;
- false inter-layer violations of approximately 0.10–0.33 mm;
- nanometre/micrometre midplane and turn-overlap violations.

The largest conceptual problem is `check_inter_layer_spacing()`: it compares the global maximum vertex radius of the inner layer with the global minimum polygon radius of the outer layer. This requires two layers to be separated as concentric annuli. Real cos-theta layers have local faces and can have different radial extrema at different azimuths while retaining the specified local inter-layer spacer.

The global `_EPSILON = 1e-9 mm` is also far below meaningful geometric and manufacturing resolution. Consecutive turns intended to touch can be reported as overlapping through numerical construction noise. Some existing CTH fixtures pass the reference radius (16.667 mm) as the aperture radius, masking the true aperture check.

**Fix:**

- define the aperture radius and harmonic reference radius as distinct types/fields;
- evaluate inter-layer insulation using minimum polygon-to-polygon distance for physically adjacent surfaces, or construct layers from a shared offset/interface curve;
- classify contacts: same-block intended contact, insulated clearance, prohibited collision;
- use scale-aware numerical tolerances and a separate engineering clearance tolerance (for example micrometre-scale numerical tolerance versus 0.1–0.5 mm design rules);
- derive bare, insulated, and structural envelopes explicitly;
- validate against CTH and at least one simpler hand-computable geometry.

**Acceptance test:** the exact CTH table with 25 mm aperture, 0.15 mm midplane gap, and 0.5 mm inter-layer gap must pass without the repair changing turn counts.

### P0-6 — Bare-conductor turns lose their per-turn keystone orientation

The margin path reconstructs each bare conductor turn using `block.alpha_deg` for every turn (`objectives.py:260–262`). `Block.turns()` changes orientation from turn to turn as a keystoned cable is stacked. Reusing the block's initial alpha is therefore wrong, especially for outer-layer blocks with many turns.

The current CTH limiting margin still agrees well with ROXIE, so this bug does not invalidate the benchmark conclusion; it does make the agreement less robust for other cables and topologies.

**Fix:** carry the actual local frame/transform with each generated turn and derive its bare envelope from that transform. Avoid reverse-engineering conductor geometry from an already insulated polygon.

**Acceptance test:** for a multi-turn keystoned block, bare and insulated centroids/orientations must advance consistently for every turn; zero-keystone behavior must remain unchanged.

### P0-7 — `.cadata` resolution can silently combine unrelated records

When no conductor name is supplied, `_first_conductor_data()` independently selects the first strand, cable, and REMFIT records. That triplet need not correspond to any `CONDUCTOR` record. A plausible-looking but nonexistent conductor can therefore be evaluated.

There is also a schema naming error: `ConductorRecord.remfit_name` is populated from column 8 of a ROXIE `CONDUCTOR` row, which is the quench-material field in the reviewed files, not the REMFIT. Resolution works in common files only because the `FILAMENT` indirection takes precedence. The core cable record contains strand count and degradation but not the dimensions and insulation needed by geometry; the GUI reparses those sections independently.

**Fix:** create one typed, loss-aware cadata domain model:

```text
Conductor -> Cable -> Strand -> Filament -> REMFIT
          -> Insulation
          -> transient/quench metadata (preserved even if unused)
```

Require an explicit `CONDUCTOR` selection when multiple conductors exist. If a file has exactly one resolvable conductor, select that conductor as a whole. Preserve unsupported fit records and mark them unavailable rather than failing an entire mixed catalog. Correct the type-11 error message, which still says only type 1 is supported.

**Acceptance tests:** multi-conductor files, reordered sections, unsupported+supported mixed fits, missing links, duplicate names, and insulation/dimension round trips.

### P0-8 — The returned “ParetoResult” is not guaranteed Pareto-optimal

After NSGA-II, refinement candidates are concatenated with the optimizer candidates (`runner.py:914–920`) without deduplication or a final nondominated sort. The final population can also have been evaluated under annealed constraints before the last callback update; there is no explicit final re-evaluation at the final engineering thresholds.

Constraint violation is dimensionally inconsistent: geometry millimetres and degrees are summed into one value, then coexist with turns, harmonic units, percentage points, and amperes. The live “closest” candidate uses the maximum raw constraint value, so a one-ampere current excess can outweigh a severe geometric failure merely because of units.

**Fix:**

1. Give every constraint a physical name, scale, and normalization.
2. Keep geometry categories separate, or aggregate only dimensionless normalized violations.
3. Re-evaluate the final population and all refined candidates at immutable final thresholds.
4. Remove duplicates using topology plus tolerance-aware continuous genes.
5. Perform a nondominated sort and return only feasible rank-zero candidates.
6. Preserve an optional “near-feasible archive” separately, with named violations.
7. Assert programmatically that no returned candidate dominates another.

**Acceptance tests:** invariance to expressing current in A versus kA; refinement cannot add a dominated point; changing an annealed limit after the last generation cannot leak an invalid point into the final front.

## 5. Optimization strategy for autonomous design

### 5.1 Formulate engineering specifications as constraints

For a target synthesis problem, use hard or progressively annealed constraints for:

- `|B0 - Btarget|` (normally eliminated exactly by linear current scaling in a no-iron model);
- each specified harmonic at the declared `Rref`;
- minimum layer margin;
- maximum current, if power-supply/cable-limiting;
- aperture, midplane, pole, wedge/inter-block, inter-layer, and collision rules;
- minimum/maximum active blocks and layer/total turn budgets.

The current exact operating-current scaling is a good design decision for the no-iron hypothesis: it removes current from the genome and avoids wasting evolution on a linear degree of freedom. Current should become a gene only when nonlinear iron, persistent-current effects, or circuit constraints are introduced.

### 5.2 Use objectives that distinguish useful feasible designs

Two objectives—worst harmonic and negative margin—do not sufficiently penalize conductor-heavy coils. Gupta explicitly treats field quality, field/coil efficiency, and peak field as separate concerns in the [magnet design lectures](../magnet_design_course_gupta/rg-uspas06-lecture04.pdf), especially slides 3, 9–10, 23, and 37. Recent integrated optimization work likewise includes field, margin, field quality, conductor efficiency, and stress [2].

Recommended default objectives after feasibility normalization:

1. minimize worst normalized harmonic utilization;
2. maximize minimum load-line margin;
3. minimize conductor volume/cross-sectional area or a cost-weighted Nb3Sn/NbTi metric;
4. optionally minimize peak-field enhancement `Bpeak/Bbore`.

Keep the default front to three objectives if usability is more important than a large many-objective archive. Report secondary metrics for every candidate even when they are not objectives.

### 5.3 Make evaluation explicitly multi-fidelity

Gupta's workflow recommends broad geometric exploration followed by peak-field calculation on promising cases. DOT already contains the beginnings of this idea, but fidelity is controlled through implementation details rather than a public contract.

Define three versioned levels:

- **screen:** inexpensive analytic or low-source bore harmonics and cheap geometry rejection;
- **search:** converged-enough cable source model and moderate near-field mesh;
- **certify:** fixed high-fidelity source/near-field convergence, all individual harmonics, layer margins, and robustness analysis.

Only certified candidates should be labelled “meets specification.” Cache results by geometry, conductor, current, temperature, fidelity version, and code commit.

### 5.4 Convergence and diversity

Fixed generation counts alone do not demonstrate Pareto convergence. Add:

- feasible hypervolume and its rolling improvement;
- epsilon or ideal/nadir movement;
- feasible fraction and topology-family coverage;
- multiple deterministic seeds and a merged nondominated archive;
- termination on stalled feasible hypervolume plus a minimum generation count;
- duplicate control and topology-aware survival.

NSGA-II is appropriate for two or three objectives and has well-defined elitist nondominated sorting [3]. If four or more objectives remain active, compare NSGA-III or reference-direction methods, but do so only after constraint normalization and benchmark correctness.

### 5.5 Robust, manufacturable Pareto fronts

A nominal 5-unit solution is not automatically manufacturable. Accelerator-magnet field quality is sensitive to conductor placement at the order of 0.1 mm; Monte Carlo geometric-error analysis is standard practice [4]. Add:

- finite-difference sensitivities of every specified harmonic to block position and angle;
- Monte Carlo cable/block placement, insulation, and assembly tolerances;
- mean, worst-case, or CVaR harmonic utilization as a certification metric;
- minimum geometric slack and sensitivity-based robustness objectives;
- a tolerance budget exported with each selected design.

This is more valuable to a designer than a nominal front containing razor-thin, numerically feasible solutions.

## 6. Critical-current and load-line model

### 6.1 What is correct

- The NbTi type-1 implementation follows the Bottura scaling relation supplied with the project. Bottura's fit is intended as a practical representation over the accelerator-magnet operating range and has finite fit uncertainty [5].
- The Nb3Sn type-11 implementation follows the CERN form shown in the supplied critical-current-fit table and is consistent with established Nb3Sn scaling-law work [6–8].
- Cable critical current correctly uses superconducting strand area, strand count, and degradation.
- The no-iron load line correctly uses linear field scaling and solves `Ic(Bpeak(I),T) = I` by bracketing/bisection.
- Per-layer margin and limiting-layer reporting are the right abstraction for graded coils.

### 6.2 Required production safeguards

- Validate temperature, field, strain, and fit-domain limits; never silently extrapolate.
- Treat the cable degradation convention explicitly: scalar cabling degradation, field/strain dependence if available, and provenance.
- Add optional Nb3Sn strain/pre-stress state. A fit without strain is acceptable only when clearly declared.
- Report both short-sample current and fraction of load line, not only `100*(1-Iop/Iss)`.
- Store peak-field location and conductor/strand identity with each margin.
- Propagate fit uncertainty into a conservative margin or uncertainty band.
- Keep self-field treatment single-counted and document whether the evaluation point is strand centre, cable boundary, or a ROXIE-equivalent convention.

The legacy script adds a scalar self-field estimate to a field already generated by all cable sources; that idea should not be copied without proving that it is not double counting.

## 7. Geometry model recommendations

The geometry layer should become a hierarchy of explicit envelopes:

```text
strand/cable metal -> bare cable -> insulated turn -> block/layer envelope -> structural clearance
```

Recommended changes:

- Define one coordinate/angle convention, with diagrams and ROXIE conversion helpers.
- Generate a turn as a rigid local-frame transform plus cable cross-section, not just four global vertices.
- Distinguish radial insulation, azimuthal insulation, wedge gap, inter-layer spacer, pole spacer, and midplane spacer.
- Model wedges as first-class optional polygons or clearance regions rather than only a generic inter-block distance.
- Use local nearest-surface distances, spatial indexing, and adjacency graphs; avoid global annular assumptions.
- Attach constraint violations to exact geometry entities and expose signed slack, not only failure messages.
- Allow a small numerical contact tolerance but never use it to waive an engineering gap.
- Add SVG/JSON export showing bare and insulated envelopes, source points, peak-field point, and constraint slack.

The optional-block representation is useful, but every layer needs a configurable minimum active block count so evolution cannot satisfy budgets by collapsing the intended topology.

## 8. Ideas worth retaining from the legacy prototype

| Legacy idea | Recommendation |
|---|---|
| Explicit targets for individual `b3`, `b5`, … | Adopt as interval constraints, with a declared reference radius |
| Conductor/strand amount objective | Adopt as conductor area, volume per metre, or cost-weighted objective |
| Staged peak-field evaluation | Adopt through the explicit screen/search/certify contract |
| Strand/two-row source visualization | Retain as a diagnostic view; validate before using it as production fidelity |
| Large population and multiobjective search | Keep configurable; use convergence evidence rather than a fixed large number |
| Current as a genome variable | Do not adopt for the linear no-iron mode; exact scaling is superior |
| Hard-coded NbTi/Nb3Sn functions | Replace fully with selected, typed `.cadata` links |
| Weighted sums of absolute target errors | Do not adopt; use normalized constraints plus Pareto objectives |
| Scalar self-field addition | Do not adopt without a no-double-counting derivation and ROXIE benchmark |

The prototype's NSGA-III choice is not inherently better than DOT's NSGA-II. Algorithm choice is secondary to correct variables, constraints, scaling, and final nondominated filtering.

## 9. Implementation roadmap

### Phase 0 — Freeze definitions and benchmarks (1–2 weeks)

1. Write the coordinate, current-sign, harmonic, margin, insulation, and `.cadata` conventions.
2. Add the CTH no-iron golden benchmark and a small analytic cos-theta/single-block benchmark.
3. Separate `aperture_radius_mm` and `r_ref_mm` everywhere.
4. Version evaluation fidelity and result schema.

**Exit criteria:** the benchmark inputs are repository-owned and reproducible; every reported quantity has units, convention, and provenance.

### Phase 1 — Correct P0 result and input defects (1–2 weeks)

1. Remove GUI harmonic double conversion.
2. Support explicit harmonics through at least `b11`.
3. Replace implicit 0.625 reference radius with an explicit setting.
4. Replace independent first-record cadata selection with linked conductor resolution.
5. Correct the `CONDUCTOR` schema and consolidate cable/insulation parsing.

**Exit criteria:** the GUI correctly recognizes the certified CTH candidate as within 5 units and at least 25% margin.

### Phase 2 — Geometry correctness (2–4 weeks)

1. Preserve per-turn keystone frames for bare and insulated geometry.
2. Replace global inter-layer radius checks with local surface clearance.
3. Classify intended contact versus forbidden overlap and introduce scale-aware tolerances.
4. Remove mandatory alpha alignment and broaden CTH-containing bounds.
5. Expose all feasibility controls and minimum block counts.

**Exit criteria:** exact CTH geometry is feasible without turn-deleting repair; deliberately perturbed collisions/gap failures are rejected with correct signed slack.

### Phase 3 — Pareto integrity and autonomous search (2–3 weeks)

1. Normalize named constraints and separate a near-feasible archive.
2. Re-evaluate at final thresholds; deduplicate and recompute rank zero.
3. Add conductor use/cost as a third objective.
4. Add feasible hypervolume termination, multi-seed campaigns, and topology diversity metrics.
5. Make screen/search/certify fidelity explicit and cacheable.

**Exit criteria:** every returned point is feasible and nondominated by assertion; repeated campaigns recover a CTH-like candidate within agreed compute budget and benchmark tolerances.

### Phase 4 — Designer workflow and robustness (3–5 weeks)

1. Add individual harmonic tables, load-line plots, layer peak maps, and constraint-slack plots.
2. Add tolerance Monte Carlo/sensitivity and robust ranking.
3. Export full campaign manifests, CSV/JSON fronts, geometry drawings, and a reproducible selected-candidate package.
4. Add comparison overlays against imported ROXIE results.

**Exit criteria:** a designer can reproduce why a candidate passed, inspect trade-offs, and quantify sensitivity without reading code.

### Phase 5 — GitHub release readiness (1–2 weeks)

1. Replace the stale README (“no physics engine yet”) with scope, validation status, quick start, screenshots, and limitations.
2. Choose a license and add contribution, citation, changelog, code-of-conduct, and security files.
3. Add CI for supported Python versions, Ruff, unit/property tests, benchmarks, and optional live-ROXIE tests.
4. Pin or lock tested dependency sets; the current global environment reports dependency conflicts.
5. Add a headless CLI/config schema and examples; do not make the GUI the only supported workflow.
6. Remove absolute-path live fixtures and provide environment-variable/skip conventions.
7. Publish a validation matrix and clearly label uncertified quantities.

**Exit criteria:** a clean clone can install, run an example, reproduce non-proprietary benchmarks, and understand the model boundary.

## 10. Recommended public API and result contract

A reusable tool should separate these stages:

```text
Catalog.load_cadata(...)
  -> ConductorSelection
GeometrySpec + ConductorSelection
  -> CoilGeometry
evaluate(Coils, OperatingSpec, Fidelity)
  -> Evaluation(B0, harmonics, peak fields, margins, slacks, provenance)
optimize(DesignSpace, EngineeringSpec, CampaignSpec)
  -> ParetoArchive(certified, search, near_feasible, history)
```

Every evaluation/result should include:

- SI value plus display unit for every quantity;
- aperture and reference radii;
- harmonic convention and all individual coefficients;
- temperature, operating current, short-sample current, peak fields/locations, margins by layer;
- conductor links and critical-surface parameters;
- geometry slack by constraint;
- source and near-field fidelity identifiers;
- random seed, campaign settings, DOT version/commit, and input hashes;
- feasibility and certification status as separate flags.

This contract makes GUI, CLI, notebooks, and future web services consumers of the same auditable domain layer.

## 11. Longer-term physics boundary

Within the declared 2D no-iron hypothesis, the next high-value calculations are conductor efficiency, forces per quadrant/block, stored energy per unit length, inductance per unit length, and tolerance sensitivity. These remain compatible with an air-core 2D engine.

Stress, quench protection, 3D ends, iron saturation, persistent-current magnetization, and coupling-current effects should be interfaces to specialized solvers or separately validated modules. Integrated magneto-mechanical optimization is state of the art [2], but implementing it is a scope expansion, not a prerequisite for an honest and useful 2D electromagnetic pre-designer. Topology/inverse Biot-Savart methods can later generate unconventional seeds, but manufacturable block parameterizations should remain the main certified path [9].

## 12. Release decision

**Current status: research prototype / not for design sign-off.**

**Eligible for an alpha GitHub release after Phases 0–2** if the README prominently states that results are limited to 2D coil-only pre-design and provides the CTH validation table.

**Eligible for a designer-facing beta after Phase 3** when returned fronts are provably feasible/nondominated and a CTH-like design is recovered autonomously in repeated campaigns.

**Eligible for engineering use only after Phase 4** with tolerance analysis, traceable certification fidelity, independent benchmark review, and documented uncertainty.

The most encouraging conclusion is that DOT does not need a wholesale physics rewrite. It needs a short correctness campaign around units, conventions, geometry, conductor linking, and Pareto integrity, followed by explicit validation and a designer-oriented result contract.

## References

1. S. Russenschuck, “ROXIE: a computer code for the integrated design of accelerator magnets,” CERN, 1999: <https://cds.cern.ch/record/382851?ln=en>
2. G. Vallone et al., “A methodology to optimize the cos-theta dipole magnet cross-section, incorporating a layer-to-layer grading,” 2022: <https://cds.cern.ch/record/2806104>
3. K. Deb et al., “A fast and elitist multiobjective genetic algorithm: NSGA-II,” *IEEE Transactions on Evolutionary Computation* 6(2), 2002: <https://doi.org/10.1109/4235.996017>
4. E. Ferracin et al., “Impact of random geometric errors on the allowed harmonics of superconducting dipole and quadrupole magnets,” CERN: <https://cds.cern.ch/record/483940/files/cer-002237717.pdf>
5. L. Bottura, “A practical fit for the critical surface of NbTi,” CERN: <https://cds.cern.ch/record/411159/files/cer-000338653.pdf>
6. A. Godeke et al., “A general scaling relation for the critical current density in Nb3Sn,” 2006: <https://www.osti.gov/servlets/purl/923445>
7. NIST, “Unified scaling law for flux pinning in practical superconductors, Part 2: parameter testing”: <https://www.nist.gov/publications/unified-scaling-law-flux-pinning-practical-superconductors-part-2-parameter-testing>
8. L. Bottura and B. Bordini, “Jc(B,T,epsilon) parameterization for the ITER Nb3Sn production,” CERN, 2009: <https://cds.cern.ch/record/1192836?ln=en>
9. D. N. Nguyen et al., “Inverse Biot-Savart optimization for superconducting accelerator magnet design,” 2021: <https://escholarship.org/uc/item/02x5z351>

### Local engineering references

- [CTH-14T electromagnetic design and conductor choice](../HFM_KE6538___D1_1__CTH_14T_Electromagnetic_design_and_conductor_choice.pdf)
- [Gupta lecture 3: superconducting magnet design](../magnet_design_course_gupta/rg-uspas06-lecture03.pdf)
- [Gupta lecture 4: field optimization](../magnet_design_course_gupta/rg-uspas06-lecture04.pdf)
- [Gupta lectures 5–7](../magnet_design_course_gupta/)
- [Real dipoles reference](../real_dipoles.pdf)
