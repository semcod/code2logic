# Ticket 013: Export CFG and DFG fingerprints for semantic retrieval candidates

- **ID**: ticket-013
- **Owner**: agent:antigravity (SESSION_EXECUTION_AUTHORIZATION)
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-10-27

## Goal and scope

Implement read-only structural IR export (`code2logic.structural_fingerprint/v1` and `code2logic.structural_export/v1`) for semantic retrieval candidates (`PLF-006`, Issue #9).

The module `code2logic.fingerprint` extracts symbol-local normalized control-flow graphs (CFG), data-flow graphs (DFG), I/O profiles, and side-effect profiles with SHA-256 source and normalized structural hashes. Alpha-renaming of parameters, local variables, recursive self-references, and docstring/comment variations produces identical structural fingerprints, while behavior-changing edits alter the corresponding CFG/DFG/I-O/effects digests. Structural similarity and candidate ranking remain strictly read-only and advisory (`authority="advisory_only"`).

## Acceptance criteria

- [x] AC-01: Stable read-only structural export and schema version (`code2logic.structural_fingerprint/v1`, `code2logic.structural_export/v1`, `code2logic.structural_similarity/v1`).
- [x] AC-02: Normalized symbol-local CFG, DFG, I/O, and effects fingerprints with raw and normalized source SHA-256 hashes.
- [x] AC-03: Alpha-renaming equivalent positive fixtures and behavior-changing negative fixtures verified via `pytest`.
- [x] AC-04: Structural similarity and candidate ranking remain advisory (`read_only=True`, `authority="advisory_only"`, `grants_authority=False`).

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
