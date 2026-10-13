# Ticket 006: Add code2logic path to application workstream in governance manifest

- **ID**: ticket-006
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-13

## Goal and scope

Add `code2logic/**` to the `application` workstream ownedPaths in `.governance/manifest.json` so that application files in `code2logic/` can be allocated under the application workstream.

## Acceptance criteria

- [x] AC-01: `code2logic/**` is declared under `coordination.workstreams.application.ownedPaths`.
- [x] AC-02: Governance check passes cleanly.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
