# Antigravity independent review prompt — TASK 0021-roxie-consistent-self-field-margin

You are reviewing a diff produced by another AI worker (Codex) that
re-architects DOT's peak-field-for-margin calculation to match ROXIE's own
documented algorithm (strand-level field with an analytic self-field
term), replacing the boundary-corner-sampling approach from task 0018.
This is a significant methodology change to physics code that several
prior tasks (0018, 0019, 0020) built on top of — treat it with
correspondingly high scrutiny.

## Inputs

- `docs/ai/tasks/0021-roxie-consistent-self-field-margin/TASK.md` — read
  fully.
- Fetch `https://roxie.docs.cern.ch/user-documentation/6_analytic_field_calc.html`
  and `https://roxie.docs.cern.ch/user-documentation/5_coil_modelling.html`
  yourself — do not trust TASK.md's transcription of the self-field
  formula and N1/N2 strand-discretization convention without checking the
  source.
- The diff/commit on branch `task/0021-roxie-consistent-self-field-margin`.
- Live ROXIE REST service at `http://127.0.0.1:8080` (check reachability
  first).

## What to check

1. **Source documentation accuracy.** Confirm the self-field formula
   (`I_strand / (2*pi*r_strand)`) and the N1/N2 strand-discretization
   convention are correctly transcribed from the actual CERN docs.
2. **Comparison methodology fix.** Confirm the diff actually compares
   DOT vs ROXIE per-conductor (matched by position/index), not by
   independently selecting each side's own worst value — this was the
   original bug that motivated this task. If Codex's tests still compare
   aggregated worst-vs-worst without also including a genuine per-conductor
   comparison, that's a significant gap.
3. **Physical correctness of the self-field decomposition.** Check that
   the "external field" computation genuinely excludes the evaluated
   strand's own source (not just uses a large-but-finite distance), and
   that the self-field addback uses the real strand radius and real
   per-strand current (`turn.current_a / cable.n_strands`), not a
   per-filament current using an arbitrary discretization count.
4. **n1/n2 choice.** Confirm `n1=2, n2=cable.n_strands/2` is used (matching
   real Rutherford cable construction and the real strand counts verified
   in TASK.md: CTH_HF=40, CTH_LF=30), not an arbitrary large number.
5. **Live ROXIE validation — run it yourself, per conductor.** Construct
   your own case(s) and extract ROXIE's own `PEAK FIELD IN CONDUCTOR N`
   values for each individual conductor, comparing against DOT's
   corresponding per-conductor value — not just the block/design-level
   worst number.
6. **No regression** on tasks 0018/0019/0020's already-validated
   aggregated worst-case numbers.
7. **Scope discipline.** No changes to `src/dot/geometry/*` or the
   bore-field code path.

## Output format

Findings ranked most-severe first — a physically wrong self-field
decomposition, or a review that still only compares aggregated
worst-vs-worst without genuine per-conductor matching, are the most severe
possible findings here (the second because it would mean the very bug that
motivated this task was never actually verified as fixed). For each: file,
line, what's wrong, concrete consequence. End with:

- **APPROVE**
- **APPROVE WITH NITS**
- **REJECT** — must not merge; list exactly what must change and why.

Do not approve based on reported numbers alone — fetch the source
documentation yourself, hand-derive at least one case independently, and
run your own live ROXIE per-conductor checks before approving.
