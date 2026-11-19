# Ticket 016: Adopt new-project 0.20.162

- **ID**: ticket-016
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-19

## Goal and scope

Fleet update to wellmanifest/new-project 0.20.162 (from 0.20.92). The release inventories every
managed `.governance/docs/**` copy for the docs checker, stops `baseline` demanding unprovable S3 levels, ignores
adoption tickets that already landed, and admits requested carrier-only follow-up commits. Standard records are
rebuilt from verifiable evidence in `audit` mode.

## Acceptance criteria

- [ ] AC-1: Goal reports the target up-to-date at 0.20.162.
- [ ] AC-2: `project/governance-check.sh` passes.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
