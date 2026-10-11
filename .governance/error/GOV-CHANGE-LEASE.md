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
