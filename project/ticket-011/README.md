# Ticket 011: Align pyproject version 1.0.51 and add errors runbook index

- **ID**: ticket-011
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-18

SESSION_EXECUTION_AUTHORIZATION: Authorized by user in active session to align pyproject.toml version with PyPI 1.0.51 and satisfy wellmanifest/logs check.

## Goal and scope

Align `pyproject.toml` `[project].version` to `1.0.51` (matching PyPI) and add `errors/README.md` runbook index per `wellmanifest/logs`.

## Acceptance criteria

- [x] AC-01: `pyproject.toml` version is `1.0.51` and `errors/README.md` passes `wellman check --root .` with 0 errors.
- [x] AC-02: `./project/governance-check.sh` passes with 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
