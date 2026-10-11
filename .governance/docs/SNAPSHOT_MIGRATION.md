---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "snapshot-migration",
  "kind": "information",
  "version": 3,
  "title": "One-time lossless snapshot migration",
  "status": "proposed",
  "owner": "wellmanifest/new-project",
  "scope": "repository",
  "created": "2026-09-14",
  "updated": "2026-09-28",
  "review_after": "2026-10-05",
  "source_revision": "a4178b9cf6fa12540ee7406d7f38391dd4fa1f30",
  "affected_repositories": ["wellmanifest/new-project"],
  "evidence": ["repo://wellmanifest/new-project/scripts/snapshot_migration.py", "repo://wellmanifest/new-project/tests/snapshot_migration_test.py"]
}
---

# One-time lossless snapshot migration

<!-- docs:section purpose -->
## Purpose

Recover a published pre-adoption snapshot without inventing historical intent
or changing ordinary delivery budgets. Prefer resume when the existing contract
is valid. Split only when each independently accepted slice preserves its source
and coverage. A new snapshot migration needs its own allocated ticket and an
explicit, independently acquired authorization for that exact import.

<!-- docs:section scope -->
## Contract and ownership

`delivery.snapshotMigration` binds repository, accepted base, original source
commit, source tree, canonical inventory SHA-256 and an authorization reference.
The new ticket contains its ordinary repair scope and budget. Its complete intent
must be accepted before implementation. The old snapshot, authorship, timestamps
and refs remain unchanged. The standard validates a proof; the consumer owns the
actual import and adopted policy, and the protected publisher owns effects.

Generate the complete inventory without modifying Git:

```sh
python3 scripts/snapshot_migration.py --root CHECKOUT --base BASE_SHA --source SOURCE_SHA
```

The digest covers sorted entries containing path and before/after Git object ID
and file mode, including additions, removals and symlinks. Gitlinks and ambiguous
paths are refused. This observation has no authority. The protected grant names
the exact implementation paths eligible for import accounting. Its length is the
approved import count; it never becomes a repository-wide limit.

<!-- docs:section content -->
## Lossless import and new work

Allocate a fresh ticket with a canonical branch/worktree from the exact approved
base. Record its README and intent before writing the imported implementation.
Create one merge commit whose first parent is that base and whose second parent
is the exact preserved source. Its tree must be byte/mode identical to the source
except for the new ticket's metadata, which includes the accepted intent and
README. Do not run a merge experiment on the predecessor branch. A conflicting
or interrupted import remains a local recovery operation; preserve both parents
and stop before publication.

The exact paths proven unchanged against the protected grant are historical
context when selecting the new ticket and checking changed-path ownership.
They do not need to be claimed in its ordinary repair scope. The scope patterns
it does declare must still belong to its workstream. This distinction grants no
ownership to change an imported file, close an old ticket or take over a lease.
An import-only candidate is material delivery: it selects the current migration
ticket and still requires ordinary independent approval for the exact subject.

Ordinary follow-up commits may contain only separately authorized repairs. A file
changed from the snapshot consumes the ordinary repair budget, even when that
change restores the original base contents. Working-directory repairs also stop
qualifying as unchanged imports. Component ownership, allowed paths, secret
scanning, immutable adoption, tests and independent review remain required.
Only history already reachable from the proven source is excluded from the new
ticket's chronology check. Equal trees with missing ancestry do not qualify.

## Managed allocation before publication

Run the independently installed immutable package's `project/new-ticket.sh`
from the target checkout, with `--workstream ID --snapshot-proposal REQUEST`.
The closed `new-project.snapshot-proposal-request/v1` request contains a stable
`requestId`, repository, exact base/source, target branch, canonical slug and a
complete `intentTemplate` without a manual ticket ID or migration contract.
The allocator reserves the next ID under the clone-wide lock/high-water mark,
returns the proposal path and digest, and creates no branch, checkout or lease.
Changed input under the same request ID is rejected; interrupted reservations
are preserved. This proposal grants no authority.

After the protected consumer has reviewed the exact import and acquired its
own controller lease, invoke `--snapshot-materialize REQUEST`,
`--recovery-lease-store DIR`, `--migration-authorization FILE` and
`--migration-authorization-sha256 SHA`. The closed materialization request binds
`proposalPath`, `proposalSha256`, lease ID, revision, fencing token and owner
actor/session. The controller must already hold an unexpired editing lease for
the exact repository, branch, worktree, scope and complete plan bytes.
Authority inputs must reside outside all registered checkouts and Git metadata.
The standard neither issues a grant nor acquires or renews a lease.

The installed package supplies executable helpers; target files supply target
policy and source data. An isolated index builds the unpublished import object.
The managed checker validates the detached candidate before a branch can be
created, then rechecks refs, peer dirty state, proposal, protected grant and
controller CAS. Source branches and the primary index remain intact. A failure
preserves the detached candidate and reservation for reconciliation; it never
pushes, approves, merges or consumes a grant. Local single-clone file storage is
the supported adapter; registered and SQLite allocation retain their own
protected controllers.

<!-- docs:section evidence -->
## Protected authorization and single use

The authorization schema is `new-project.snapshot-migration-authorization/v1`,
registered with the contract in `governance/snapshot-migration.schema.json`.
It binds grant ID, repository, ticket, exact source contract and complete intent
digests, head branch, target branch, accepted base and the implementation path
allowlist. Explicit `historicalTickets` name unchanged source metadata that this
candidate treats as history; this does not close tickets or transfer a live lease.
`maxUses` is exactly one. A consumed grant is rejected.

The checker requires `--migration-authorization` outside the candidate checkout
and `--migration-authorization-sha256` from independently protected configuration.
It also requires `--expected-repository` and `--migration-branch`; the latter is
the authenticated PR head branch, including in detached merge-result jobs. A
candidate-provided file, digest, command-line override or Markdown approval is
not a trusted grant. Infrastructure must provision these inputs through its
existing protected policy process before admitting a migration. Never derive
the expected digest from the same untrusted file at execution time.

The trusted caller supplies the freshly observed target as `--base` and tests
its exact candidate/merge result as `--head`. A different current base rejects the
single-use contract, including a second publication after the first merge. The
protected publisher must reobserve that base immediately before merge, serialize
its existing grant transaction and record consumption in its external journal.
A timeout requires readback of the same transaction before another effect. This
read-only checker neither operates that journal nor manufactures approval. A
publisher unable to enforce consumption must refuse migration publication.

<!-- docs:section next_actions -->
## Validation and adoption

Run `python3 tests/snapshot_migration_test.py`, the existing governance regression
suite, package/adoption checks and the managed gate. Fixtures cover changed pins,
foreign subjects, additional import files, missing source history, missing intent,
consumed grants, changed bases, dirty repairs, import-only approval rejection,
wrong-head reviews and unchanged ordinary scope, ownership and budgets.
Passing fixtures proves the standard implementation only. A consumer still needs
the independently published immutable package, supported CI pin, a real grant,
full application tests and a protected exact-head result before review and merge.

<!-- docs:section limitations -->
## Limits and rollback

This package adds no production grant service and no implicit grant transport.
It does not authorize a migration solely because its inventory is valid. A
specific consumer's historical findings remain in its own repository and cannot
be dismissed by this document. Source, package, adoption, deployment, canary and
publication remain distinct stages. Roll back through an independently reviewed
successor package while retaining the original source and recovery history.
