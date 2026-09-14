# ticket-004: Remove pfix auto-repair from the project

- **Status**: IN_PROGRESS
- **Workflow state**: EDIT

SESSION_EXECUTION_AUTHORIZATION: on 2026-09-13 the user requested that pfix be
removed from Semcod projects or deactivated, because its automatic repairs
overwrite development changes.

AC-01: No tracked `pyproject.toml` declares a `[tool.pfix]` table or a `pfix`
requirement (runtime, optional, group or tool environment).
AC-02: The parsed TOML differs from the base only by the removed pfix entries.
AC-03: A tracked `uv.lock` is regenerated so it no longer records a direct pfix
requirement of this project.
AC-04: Source code, tests and generated documentation projections are unchanged.

Canonical fleet evidence:
`subactor/docs/architecture/analysis/semcod-library-quality.md`.
This ticket does not establish full new-project adoption.
