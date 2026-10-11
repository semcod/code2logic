# Reconcile intent before discarding an unmerged branch

Before proposing an unmerged branch for discard, reconcile its accepted intent
against the current target branch. An orphaned branch is a lifecycle finding,
not evidence that its work is obsolete. A backup is preservation, not a promise
to implement the work later. Keep the decision about requirements separate from
the decision about a Git ref.

## Required procedure

1. Observe the repository, exact source ref/SHA, target ref/SHA, source intent
   bytes and SHA-256, PRs, dirty state, leases and active processes. Preserve
   unknown work. Obtain and verify a recoverable archive; include dirty work
   only through the existing secret-scanned snapshot boundary.
2. Derive the complete criterion inventory from the accepted intent and its
   acceptance criteria. Bind that derivation to the source intent digest and
   preserve source references. Missing or ambiguous intent requires review; do
   not invent a smaller inventory to make a report pass.
3. Check Git ancestry, then patch/content equivalence. Different commit IDs do
   not imply different functionality (squash, cherry-pick and reimplementation
   change history). Equal patch IDs alone do not prove present-day behavior.
   For code changes, bind relevant behavioral tests to the current target SHA.
4. Classify every criterion: `implemented`, `partial`, `superseded`, `missing`
   or `unknown`. Cite immutable evidence. For `partial`/`missing`, preserve a
   linked follow-up ticket and intent, or an explicit owner discard decision.
   `superseded` requires the accepted decision that replaced the requirement.
   `unknown` never permits automatic resolution, even with a backup.
5. Present this reconciliation before requesting any new owner decision. Reuse
   existing authority only if it explicitly covers the exact operation. A
   report does not grant branch deletion, ticket closure or merge authority.
6. The protected controller rechecks authority, the receipt chain, source and
   target SHA, archive integrity and exact ref immediately before a mutation.
   A moved head invalidates the observation; reacquire it. Retain an external
   operation receipt and the linked residual-work disposition. Follow the
   existing worktree/branch cleanup and protected publication procedures.

## Read-only conformance boundary

The managed checker validates a report against an independently acquired
observation and a content-addressed evidence directory:

```bash
python3 .governance/branch_intent_reconciliation.py \
  --report /external/report.json \
  --observation /protected/observation.json \
  --evidence-root /protected/evidence
```

In this hub the script is `scripts/branch_intent_reconciliation.py`. All three
input artifact kinds use `branch-intent-reconciliation.schema.json`.

The report binds `repository`, `sourceRef`, `sourceHeadSha`, `targetRef`,
`targetHeadSha`, and `intentSha256`. Each criterion has `id`, `outcome`,
`evidence` references, and nullable `followUp`/`decision` references. The
preservation reference is mandatory. Each reference is `{receiptRef, sha256}`.

The observation contains those same bindings, the full `criteria` inventory
with `requiredProof` (`content`, `behavior`, `either`), and a `receipts` map from
verified receipt identity to SHA-256. The controller obtains this map outside
the author's checkout after checking issuer, scope, archive restoration and
evidence provenance. It must not simply copy the report or use an author-made
observation as authority. A hash establishes integrity, not authenticity.

Each evidence file is named `<sha256>.json`. It contains its schema identity,
receipt identity, bindings, criterion IDs, kind and closed `facts` object:

| Kind | Facts verified by conformance | Required upstream verification |
| --- | --- | --- |
| `preservation` | Archive ref/hash and `restoreVerified=true` | Actually restore/verify the archive and its source SHA; retain its storage |
| `content-equivalence` | Source/target paths and equal byte digests | Acquire bytes at both pinned commits; prove they address the criterion |
| `test-result` | Suite/result digests and `passed=true` | Execute relevant tests at the target SHA; verify criterion coverage and logs |
| `decision` | Decision ref, actor, supersede/discard disposition | Verify the actor's authority and the accepted decision bindings |
| `follow-up` | Ticket ref and its intent digest | Verify the ticket exists and owns the outstanding criterion |
| `advisory` | Analysis ref | Never sufficient implementation or disposition evidence |

The checker reads and hashes receipts, rejects receipts outside the observation
allowlist, checks bindings and criterion coverage, and checks the required proof
kind. It does not execute tests, restore archives, contact GitHub, verify actor
identity or prove arbitrary program equivalence. These belong to evidence
producers and the protected controller. Content proof cannot satisfy a criterion
whose independently selected `requiredProof` is `behavior`.

Exit 0 means `ready-for-owner-review`, exit 1 means unresolved `needs-review`,
and exit 2 means invalid/incomplete evidence (`GOV-BRANCH-INTENT-001`). Every
result has `authority=none` and `deletionAuthorized=false`. `unknown` remains
unresolved regardless of LLM confidence or whether other criteria pass.

## Tool composition and prevention

Intent/Contract DSL can formalize criteria and exclusions. data2dsl can compare
bounded facts while retaining provenance. todo2code can link intent, Git, AST
and tests and identify gaps. Their outputs remain evidence/advice; `MATCH`,
`ALIGNED` or an LLM verdict is not discard authority.

Preserve the link `criterion -> implementation/test -> replacement/follow-up ->
terminal receipt`. Run reconciliation when work is superseded or a PR closes
without merge, rather than waiting for an orphan-branch publication failure.
Escalate ambiguous criteria with the evidence already collected. Do not create
carrier-only closure PRs, hide missing work behind a backup, or silently mark
unimplemented requirements as completed.

The package ships the checker, schema and this procedure. Adoption remains an
explicit pinned package upgrade. Product cleanup controllers must call this
boundary with independently verified observations before mutations; shipping
the standard does not automatically install enforcement in every product.
