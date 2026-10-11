# GOV-WORK-START-001 — work admission before allocation

## Situation

A new task would overlap pending work, exceed the workstream limit, or start
from incomplete branch/worktree observations. An unbound branch rejected by
the commit hook is not necessarily a Git merge conflict.

## Meaning

The query reads registered worktrees, local branch contributions, dirty paths,
branch-owned intent and the managed activity resolver. It does not authorize a
writer, transfer a lease, refresh remotes, allocate a ticket or close old work.
The complete report is clone-local and may contain private filesystem paths;
keep it in private receipt storage, not a tracked ticket.

## Safe resolution

| Route | Use | Boundary |
| --- | --- | --- |
| REUSE_EXISTING | Continue the matching canonical ticket checkout. | Revalidate intent, owner and current lease first. |
| ASSIST_READ_ONLY | Help an active delivery with analysis or review. | No second writer or trusted self-approval. |
| HANDOFF_REQUIRED | Reconcile pending work from an inactive ticket. | Accepted scope, snapshot and controller CAS; no automatic takeover. |
| SERIALIZE | Workstream capacity is occupied. | Queue without another delivery worktree. |
| RECONCILE | Owner, ancestry, pending branch or observations are uncertain. | Preserve work and resolve the specific missing evidence. |
| NEW_TICKET_CANDIDATE | Scope and WIP capacity permit new allocation. | Planning candidate only; never write authority. |

```text
task -> registered clone observation
          |-> existing work -> reuse / assist / handoff / queue
          |-> uncertainty   -> reconcile; preserve data
          `-> free scope    -> managed allocation candidate
                                -> intent + owner + fencing + gate -> one writer
```

1. Run `python3 scripts/work_start_check.py --root . --workstream <declared-id>`
   (adopters use `.governance/work_start_check.py`). Add `--ticket ticket-NNN`
   for an explicit continuation; optionally narrow with repeatable `--path`.
2. Follow the route: REUSE_EXISTING, ASSIST_READ_ONLY, HANDOFF_REQUIRED,
   SERIALIZE, RECONCILE or NEW_TICKET_CANDIDATE. Finish existing authorized
   work first. Read-only assistance is not permission to edit another writer's
   files or self-approve their PR.
3. Handoff requires an accepted scope and controller-owned compare-and-swap
   lease transfer/reacquisition, a restorable snapshot and exact-head checks.
   If unavailable, queue the affected work without a delivery worktree.
4. Keep disjoint authorized work moving. Do not count a clean integrated
   historical checkout as a new pending delivery merely because it exists.
5. Reobserve immediately before allocation and before writing; verify intent,
   owner, fencing and the governance gate at the effect boundary. A saved
   report is evidence, never a replayable admission token.

For a branch without a registered worktree, distinct commit IDs alone are not
a competing delta. Admission compares the complete Git tree of **every**
commit unique to that branch with target trees strictly after the common
ancestor. A new intentional rollback cannot reuse a pre-divergence snapshot.
If all snapshots already occur there, the branch remains in `uncheckedBranches`
but does not block admission. This narrowly handles preserved pre-rewrite
copies without renaming or deleting them. Matching HEAD alone, matching paths,
or matching patch IDs is insufficient. An unmatched intermediate commit or
later new work still routes to reconciliation. Missing history fails closed.

### Stale carrier of an integrated ticket

Blocker `integrated-ticket-carrier` names an active-projected ticket whose
carrier is dirty in a checkout while its directory is already on the observed
target and no `ticket/NNN` branch lies outside that target. A typical source is
an allocation-time copy left in a primary checkout that is behind the target.
The conservative `status-projection` activity is unchanged, so the copy still
counts toward the workstream limit; admission routes to RECONCILE instead of an
unexplained SERIALIZE. Resolve it without discarding unknown work:

1. Compare each dirty carrier with the target version and confirm no process or
   session is still editing it.
2. Store a content-addressed, secret-scanned snapshot of every dirty file in
   ignored receipt storage, recording base HEAD and target SHA.
3. Recheck the file digests, restore only the snapshotted carrier paths and
   fast-forward the checkout; leave unrelated dirty work in place.
4. Reobserve admission. A differing carrier that records real continuation work
   needs a new or reused ticket, not a restore.

### Writes in the selected checkout

The selected checkout of REUSE_EXISTING is not a competing peer, yet another
writer may have left uncommitted changes in it. Every registered checkout
reports `dirtyNewestModifiedAt`, the newest modification time of its dirty
paths: recency evidence only, never writer identity or authority. When dirty
paths of the selected checkout overlap the requested scope, `requiredBeforeWrite`
asks the caller to confirm they belong to this session. A caller that observed
the checkout earlier passes that report's `dirtyDigest` with
`--ticket ticket-NNN --expect-dirty-digest <sha256>`; any change since then adds
blocker `selected-checkout-changed` and removes REUSE_EXISTING. This is a
clone-local compare-and-swap on content, not a lease or cross-clone lock.
Disjoint dirty work of another writer may continue beside authorized work.

Registered checkout observations, dirty paths, active scopes and WIP limits
are unchanged. Historical content inclusion is not current behavior, owner
consent, a merge receipt, ticket closure or permission to discard history.
Use the normal reconciliation process for cleanup. Target-tree indexing is
local to one observation; a changed target cannot reuse an earlier result.

### Optional publication observation

Add `--observe-publication` to the same query to read live `origin` branch
advertisements, without fetch, ref updates, staging or lazy object downloads.
For example, from an adopted checkout:

```bash
python3 .governance/work_start_check.py --root . --workstream integration \
  --ticket ticket-001 --observe-publication
