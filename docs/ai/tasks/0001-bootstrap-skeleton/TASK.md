# TASK: Bootstrap DOT package skeleton

- **ID**: 0001-bootstrap-skeleton
- **Status**: draft
- **Model/effort**: Low/medium effort for both Codex and Antigravity. This
  task is pure scaffolding — no physics, no geometry, no optimization logic.
  Mistakes here are cheap to catch and cheap to redo, so there is no reason
  to spend top-tier model budget on it. Reserve the strongest models for the
  physics engine and geometric constraint tasks that come later.
- **Worktree**: .worktrees/0001-bootstrap-skeleton (branch task/0001-bootstrap-skeleton)

## Goal

Create the initial installable Python package skeleton for DOT, with no
domain logic yet — just structure, tooling config, and a smoke test — so
that subsequent tasks (physics engine, geometry model, optimizer, GUI) have
a consistent place to land and CI/lint/test tooling already works.

DOT's ultimate purpose (for context, not to be implemented in this task):
reproduce `dipole_designer`'s `target_synthesis_gui` workflow — given target
bore field, field quality (harmonics), load-line margin, and cable type,
search for a feasible 2D no-iron dipole coil cross-section — using a native
physics engine instead of calling ROXIE.

## Scope (files/modules Codex may touch)

- `pyproject.toml`
- `src/dot/__init__.py` (package version string only, e.g. `__version__ = "0.0.1"`)
- `src/dot/py.typed` (empty marker file)
- `tests/__init__.py`
- `tests/test_package.py` (smoke test: `import dot; assert dot.__version__`)
- `.gitignore` (already exists at repo root — only touch if genuinely
  missing an entry needed for this task, and say so explicitly)
- `README.md` (repo root — short: what DOT is, one paragraph, current status
  "early scaffolding", link to `docs/ai/README.md` for the dev workflow)

## Explicit non-goals

- No physics/electromagnetics code.
- No geometry/constraint code.
- No optimizer code.
- No GUI code.
- No ROXIE-related code or dependencies, ever.
- No CI workflow files (GitHub Actions) — a later task.
- Do not add `pymoo`, `PySide6`, `matplotlib`, `shapely`, or any other heavy
  dependency yet. This task only needs `numpy`, `pytest`, and `ruff` as dev
  tooling.

## Reference material (read-only, do not copy)

- `C:\Users\elisei\Desktop\dipole-optimization-tool\pyproject.toml` and its
  `src/dipole_opt/` layout — for a sense of a reasonable `src/`-layout
  package structure and Python version floor (3.11+). Do not copy its
  content; DOT's package name is `dot`, not `dipole_opt`.
- `C:\Users\elisei\Desktop\dipole_designer\pyproject.toml` — for comparison
  of dependency floors only.

## Acceptance criteria

- [ ] `pip install -e .` (or `python -m pip install -e .`) succeeds in a
      clean virtualenv.
- [ ] `python -c "import dot; print(dot.__version__)"` prints `0.0.1`.
- [ ] `ruff check .` is clean.
- [ ] `pytest -q` passes (at least the one smoke test).
- [ ] No files outside declared scope were modified.
- [ ] Package name is `dot`, importable as `import dot`, `src/`-layout.
- [ ] `pyproject.toml` declares: Python `>=3.11`, `numpy` as a runtime dep,
      `pytest` and `ruff` under a `[project.optional-dependencies.dev]` (or
      `[dependency-groups.dev]`) group. `[tool.ruff]` config included.

## Notes / open questions

- Package/import name chosen as `dot` (lowercase) to match the project name
  DOT (Dipole Optimization Tool) while avoiding collision with common
  meanings — coordinator judgment call; flag to user if this should instead
  be e.g. `dipole_opt_tool` or similar before task 0002 builds on top of it.
