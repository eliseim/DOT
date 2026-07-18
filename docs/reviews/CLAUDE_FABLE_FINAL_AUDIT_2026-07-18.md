# Claude Fable final publication audit — DOT

**Reviewer:** Claude Fable (independent, read-only pass)
**Date:** 2026-07-18
**Fable verdict:** **READY AFTER FIXES** — no blockers or high-priority findings; two cosmetic
findings only.

Fable inspected the complete staged publication tree. Its sandbox again prevented Python, pytest,
Ruff, and pip-audit execution, so the independent model review was static; the dynamic evidence was
run separately by DOT's release gate and is summarized below.

## Findings and disposition

1. **Mojibake at `docs/DOT_IMPLEMENTATION_REPORT.md:147`.** A code-point inspection reproduced the
   double-decoded dash sequence. It was replaced with the portable ASCII range `0.065-0.481%`.
2. **Extra blank line at EOF in `src/dot/campaign.py`.** Reproduced with
   `git diff --check --cached` and removed. This was cosmetic and had no runtime effect.
3. **Closure scan found two adjacent instances of the same mojibake.** The remaining report ranges
   were changed to portable ASCII (`0.064-1.182%` and `0.017-0.334`), and the tracked text tree was
   scanned for the double-decoded sequence before commit.

## Closure of the initial audit

Fable confirmed all of the following:

- all README-linked publication documents and benchmark/source/test/launcher files are staged;
- `docs/ai/` is deliberately retained and prominently labeled as a historical provenance archive;
- the fresh 2026-07-18 live ROXIE parity report is present and its reported values satisfy its
  declared tolerances;
- MIT licensing and Mattia Elisei / INFN Milan / University of Rome La Sapienza attribution are
  consistent across release metadata;
- README LHC MB numerical claims match the certified benchmark artifacts;
- no proprietary PDF, untracked file, personal source path, secret, or refinement-code inconsistency
  was found;
- CLI behavior and documented model limitations are coherent and honestly scoped.

Fable classified the disclosed absence of iron, 3D ends, mechanics, and quench modeling—and the
absence of committed CTH/FalconD convergence certificates—as honest release limitations rather
than blockers.

## Independent dynamic release gate

Run outside Fable's restricted command sandbox against this release candidate:

- pytest: **234 passed, 13 skipped** (Tk/display and licensed live-ROXIE environment gates);
- Ruff: passed;
- wheel build and clean Python 3.11 installation: passed;
- `pip check`: passed;
- `pip-audit`: no known vulnerabilities;
- all three packaged benchmark schemas: passed `dot validate`;
- clean-wheel `dot optimize --quick`: completed and wrote an honestly labeled archive;
- live ROXIE parity: 11/11 service cases plus 5/5 stored CTH harmonic cases passed.

## Conclusion

Fable found no blocker or high-priority defect. After reproducing and fixing its cosmetic findings,
the candidate satisfies the conditions in Fable's conclusion for a local GitHub-ready DOT 0.1.0
commit.

## Post-fix closure seal

Fable then inspected the corrected staged blobs and returned **READY**. It confirmed all three report
ranges are plain ASCII, `campaign.py` has exactly one terminal newline, the cached diff check is
clean, the index has no unstaged or untracked files, and a staged-text scan contains none of the
double-decoded or replacement-character patterns it searched for. Its final conclusion was that the
exact staged tree may be committed locally as DOT 0.1.0.
