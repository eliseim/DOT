# Codex worker prompt — TASK 0001-bootstrap-skeleton

You are implementing a single scoped task inside an isolated git worktree for
the DOT (Dipole Optimization Tool) project. Read
`docs/ai/tasks/0001-bootstrap-skeleton/TASK.md` in this worktree fully before
writing any code.

## Hard rules

1. Only touch files listed under "Scope" in TASK.md. If you believe a file
   outside that scope must change, stop and report why instead of editing it.
2. Do not import, vendor, or copy code from `dipole_designer` or
   `dipole-optimization-tool`. You may read them (paths given in TASK.md's
   "Reference material") for structural/tooling reference only.
3. No ROXIE dependency, ever, anywhere in DOT's runtime path.
4. Follow the acceptance criteria in TASK.md exactly. Do not add unrelated
   improvements, refactors, or "while I'm here" changes. In particular: do
   NOT add pymoo, PySide6, matplotlib, shapely, or any GUI/optimizer/physics
   code in this task — that is explicitly out of scope.
5. Write the smoke test specified in TASK.md. Run `pytest` and `ruff check`
   yourself before declaring the task done; report the exact commands and
   their output.
6. Do not modify git history, do not force-push, do not touch files outside
   this repository.

## Deliverable

A diff limited to the declared scope, plus a short summary: what changed,
what you tested (paste command output), and confirmation that no
optimizer/physics/GUI/ROXIE code was introduced.

## Task-specific instructions

Implement exactly what `docs/ai/tasks/0001-bootstrap-skeleton/TASK.md`
describes:

1. `pyproject.toml`: package name `dot`, `src/`-layout
   (`[tool.setuptools.packages.find] where = ["src"]` or equivalent for your
   build backend of choice — prefer `hatchling` or `setuptools`, either is
   fine, pick one and be consistent), Python `>=3.11`, runtime dependency
   `numpy`, dev dependencies `pytest` and `ruff` under an optional/dependency
   group, and a `[tool.ruff]` section with a reasonable line-length (e.g. 100)
   and default rule set.
2. `src/dot/__init__.py` containing only `__version__ = "0.0.1"`.
3. `src/dot/py.typed` — empty file (PEP 561 marker).
4. `tests/__init__.py` — empty.
5. `tests/test_package.py` — one test importing `dot` and asserting
   `dot.__version__ == "0.0.1"`.
6. Root `README.md` — short: one paragraph describing DOT as a tool for
   designing the 2D no-iron cross-section of a superconducting dipole magnet
   without depending on ROXIE, current status "early scaffolding, no physics
   engine yet", and a link to `docs/ai/README.md` for the AI-assisted dev
   workflow.

After writing the files, actually run (report output):
- `python -m pip install -e .` (or `pip install -e .`) in a clean/fresh
  environment if possible, or at minimum verify the package metadata is
  syntactically valid.
- `ruff check .`
- `pytest -q`