```

Use the actual declared workstream and ticket. Without this flag the query
remains local and its admission behavior is unchanged. The optional field is
`new-project.publication-observation/v1`, addressed by
`urn:wellmanifest:new-project:schema:work-start-report:v1#publicationObservation`.
Use the helper and schema from the same immutable pin; an older closed schema
does not accept the new opt-in field. This is an observation, not a new gate.

| Field per registered checkout | Meaning |
| --- | --- |
| `uncommittedPathCount` | Staged, unstaged and untracked paths, including tracking carriers. |
| `unpublishedCommitCount` | Commits reachable from HEAD but not from any observed `origin` branch; `null` when not proven. |
| `remoteContainingRefs` | Advertised branch refs proven to contain the complete HEAD history. |
| `sameBranchContainsHead` | Whether the remote branch with the same name contains HEAD; separate from publication on another branch. |
| `headReachableFromTarget` | Git ancestry only, never protected merge, review or release evidence. |
| `nextAction` | Read-only recommendation, not effect authorization. |

Scope is explicitly `origin-heads`: other remotes, tags and hidden PR refs are
not queried. Being ahead of local `main` or a same-name upstream is not proof
that code is absent from GitHub. Shallow history or missing advertised objects
produce `partial`; exact HEAD/ancestry evidence can still prove publication,
but incomplete history cannot prove a nonzero unpublished count. Unavailable
or malformed remote data produces `unavailable`; a changed second advertisement
produces `changed` and invalidates remote-derived facts. `null` is not zero.
No prompt for credentials or Git stderr is exposed in the report. This is a
bounded observation, not an atomic remote snapshot or a cross-machine lock.

The result explicitly lists PR, checks, approval, protected merge, release and
deployment as unobserved stages. Preserve dirty work regardless of remote
status. Gather those stages' own exact-head receipts before claiming DONE.

## Verification

Report `new-project.work-start-report/v1` uses closed schema
`urn:wellmanifest:new-project:schema:work-start-report:v1`. It binds refs,
intent and dirty-content digests, including changes to already dirty files.
The helper, schema and this runbook ship through the immutable package.
Files and opted-in SQLite ticket input use the managed activity resolver.

`python3 tests/work_start_test.py` checks real Git fixtures and no-write queries.
The managed allocator invokes `--allocation-check` under its clone-wide ID
lock before reserving a number. A rejected attempt leaves no new ticket,
high-water reservation or worktree. The query exit code alone does not
authorize development; REUSE_EXISTING also requires the current writer lease.

The allocator accepts repeatable `--path` arguments for explicit implementation
scope, for example `./project/new-ticket.sh --workstream api --path 'api/new/**'`.
Quote glob patterns: the shell must not expand them. The managed storage bridge
validates repository-relative paths against the gate's workstream ownership
predicate before reservation. Malformed, unowned and tracking-only scopes fail.
The exact arguments reach live admission under the allocation lock; the admitted
paths are retained in file and SQLite intents. Without `--path`, admission still
uses the whole workstream. A disjoint scope does not bypass an occupied WIP slot.
Revalidate admission and fencing if the eventual intent expands beyond this scope.

This is not a global scheduler or an editor lock. Independent clones, live
GitHub PR/check/release state, processes and writer authority require separate observations.
The query does not fetch or verify a lease. Recheck it at the effect boundary;
the allocator's ID lock does not replace writer fencing. Unborn seed bootstrap
retains its separate contract, not a development-gate exemption.

## Do not

- Do not use `--force-new`, rename a branch or disable hooks to bypass admission.
- Do not merge, reset, clean, delete, stage or copy foreign work automatically.
- Do not guess owners, remote freshness or independent-clone state from Git.
- Do not treat BLOCKED/PLAN as permission to take a dirty checkout.
- Do not repeat allocation to resolve a missing observation.

## Related rules

P-WORKSPACE-005, P-WORKSPACE-006, C-START-004, C-CONCURRENCY-005,
P-CORE-014, P-TICKET-ACTIVITY-001 and P-LEASE-001.
