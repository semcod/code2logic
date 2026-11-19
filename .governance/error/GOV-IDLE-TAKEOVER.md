# GOV-IDLE-TAKEOVER

## Situation

Another agent's ticket blocks the next task, but its writer has stopped. The
idle takeover policy (`new-project.idle-takeover/v1`) lets an autonomous agent
continue that ticket after `coordination.idleTakeover.idleMinutes` without
observed activity, and keeps a board of every ticket's state for the next agent.

## Meaning

- `GOV-IDLE-TAKEOVER-001`: the takeover was refused by policy or state.
- `GOV-IDLE-TAKEOVER-002`: the observation or a snapshot, receipt, lease or
  board write failed.

### Explicit local lease continuation

Standard0.20.149 adds two explicit controller operations. Ordinary `observe`
and `takeover` keep their existing refusal states. A timeout or a metadata
snapshot alone never transfers ownership.

`idle_takeover.py --root PRIMARY recover-reservation --request FILE --actor ID
--session ID` accepts a closed `new-project.expired-reservation-recovery/v1`
request with `requestId`, `workstream`, and `restoration`. The latter is the
existing `new-project.local-ticket-restoration-request/v1` object, including
the exact old reservation SHA-256, owner, revision/fence, metadata snapshot
path/digest and optional exact restoration HEAD. Both input files must be
outside checkouts. The caller supplies a fresh identity, never the old holder's
identity. Recovery requires enabled manifest idle policy, an expired idle lease,
no registered checkout or branch, no integrated metadata and no observable
process in the missing path (including Linux deleted-cwd processes).
Released and frozen/publication-owned leases refuse. This operation requires
Linux process observation; it is not a multi-node controller.

The pinned canonical `expire`/`release` transitions and a fresh claim advance
revision and fencing. The result names the canonical worktree/branch, its new
`writerEnvironment`, and `restorationRequest` for the existing native
`new-ticket.sh --restore-local-request` route. It restores no source bytes,
reserves no new number and grants neither editing nor publication. After
restoration, run the normal work-start/governance gates before writing.

`idle_takeover.py --root OWNED_CHECKOUT checkpoint-owner --request FILE --actor
ID --session ID` accepts `new-project.owner-lease-checkpoint/v1` with
`requestId`, `ticket`, `reservationSha256`, `leaseRevision` and `fencingToken`.
It requires the same current live owner and canonical branch, captures its
actual Git HEAD through a canonical heartbeat, and does not extend expiry or
change scope/owner. Frozen, expired and released leases refuse. Use the returned
fencing values; old tokens no longer authorize a write. This POSIX operation
does not establish review, merge or release provenance.

Both operations hold the existing per-lease lock, revalidate state after
preparation, and use anchored atomic storage. Prepare/result records in
`.subactor/receipts/lease-continuation/` bind request identity and both lease
hashes. An interrupted final receipt can replay the same claim; it cannot
renew a lease or apply a changed request. Retain divergent preparations for
reconciliation rather than overwriting a current owner.

### Policy (single source: the governance manifest)

```json
"coordination": {
  "idleTakeover": { "enabled": true, "idleMinutes": 15, "leaseMinutes": 120 }
}
```

The default and hub manifests carry these values; the manifest schema bounds
them (`idleMinutes` 5–240, `leaseMinutes` 15–480 and greater than
`idleMinutes`). The script has no built-in threshold and no validator of its
own: it applies the pinned `governance_check.idle_takeover_policy_valid`, so a
missing or malformed policy (non-boolean `enabled`, a boolean, zero, negative or
out-of-range duration) reports `POLICY_DISABLED` and nothing is taken over.

### Activity

A ticket is idle only when the newest of these is older than `idleMinutes`:

- the lease `heartbeatAt`;
- the ticket branch commit;
- the newest modification of a dirty or untracked file in the ticket worktree;
- the ticket's latest checkpoint in the stream that `.subactor/manifest.json`
  declares as `continuity.eventStreamPath`.

A live process whose working directory is inside the ticket worktree always
makes the ticket `ACTIVE` (observed through `/proc`; other platforms rely on the
four timestamps).

### Worktree layout (wellmanifest/worktrees v5)

Layout roots come from the pinned `change_lease_check.py` (`WORKTREES_ROOT`,
`LEASE_ROOT`); nothing else defines them. The primary checkout is the first
entry of Git's worktree registry, also when the command runs inside a linked
worktree. A ticket is a takeover candidate only when one delivery unit matches:

- worktree `<primaryCheckout>/.worktrees/<ticket>--<slug>`;
- lease `<primaryCheckout>/.subactor/leases/<ticket>--<slug>.json`;
- branch `ticket/NNN-<slug>` and the lease's `ticketId`;
- no symlink in the canonical worktree path.

Anything else is `NONCANONICAL_LAYOUT` with the failing parts in
`layoutProblems`. Request an adoption upgrade; do not move or recreate it by hand.

