# TASK: <short title>

- **ID**: NNNN-<slug>
- **Status**: draft | ready | in-progress | review | done | rejected
- **Model/effort**: <coordinator's chosen effort level for Codex + Antigravity, and why>
- **Worktree**: .worktrees/<task-slug> (branch task/<task-slug>)

## Goal

<One paragraph: what should exist after this task that doesn't exist now.>

## Scope (files/modules Codex may touch)

- <path/glob>
- <path/glob>

## Explicit non-goals

- <thing that must NOT be done in this task, even if tempting/related>

## Reference material (read-only, do not copy)

- <e.g. C:\Users\elisei\Desktop\dipole_designer\... — what to learn from it>
- <e.g. C:\Users\elisei\Desktop\dipole-optimization-tool\... — what to learn from it>

## Acceptance criteria

- [ ] <concrete, testable condition>
- [ ] `ruff check` clean on changed files
- [ ] `pytest` passes, including new tests covering this change
- [ ] No files outside declared scope were modified

## Notes / open questions

<anything the coordinator is unsure about; flag for user if it blocks scoping>
