# Ticket 008: Fix hardcoded docstring path in terminal.py

- **ID**: ticket-008
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Eliminate hardcoded `/home/tom` user path in `code2logic/terminal.py` in accordance with `wellmanifest/nohardcode` (`NOHARDCODE-009`).

## Acceptance criteria

- [x] AC-01: Replace hardcoded absolute user home path in `code2logic/terminal.py` with relative contract reference.
- [x] AC-02: Governance check passes (`GOV-PASS`).
- [x] AC-03: Test suite passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
