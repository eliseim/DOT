# Claude Fable GUI review — DOT 0.1.1

**Date:** 2026-07-19

Claude Fable reviewed the uncommitted GUI terminology/layout update in a read-only foreground
session. Its command sandbox did not permit Python/test execution, so the independent review was
static; DOT's dynamic verification was run separately.

## Review conclusion

Fable found the change careful and mostly self-consistent. It confirmed that:

- legacy `roxie` and pre-v2 `dot-pole-zero` configuration values remain loadable and migrate to
  DOT's neutral `native-midplane-zero` convention;
- the angle conversion mathematics was not changed;
- GUI labels, CSV headers, README artifact names, CLI messages, tooltips, and summary-image titles
  were updated consistently;
- internal compatibility names, cadata-format handling, and independent parity tests should remain
  because they are validation/compatibility mechanisms rather than GUI branding.

## Findings and disposition

1. **Generated JSON still exposed `roxie_block`. — Implemented.** Final-candidate, Pareto,
   headless-run, and generation-snapshot documents now use continuous `block` plus
   `block_in_layer`. Their schema versions were advanced where applicable. Regression tests assert
   that the new designer-facing candidate and generation documents contain no `roxie` string.
2. **Load-before-Save differs from the old bottom-row order. — Not implemented.** The new toolbar
   intentionally follows the conventional Open/Load-then-Save ordering. Preserving muscle memory
   from the superseded bottom action row was not judged more important than the requested standard
   desktop layout.

No release blocker, physics change, or optimization regression was identified by the review.

## Closure review

After the JSON/schema correction and full local verification, Fable performed a second read-only
inspection and returned **READY**. It confirmed the neutral fields and schema revisions in final,
Pareto, headless, and generation outputs; the neutral CSV names/headers; preservation of legacy
configuration tokens and parity tests; the requested window title/top toolbar/table headings; and
the absence of a new blocker.
