# DOT AI Orchestration

DOT (Dipole Optimization Tool) is developed using a coordinator/worker/reviewer
pipeline. This document defines the workflow. Read it before starting or
reviewing any task.

## Roles

- **Coordinator (Claude, this session)** — plans work, writes task specs and
  prompts, creates isolated git worktrees, runs the final gate (pytest/ruff/
  regression tests), reads the reviewer's verdict, and decides whether to
  merge. The coordinator does not write production code directly except in
  narrow cases (docs, scaffolding, config) explicitly called out as such.
- **Codex CLI (implementation worker)** — runs inside an isolated git
  worktree, receives a `CODEX_PROMPT.md`, and implements exactly what is
  scoped in the paired `TASK.md`. Nothing more.
- **Antigravity CLI (independent reviewer)** — runs against the same
  worktree/diff *after* Codex is done, with no visibility into Codex's
  reasoning, only the diff and `ANTIGRAVITY_REVIEW_PROMPT.md`. Produces an
  independent pass/fail judgment plus findings.
- **Gate (pytest / ruff / regression tests)** — objective, automated,
  non-negotiable. A task cannot be merged if the gate fails, regardless of
  what Codex or Antigravity say.

## Directory layout

```
docs/ai/
  README.md                              this file
  TASK_TEMPLATE.md                        template for a new task spec
  CODEX_PROMPT_TEMPLATE.md                template for the worker prompt
  ANTIGRAVITY_REVIEW_PROMPT_TEMPLATE.md   template for the reviewer prompt
  FINAL_VERDICT_TEMPLATE.md               template for the merge decision
  tasks/
    0001-<slug>/
      TASK.md
      CODEX_PROMPT.md
      ANTIGRAVITY_REVIEW_PROMPT.md
      FINAL_VERDICT.md
    0002-<slug>/
      ...
```

Each task gets its own numbered folder under `tasks/`. Task folders are
append-only history — once `FINAL_VERDICT.md` is filled in, the folder is not
edited again.

## Workflow (per task)

1. **Scope.** Coordinator writes `TASK.md`: goal, exact file/module
   boundaries, explicit non-goals, acceptance criteria (tests that must pass),
   and links to any reference material (e.g. specific files in
   `dipole_designer` or `dipole-optimization-tool` to consult, never to copy
   wholesale — see "Provenance" below).
2. **Isolate.** Coordinator creates a git worktree on a new branch
   (`git worktree add .worktrees/<task-slug> -b task/<task-slug>`). All
   worker changes happen only inside that worktree.
3. **Implement.** Coordinator hands `CODEX_PROMPT.md` + `TASK.md` to Codex
   CLI, invoked with its working directory set to the worktree. Codex may
   only touch files inside its declared scope.
4. **Independent review.** Coordinator hands the resulting diff +
   `ANTIGRAVITY_REVIEW_PROMPT.md` to Antigravity CLI. Antigravity does not see
   Codex's chat transcript — only the diff, the original `TASK.md`, and the
   repository. It reports correctness bugs, scope creep, missed acceptance
   criteria, and physics/geometry concerns explicitly.
5. **Gate.** Coordinator runs `ruff check`, `ruff format --check`, and
   `pytest` (including any regression fixtures) inside the worktree.
6. **Verdict.** Coordinator writes `FINAL_VERDICT.md`: summarizes Codex's
   output, Antigravity's findings, gate results, and a merge/reject/rework
   decision. **Merging into `main` always requires explicit user
   confirmation** — the coordinator never merges autonomously.
7. **Cleanup.** On merge or reject, the worktree is removed
   (`git worktree remove`). Rework loops back to step 3 with an updated
   `CODEX_PROMPT.md` addressing the findings.

## Provenance rule

DOT must not link against, vendor, or literally copy code from
`dipole_designer` (ROXIE-coupled) or from `dipole-optimization-tool` (the
distrusted prior attempt). Both may be *read* for reference (algorithms,
constraint definitions, file formats, lessons learned) but every line landing
in DOT is freshly written and reviewed. Task specs must call out which
reference material, if any, was consulted, so provenance stays auditable.

## Model/effort discipline

Not every task needs the most expensive model on every role:

- Small, mechanical, well-scoped tasks (boilerplate, config, docs) → cheaper/
  faster models for both worker and reviewer.
- Physics engine, geometry constraints, and optimizer core → the strongest
  available model for both Codex and Antigravity, since correctness bugs
  here are expensive (infeasible magnet designs, silently wrong field
  quality).
- The coordinator should state the chosen effort level and why in `TASK.md`.

## Non-negotiables (current phase)

- No production code is modified without a `TASK.md` behind it.
- No merges happen without explicit user approval.
- Any command that would touch files outside this repository requires asking
  the user first.
- Geometric feasibility constraints are treated as safety-critical: any task
  touching them requires the highest review rigor and explicit regression
  tests before merge.
