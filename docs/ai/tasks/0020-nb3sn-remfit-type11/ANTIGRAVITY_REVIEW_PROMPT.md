# Antigravity independent review prompt — TASK 0020-nb3sn-remfit-type11

You are reviewing a diff produced by another AI worker (Codex) adding a new
critical-current fit (REMFIT type 11, Nb3Sn, CERN/Bordini parametrization)
to DOT, alongside the existing type-1 Bottura Nb-Ti fit. This is genuinely
new physics code with no prior implementation to compare against — the
correctness bar rests entirely on (a) independently re-reading the source
formula image and (b) live ROXIE validation, since there was no previous
DOT-computed CTH_HF margin number to regress against.

## Inputs

- `docs/ai/tasks/0020-nb3sn-remfit-type11/TASK.md` — read fully.
- `C:\Users\elisei\Desktop\DOT\critical_current_density_fits.png` — the
  primary source. Read this image yourself; do not trust TASK.md's
  transcription without checking it against the image directly.
- The diff/commit on branch `task/0020-nb3sn-remfit-type11`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Formula transcription correctness.** Read the REMFIT type-11 formula
   directly from the image yourself (crop/zoom if needed) and confirm it
   matches what's implemented — this is the first line of defense against
   a subtly wrong physics formula.
2. **Column mapping correctness.** Independently verify the `C1..C7 ->
   C0, Bc20, Tc0, alpha, v, p, q` mapping against the real REMFIT rows in
   `roxie_CTH_cables.cadata` (`PIT192`, `MQXFS5`, `HFM1`) — check the
   physical plausibility of each value (Bc20 for Nb3Sn is typically
   ~28-31T, Tc0 ~16-18K) independently, don't just accept the diff's
   reasoning.
3. **Hand-derivation.** Compute `Jc(B,T)` by hand for at least one
   `(B,T)` point using `HFM1`'s coefficients (pick a different point than
   whatever Codex used, if possible) and compare against the
   implementation.
4. **Live ROXIE validation — run it yourself.** This is the critical check
   since there's no prior baseline. Submit your own live ROXIE jobs for at
   least 1 CTH_HF-only case and 1 mixed CTH_HF+CTH_LF case (construct your
   own, don't just reproduce Codex's). Compare peak field and load-line
   margin against ROXIE's own reported numbers.
5. **No regression on CTH_LF (type-1/Bottura).** Run the existing CTH_LF
   margin tests from tasks 0018/0019 yourself and confirm unchanged
   numbers.
6. **Dispatch cleanliness.** Check how `load_line_margin_objective` and
   `loadline.py` distinguish type-1 vs type-11 coefficients — flag if it's
   done via fragile string-matching on REMFIT names rather than the
   coefficient type itself.
7. **Scope discipline.** Only declared files touched? Bottura (type-1)
   code path unmodified?

## Output format

Findings ranked most-severe first — a wrong physics formula (silently
producing incorrect Jc/margin values) is the most severe possible finding
here, more severe even than a geometry regression, since there's no
existing test coverage to catch it other than this review. For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — re-read the source image
yourself, hand-derive at least one independent case, and run your own live
ROXIE checks for both a CTH_HF-only and a mixed-cable case before
approving.
