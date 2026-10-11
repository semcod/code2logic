# GOV-ARCHITECTURE-001: reconcile architecture ownership

## Situation

An implementation declares data changes outside the integration workstream.

## Meaning

This finding is a routing or contract error, not a request for a second user
approval. Observe the actual diff and existing execution authorization first.

## Safe resolution

1. Check whether responsibility really moves between components. Changing an
   implementation within its existing owner is not a responsibility transfer.
   Do not clear a true transfer merely to pass validation.
2. Classify each data change. `component-local-state` means private state such
   as a deployment journal or cache owned by one declared component. It does
   not cover business database migrations, shared schemas, import/export or
   transfers of data ownership. Bind the record to exactly one declared
   component by its name.
3. `schema-migration`, `cross-component-migration`, `ownership-transfer`,
   `unknown` and legacy prose require the integration workstream. A mixed list
   is integration-owned if any item requires integration. A local-state record
   never overrides `responsibilityChanges=true` or integration-required paths.
4. For a classification error, correct the contract under the existing scope
   and current lease, retaining the reason and validation evidence. For a real
   integration change, resolve the target manifest's integration owner and
   reuse or allocate the appropriate ticket through the managed allocator.
   `integrationTicket` alone does not transfer path ownership.
5. If another writer owns the same files, preserve its work. Prepare a patch
   and isolated regression tests; apply it only after an accepted handoff or
   serialization. Unknown ownership is not inferred from idle time.
6. Revalidate intent and lease before writes. Validate the full delivery diff
   with the exact observed base and head before publication; a check of an
   empty worktree does not validate the PR. Keep protected review unchanged.

## Verification

Run the managed gate against the actual full base/head diff. Verify that the
component exists and the source paths still belong to the selected workstream.

Example (the component must also be present in `architecture.components`):

```json
{
  "kind": "component-local-state",
  "component": "DisplayNet artifact deployment",
  "description": "Private retained-image journal and failed-release quarantine"
}
```

## Do not

Do not relabel migrations as local state or clear true responsibility transfers.

Older adopters intentionally reject typed records. Publish and adopt the
versioned checker, schema, diagnostic and this runbook together through the
managed package mechanism before using them in a target ticket. Do not patch
an adopted checker by hand or mark a candidate package as an approved release.

## Related rules

- `GOV-INTEGRATION-001`: shared-path ownership remains enforced.
- `GOV-SCOPE-001`: a classification does not expand allowed paths.
- `P-CORE-008`: existing session authorization permits bounded execution.
- `P-CORE-009`: reuse the matching authorized ticket.
