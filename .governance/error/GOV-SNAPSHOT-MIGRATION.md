# GOV-SNAPSHOT-MIGRATION: bounded import proof rejected

## Situation

A ticket declares `delivery.snapshotMigration`, but its contract, protected grant,
Git subject, initial import or fresh target observation does not validate.

## Meaning

`001` is an invalid contract; `002` is an unavailable or inconsistent Git subject;
`003` is missing or mismatched protected authorization; `004` is invalid import
chronology or missing source ancestry; `005` is changed inventory/import content;
`006` is a consumed authorization, changed base or reused source ticket.
Classification does not turn a failed gate into a pass.

## Safe resolution

1. Reobserve the exact repository, PR branch, head, target base and original source.
2. Recompute the source inventory with the managed `snapshot_migration.py` query.
3. Preserve the predecessor and inspect the new ticket intent and import parents.
4. Have the existing protected policy boundary resolve the exact grant and its
   digest. The candidate cannot select that digest or claim consumption authority.
5. Route new repairs through their ordinary approved budget. Restore the exact
   import only in the owned delivery checkout, preserving pending local work.
6. If the base or grant transaction changed, reconcile its readback and obtain the
   appropriate successor contract through the owner. Never replay a consumed grant.

## Verification

Run the managed gate with authenticated repository, branch, fresh base and the
independently pinned grant. Run every application and isolation test, then the
independent protected reviewer. Reobserve the grant journal and exact PR result
before reporting a merge or resuming an uncertain publication.

## Do not

Do not raise global budgets, forge old intent dates, squash away the preserved
source, create a source-less copy, disable secret scanning, omit tests, self-approve,
force-push or delete the predecessor. Do not treat a local grant file as trusted
merely because it is outside the checkout. Do not edit adopted managed copies.

## Related rules

P-CORE-008, P-CORE-009, C-PUBLISH-003, C-PUBLISH-008, C-LEASE-002.
See `docs/information/snapshot-migration.md` and `governance/intent.schema.json`.
