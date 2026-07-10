# Outcome: not merged

**Status: closed without merging.** The branch
`task/0021-roxie-consistent-self-field-margin` (commits `e89f385` through
`290eb1d`) implements ROXIE's documented strand-level self-field algorithm
(`B_self = mu0 * I_strand / (2*pi*r_strand)`, added to the external field
from all other strands, evaluated at each strand's own position) but does
**not** improve on task 0018's simpler boundary-corner-sampling method —
it is materially worse on every tested case:

| Case | Task 0021 (strand self-field) | Task 0018 (boundary-corner, already merged) |
|---|---|---|
| `cth_hf_single_turn_r34_phi36` | 7.33% peak field error | 0.19% |
| `cth_lf_three_turn_r42_phi48` | 3.32% peak field error | 0.20% |
| `cth_hf_lf_mixed_two_layer` | 5.63% peak field error | 0.20% |

## What was ruled out across three debugging rounds

1. An initial implementation included an unexplained `0.75` self-field
   scaling factor with no basis in the documented formula — removed.
2. A subsequent `n1`/`n2` strand-grid-orientation swap, based on incorrect
   coordinator feedback, was identified and reverted. The corrected
   orientation (`n1` = broad/many-strands direction, `n2` = 2-strand
   thickness direction) was confirmed structurally correct for a standard
   2-strand-thick Rutherford cable — this is a manufacturing-convention
   fact independent of any cable-dimension arithmetic (cable compaction
   during manufacturing means outer cable width is not reliably
   `2 * strand_diameter`, so that arithmetic should not be used as a
   geometry sanity check either way).
3. A vector-vs-scalar combination hypothesis for the self-field term was
   tested and found to be mathematically vacuous for this formula (the
   proposed "vector" self-field is constructed parallel to the external
   field, so it algebraically collapses to the same scalar sum) — ruled
   out, not the source of the gap.

With geometry, the scaling factor, and the combination method all ruled
out or corrected, the ~7% single-turn residual is unexplained. The
`I_strand / (2*pi*r_strand)` self-field magnitude, taken at face value
from the documented formula and real cadata strand/cable records, appears
too large relative to what ROXIE actually reports for these cases. Closing
this gap would likely require either ROXIE's own source code/internal
documentation beyond what's publicly available, or a different
strand-current/geometry convention than the one derivable from the public
CERN ROXIE user documentation.

## Decision

Task 0018's boundary-corner-sampling method remains DOT's production
peak-field/margin implementation. This branch is preserved (not deleted)
for reference in case future work (e.g. access to more detailed ROXIE
internals, or a literature-sourced correction to the self-field
convention) makes it worth revisiting, but should not be merged as-is.
