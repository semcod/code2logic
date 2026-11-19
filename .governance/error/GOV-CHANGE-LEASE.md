# GOV-CHANGE-LEASE

## Situation

`GOV-CHANGE-LEASE-001` through `004` mean repository or publication authority
cannot be established from a closed, monotonic change lease.

## Meaning

- `001`: malformed, unknown or non-closed lease, request or receipt.
- `002`: stale CAS/fencing authority or non-monotonic receipt trace.
- `003`: illegal transition, changed frozen HEAD or invalid freeze state.
- `004`: supersession lacks accepted terminal replacement evidence.

## Safe resolution

For a completed delivery under `local-single-clone`, the current owner may
explicitly hand off its valid lease through the managed POSIX controller:

```sh
python .governance/terminal_lease_release.py --root . --request /absolute/request.json
python .governance/terminal_lease_release.py --root . --request /absolute/request.json --apply
```

The closed request has `schema: new-project.terminal-owner-release/v1`,
`requestId`, canonical `worktreeId`, current `ownerActor` and `ownerSession`,
`ownerHandoff: true`, `expectedRevision`, `expectedFencingToken`, the exact
`expectedLeaseSha256` and `terminalReceiptRef`. The receipt must already be in
the configured registry. Actor/session identify the invoking owner; never copy
another session's identity from its lease. The merged receipt must verify in
the configured Git-common terminal registry and bind this ticket's merged
HEAD against its current target. This is a resource handoff, not publication
approval. A dry run grants no authority.
The invoking session supplies `NEW_PROJECT_WRITER_ACTOR` and
`NEW_PROJECT_WRITER_SESSION`; applying requires them to match the request and
the current lease. The controller API takes that caller context separately.

When the original writer session has already exited after verified terminal
delivery (`releasesReservation: true`), the local-single-clone controller may
settle eligible leases (`claimed`, `editing`, `validating`, `approved`,
`merged`, `closed`) without impersonating the former writer session:

```sh
python .governance/terminal_lease_release.py --root . --settle-verified
python .governance/terminal_lease_release.py --root . --settle-verified --apply
python .governance/terminal_lease_release.py --root . --settle-verified --ticket ticket-123 --apply
```

Controller settlement requires an unambiguous verified terminal receipt on
`targetBranch`, clean or already-removed checkout ancestry, and exclusive lease
CAS, writing an immutable receipt under `.subactor/receipts/terminal-owner-release/`
with `"settledBy": "controller:verified-terminal-receipt"`.

The controller rechecks owner, bytes, fencing, clean delivery checkout and
source ancestry, uses canonical transitions and increments fencing. An active
local claim is explicitly cancelled before release; an already approved or
merged lease follows its existing terminal transitions. No approval phase is
invented. A write-ahead receipt makes an interrupted request replayable with
the same request, without repeated transitions. Re-observe after any CAS loss.

This adapter preserves every worktree and branch. Registered controllers,
frozen publication still awaiting reconciliation, unknown/foreign owners,
expired phases and invalid states such as `completed` need their existing
controller. An expired timestamp alone never permits taking ownership or
normalizing the record. Unsupported platforms refuse before controller effects.

1. Stop the writer; never retry with guessed counters.
2. Read the authoritative lease from the repository change controller.
3. Use its exact revision, fencing token, phase and HEAD.
4. For replacement, attach its accepted terminal receipt.

## Verification

```bash
python3 .governance/change_lease_check.py validate .governance/change-lease.json
python3 .governance/change_lease_check.py trace .governance/change-lease-events.jsonl
```

Expected result: `GOV-CHANGE-LEASE-PASS`.

## Do not

- Do not reuse a revision or fencing token.
- Do not change branch, PR or HEAD after `publication_frozen`.
- Do not infer success from a closed PR or absent worktree.
- Do not store credentials, tokens or raw diffs in lease evidence.

## Related rules

- `wellmanifest/poa`: monotonic revision and independent admission.
- `wellmanifest/logs`: correlation, causation, hashes and receipt references.
- `wellmanifest/dsl`: controlled effects require external authority.
- `wellmanifest/new-project`: exact-head publication and terminal cleanup.
