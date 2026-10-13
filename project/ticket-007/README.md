# Ticket 007: Support exclude patterns and directory pruning in code2logic

- **ID**: ticket-007
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Support custom `--exclude` patterns in CLI and `ProjectAnalyzer`, expand default `IGNORE_DIRS` to prune `.subactor`, `.worktrees`, `.planfile`, `.benchmarks`, `managed_components`, and `workshop`, and filter ignored directories and excluded paths during both git file listing and directory walking.

## Acceptance criteria

- [x] AC-01: Add `.subactor`, `.worktrees`, `.planfile`, `.benchmarks`, `managed_components`, and `workshop` to default `IGNORE_DIRS`.
- [x] AC-02: Support `--exclude` / `-e` CLI option in `code2logic` and `exclude` parameter in `ProjectAnalyzer`.
- [x] AC-03: Filter excluded paths and ignored directories in `_scan_files`.
- [x] AC-04: Full test suite passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
