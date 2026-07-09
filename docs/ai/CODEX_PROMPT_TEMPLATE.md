# Codex worker prompt — TASK NNNN-<slug>

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read `docs/ai/TASK.md` in this
worktree (or the sibling `docs/ai/tasks/NNNN-<slug>/TASK.md`) fully before
writing any code.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md. If you believe a file
   outside that scope must change, stop and report why instead of editing it.
2. Do not import, vendor, or copy code from `dipole_designer` or
   `dipole-optimization-tool`. You may read them (paths given in TASK.md's
   "Reference material") for algorithmic/domain understanding only.
3. No ROXIE dependency, ever, anywhere in DOT's runtime path.
4. Follow the acceptance criteria in TASK.md exactly. Do not add unrelated
   improvements, refactors, or "while I'm here" changes.
5. Write tests for what you implement. Run `pytest` and `ruff check` yourself
   before declaring the task done; report the exact commands and their
   output.
6. If a geometric/physics constraint is involved, state explicitly which
   invariant it enforces and how your test proves it.
7. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope, plus a short summary: what changed,
what you tested, what you deliberately left out (and why, if relevant to
scope discipline).

## Task-specific instructions

<paste the specific implementation instructions for this task here>
