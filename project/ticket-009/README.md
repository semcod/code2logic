# Ticket 009: Fix check_performance_issues regex and AST loop detection

- **ID**: ticket-009
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-16

## Goal and scope

Fix `check_performance_issues` in `code2logic/code_review.py` so regex patterns (such as `for.*in.*:`) are evaluated with `re.search` instead of literal substring checks, and inspect Python AST loop context to detect N+1 queries, subprocess calls in loops, and uncached YAML/AST parsing in loops.

## Acceptance criteria

- [x] AC-01: Update `code2logic/code_review.py` to support regex pattern matching and AST loop inspection for N+1 queries, subprocesses in loops, and uncached parsing in loops.
- [x] AC-02: Add unit tests in `tests/test_code_review.py`.
- [x] AC-03: Governance check (`./project/governance-check.sh`) and test suite pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
