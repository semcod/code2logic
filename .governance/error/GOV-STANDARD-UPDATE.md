# GOV-STANDARD-UPDATE-001: explicit standard update could not complete

## Situation

The explicitly invoked compatibility updater found Goal unavailable or
incompatible, release verification failed, or Goal prepared or refused an
update. Its legacy `--pre-commit` protocol prepares changes and returns control
for review; the managed commit hook no longer invokes this updater.

## Meaning

The committed pin remains authoritative. A newer release gains trust only when
Goal verifies its annotated tag, final GitHub Release, full SHA and generated
digests. Preparation does not stage, commit, merge or publish the result.
The managed commit hook checks the staged local immutable pin and worktree
guard only. A new upstream release does not change a feature ticket's pin.

## Safe resolution

1. Preserve the worktree and read the Goal output above this code.
2. Install Goal with `governance adopt --latest --pre-commit` support.
3. Validate `.governance/standard-adoption.json`; when `executor` is
   `koru-goal`, install a compatible Koru supervisor as well.
4. Allocate or resume exactly one standard-adoption ticket in its own worktree.
5. Run explicit adoption in that ticket, review the prepared diff, validate it
   and stage it explicitly before committing.

## Verification

- The explicitly invoked Goal preparation command returns zero when the verified release
  is already pinned.
- A prepared update remains visible for review and does not create a commit.
- An ordinary commit does not invoke Goal, Koru or release discovery.
- Managed governance and standard conformance pass after explicit restaging.

## Do not

- Do not use `--no-verify`, delete the hook or weaken digest checks.
- Do not trust `main`, `latest`, a lightweight tag or unbound release metadata.
- Do not commit the prepared update from an unrelated feature ticket.

## Related rules

- `P-CORE-007`, `P-CORE-014`, `P-CORE-024`
- `GOV-SYNC-001`, `GOV-TICKET-001`
