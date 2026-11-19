# Ticket 015: Align logic2code, logic2test and lolm versions with their pyproject

- **ID**: ticket-015
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-18

## Goal and scope

Fixes semcod/code2logic#20. `logic2code`, `logic2test` and `lolm` all declared `__version__ = "1.0.51"`
while their `pyproject.toml` declare 0.1.9, 0.1.10 and 0.1.10. The new-project 0.20.162 gate reports
GOV-VERSION-001 for each and blocks the fleet standard adoption. The installed gate (0.20.92) instead
requires these literals to equal the root `VERSION` (1.0.51), so no literal satisfies both. Replace
the literals with dynamic version discovery (installed distribution metadata, falling back to the
sibling `pyproject.toml` in a source checkout), as both gates' remediation recommends.

## Acceptance criteria

- [ ] AC-01: The current gate passes and `wellman-governance check` (0.20.162 runtime) reports no GOV-VERSION-001; each package resolves its pyproject version.
- [ ] AC-02: `project/governance-check.sh` passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