### States

| State | Meaning | Action |
| --- | --- | --- |
| `ACTIVE` | Activity within `idleMinutes` or a live process. | Assist read-only or choose other work. |
| `IDLE_TAKEOVER_ELIGIBLE` | Idle, canonical, takeable phase (`claimed`, `editing`, `validating`, `expired`), worktree present. | `idle_takeover.py takeover`. |
| `IDLE_FROZEN` | Publication frozen, dispatching or approved. | Never taken over; follow the PR's validator outcome. |
| `IDLE_INTEGRATED` | Clean worktree whose HEAD is already in the target branch. | Release the lease; nothing to continue. |
| `IDLE_NO_WORKTREE` | Lease without a registered ticket worktree. | Reconcile; never taken over. |
| `IDLE_NOT_TAKEABLE` | Idle in a phase the lease contract cannot expire or release. | Reconcile through the controller. |
| `POLICY_DISABLED` | No enabled manifest policy, so idleness is not measured (a live process still reads `ACTIVE`). | Accepted handoff only. |
| `NONCANONICAL_LAYOUT` | Worktree, lease or branch outside the v5 layout. | Adoption upgrade; never by hand. |
| `INVALID_LEASE` | The repository's pinned lease contract rejects the lease. | Restore controller evidence. |

Phase sets are derived from the pinned contract's transitions, not listed here.

## Safe resolution

### Takeover

```sh
python3 .governance/idle_takeover.py observe            # rewrite and print the board
python3 .governance/idle_takeover.py takeover --ticket ticket-NNN \
  --actor agent:<id> --session <session>
```

`takeover` takes an exclusive, non-waiting lock on
`<lease>.json.lock` (a held lock refuses), re-observes under it and refuses
anything that is not `IDLE_TAKEOVER_ELIGIBLE` or already held by the same
session. Still under the lock it:

1. stores dirty work as a content-addressed tar (tracked diff plus every dirty
   or untracked file) in `.subactor/snapshots/idle-takeover/<ticket>/<sha256>.tar`;
   the worktree is not reset, so the new owner continues from the same files;
2. moves the lease through the pinned change-lease CAS: `expire` (unless already
   expired), `release`, then a new `claimed` lease for the new actor and session
   with revision and fencing token one above the release receipt and
   `leaseMinutes` until expiry;
3. compares the lease bytes and file identity immediately before the receipt and
   the replacement and refuses on any concurrent change; a writer that bypassed
   the lock still fails the fencing token at its next commit;
4. appends the record to `.subactor/receipts/idle-takeover/<ticket>.jsonl`;
5. rewrites the board and prints the record as JSON.

The JSON result names `ticket`, `branch`, `worktreePath`, `leasePath` and
`writerEnvironment` (`NEW_PROJECT_WRITER_ACTOR`, `NEW_PROJECT_WRITER_SESSION`,
`NEW_PROJECT_LEASE_REVISION`, `NEW_PROJECT_FENCING_TOKEN` for the writer hook).
Take these only from the result (worktrees rules 9–10), export the environment,
and work only inside `worktreePath`. A non-zero exit ends the attempt.

The authority reference is
`policy:new-project.idle-takeover/v1;idleMinutes=…;limit=…;lastActivity=…`.
It authorizes continuing the ticket's existing intent and scope only. It never
grants review, approval, merge, a scope change or a takeover of a frozen
publication; the independent Validator remains required.

### Autonomy board

Every `observe`, `takeover` and `work_start_check.py` run rewrites
`.subactor/cache/autonomy-board.json` and `.md` in the primary checkout (the
root-ignored cache namespace). The header names the worktree and lease roots
and links the repository, its pull requests and its issue list. Each ticket
lists state, owner, phase, idle minutes, the newest activity source, dirty file
count, its worktree path and links to the branch, README and pull request. Read
it before choosing the next task. The board is an observation and grants no
authority.

## Verification

```sh
python3 tests/idle_takeover_test.py
```

## Do not

- Do not take over a ticket that is not `IDLE_TAKEOVER_ELIGIBLE`, or treat lease
  expiry, an old commit or a missing heartbeat alone as a handoff.
- Do not reset, clean, move or recreate the previous writer's worktree; the
  snapshot is evidence, not a replacement for the files.
- Do not hand-write a lease, reuse a revision or fencing token, or copy the
  previous holder's actor or session.
- Do not take paths from a directory listing; use only the JSON result.
- Do not treat the takeover as review, approval, merge or scope authority.

## Related rules

- `GOV-WORK-START`: routes and accepted handoff.
- `GOV-CHANGE-LEASE`: CAS transitions, fencing and receipts.
- `wellmanifest/worktrees` v5: canonical worktree and lease layout, rules 1–13.
- `wellmanifest/nohardcode` and `wellmanifest/ssot`: the policy lives in the
  manifest and the layout in the lease contract; the script repeats neither.
