# Independent final publication audit request for DOT

Act as the final independent release auditor for the DOT repository in the current working
directory. Review the complete **staged** publication tree; do not limit yourself to the last few
files and do not trust prior reports without checking the source.

This follows your initial `READY AFTER FIXES` audit. The initial findings were handled as follows:

1. Every README-linked publication document, benchmark, source file, test, launcher, and metadata
   file is now staged for the prospective local commit.
2. `docs/ai/` is intentionally retained as transparent provenance. Its README now prominently
   labels it a historical archive whose old prompts are not current product requirements.
3. Independent local dynamic verification passed: 234 tests passed and 13 environment-gated tests
   skipped; Ruff and `git diff --check` passed. A wheel was built, installed into a clean Python 3.11
   venv, imported, and used for all three `dot validate` benchmark commands plus a quick headless
   optimization. `pip check` and `pip-audit` passed with no known vulnerabilities.
4. A fresh live ROXIE comparison was run on 2026-07-18. Its numerical evidence and environment
   boundary are recorded in `docs/reviews/ROXIE_PARITY_2026-07-18.md`.
5. The project now carries the MIT License and credits Mattia Elisei, INFN Milan and University of
   Rome La Sapienza. Nothing is to be published or pushed in this audit.

Product boundaries to enforce:

- 2D, coil-only/air-core calculations; no iron and no 3D ends.
- Layer 1 radius equals aperture radius, with no Layer-1 radial-gap input.
- The untrusted post-NSGA-II refinement stage is removed.
- Normal harmonics support signed targets; residuals are `abs(b_n - target_n)`.
- Live ROXIE tests are intentionally license-gated and must skip cleanly without proprietary tools.

Inspect staged source, tests, benchmark provenance, packaging, GUI/CLI behavior, launchers, CI,
documentation, and git hygiene. Focus on release-blocking correctness, resilience, physics errors,
misleading certification, proprietary leakage, missing staged files, and regressions introduced by
the final fixes. You may use read-only inspection commands. Do not edit files, write a report file,
spawn/delegate to another agent, create a commit, or publish anything.

Return a concise Markdown report directly with:

- final verdict: `READY`, `READY AFTER FIXES`, or `NOT READY`;
- any blockers/high findings first, with exact file and line references and reproducible evidence;
- confirmation or rejection of each of the five closure items above;
- remaining medium/low limitations that are honest release notes rather than blockers;
- a one-sentence conclusion stating whether this exact staged tree may be committed locally as the
  GitHub-ready DOT 0.1.0 candidate.
