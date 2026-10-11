# GOV-REMEDIATION-001/002/003/004 — invalid or inconsistent remediation intent

## Situation

`GOV-REMEDIATION-001` means the target-owned remediation intent is malformed or
semantically unsafe. `GOV-REMEDIATION-002` means a todo2code plan conflicts with
accepted scope, criteria, priority or preservation constraints.
`GOV-REMEDIATION-003` means the advisory overlay no longer matches the
authority-bearing intent digest. `GOV-REMEDIATION-004` means a declared task or
TODO projection is missing, differs byte-for-byte from the accepted intent, or
resolves outside the selected repository root.

## Meaning

The deterministic boundary cannot prove that the proposed refactoring still
implements the accepted diagnostic intent. LLM and todo2code output remains
advisory and cannot repair that authority gap by assertion.

## Safe resolution

1. Open the populated `remediation-intent.dsl.json` in the affected target
   repository ticket; do not copy it into the Governance Hub.
2. For `GOV-REMEDIATION-001`, resolve every reported field, path, dependency,
   applicability signal and verification, then validate again.
3. For `GOV-REMEDIATION-002`, reject or regenerate plans outside accepted scope.
   If the objective truly changed, record a fresh bounded intent and authority.
4. For `GOV-REMEDIATION-003`, discard the stale advisory overlay and rerun
   todo2code analysis against the current intent.
5. For `GOV-REMEDIATION-004`, render both declared projections atomically,
   verify them before extraction and reject any path/symlink escape.
6. Give `analyze-todo2code` the exact graph, diagnostics and plan set from the
   same run. It correlates `source.path` to projection record IDs and ignores
   repository history that does not cite those IDs.
7. Keep unknown ownership explicit and preserve dirty worktrees or other user
   state until a human classifies them.

## Verification

Run `validate`, then `render-todo2code <intent> --root .`, then
`verify-todo2code <intent> --root .`, and require zero exit statuses. Run
todo2code deterministically on those exact task/TODO files. Regenerated
analyzed intents must bind current intent, graph, diagnostics and plan digests,
list projection record IDs, and contain no blocking todo2code finding before
implementation proceeds.

## Do not

Do not edit digests by hand, suppress applicability uncertainty, infer missing
owners, widen paths from an LLM suggestion, or authorize deletion merely to
make validation pass. Do not use a target ticket or incident log as a reusable
runbook.

## Related rules

`C-DIAGNOSTIC-001`, `C-DIAGNOSTIC-002`, `C-DIAGNOSTIC-003`,
`C-REMEDIATION-001`, `C-REMEDIATION-002`, `C-REMEDIATION-003`,
`C-REMEDIATION-004`, `C-REMEDIATION-005`, `P-CORE-008`, `P-CORE-020`.
