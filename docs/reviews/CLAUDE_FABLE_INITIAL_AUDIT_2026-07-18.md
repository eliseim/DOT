# Independent Pre-Publication Review — DOT

**Reviewer:** Claude Fable (independent, read-only pass)
**Date:** 2026-07-18
**Verdict:** **READY AFTER FIXES**

Scope note: this was a static review (file/diff/content inspection). Fable was unable to execute
`pytest`/`ruff` in its sandbox session because Bash tool calls to Python were blocked, so no dynamic
test/lint verification was performed by Fable. DOT's own verification is recorded separately.

## Release blockers

1. **README links to files that are not tracked in git.** `README.md` cites
   `docs/DOT_IMPLEMENTATION_REPORT.md`, `docs/DOT_TECHNICAL_REVIEW_AND_IMPLEMENTATION_GUIDE.md`,
   `docs/PERFORMANCE.md`, and `docs/reviews/ROXIE_PARITY_2026-07-18.md`. These existed only in the
   working tree during the audit. Fable's correction: stage them in the publication commit or remove
   the links.

## High-priority findings

2. **`docs/ai/` is a tracked internal AI-agent development trail.** It contains task prompts and
   review verdicts. This is not a correctness bug, but Fable recommends making an explicit decision
   whether its transparency value outweighs repository noise.

3. **Dynamic verification was unconfirmed by Fable.** Given the large physics, geometry, optimizer,
   and GUI diff, Fable requires a fresh test and lint pass before publication.

## Checks that passed

- No leaked secrets or personal paths were found in `src/`.
- Removal of `refinement.py` and its tests is internally consistent; stale configuration is rejected
  with a migration error and the changelog documents removal.
- README LHC MB benchmark values exactly match the certified result JSON.
- CI benchmark paths exist for all three included benchmarks.
- Cadata benchmark fixtures are minimal rather than full proprietary catalogues; no PDFs or other
  clearly proprietary reference documents are tracked.
- The documented CLI entry points exist.
- ROXIE parity report tolerances match the live test assertions.
- The harmonic convention is documented consistently as CERN/European units.
- Packaging metadata, `py.typed`, license metadata, and the Python CI matrix are coherent.

## Fable's verification matrix before tagging

| Item | Fable status |
|---|---|
| `pytest -q -m "not slow and not live_roxie"` | Not run by Fable — must run before release |
| `ruff check src tests` | Not run by Fable — must run before release |
| README-linked publication documents staged | Not yet — blocker 1 |
| Decision on publishing `docs/ai/` | Open — finding 2 |
| Fresh live ROXIE parity | Optional; fresh evidence dated 2026-07-18 exists |

## Bottom line

Fable reported no electromagnetic or geometry correctness red flags in the areas it statically
checked. Its blocking issue was git hygiene: include the referenced documents in the commit, run
tests and lint, and make an explicit decision about the historical `docs/ai/` development trail.

> This file preserves Fable's substantive report. Formatting was normalized for the repository;
> no finding or verdict was changed.
